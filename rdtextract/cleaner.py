"""HTML cleaner: strips nav/footer/scripts/ads/hidden elements, keeps semantic content."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


class HTMLCleaner:
    """Utility to clean HTML before Markdown conversion."""

    _JUNK_TAGS = {
        'script', 'style', 'noscript', 'iframe', 'svg', 'canvas',
        'nav', 'footer', 'header', 'aside', 'form', 'button',
        'select', 'option', 'input', 'textarea', 'label',
        'menu', 'menuitem', 'dialog', 'template',
    }

    _JUNK_PATTERNS = {
        'nav', 'navbar', 'menu', 'sidebar', 'footer', 'header',
        'breadcrumb', 'cookie', 'consent', 'banner', 'popup',
        'modal', 'ad', 'ads', 'advert', 'advertisement',
        'social', 'share', 'sharing', 'comment', 'comments',
        'related', 'recommended', 'newsletter', 'subscribe',
        # 'widget' seul est trop large : matche elementor-widget-wrap,
        # tag-widget, gutenberg-widget — qui contiennent du vrai contenu
        # de page sur les CMS WordPress modernes. On garde uniquement les
        # variantes spécifiques de "zone widget" (sidebar / footer widget area).
        'widget-area', 'wp-widget-area', 'widgets-area',
        # 'overlay' seul est trop large aussi : de nombreux thèmes (Joomla Helix,
        # cartes d'actualités) l'emploient pour un effet de survol/légende sur du
        # VRAI contenu. Les overlays réellement parasites sont déjà couverts par
        # leur mot principal ('modal-overlay'→modal, 'popup-overlay'→popup,
        # 'cookie-overlay'→cookie, 'nav-overlay'→nav) et les backdrops génériques
        # sont vides donc retirés par le nettoyage des éléments vides.
        'modal-overlay', 'popup-overlay', 'search-overlay', 'menu-overlay',
        'toolbar', 'pagination',
    }

    # Containers of popular cookie-consent plugins (WordPress + JS). Their class
    # names glue the word "cookie" (cmplz-cookiebanner) so the plain 'cookie'
    # pattern misses them, and a long banner on a short page survives the ratio
    # guard. These identifiers are unambiguous chrome → stripped unconditionally.
    _COOKIE_BANNER_RE = re.compile(
        r'(?:cmplz-cookiebanner|cmplz-manage-consent|cli-modal|cli-bar-popup|'
        r'moove_gdpr|moove-gdpr|borlabs-cookie|tarteaucitron|axeptio|didomi-'
        r'|onetrust-banner|onetrust-consent|ot-sdk-container|iubenda-cs|'
        r'cookie-?consent|cookie-?notice|cookie-?law-info|gdpr-?cookie|cc-window)',
        re.IGNORECASE,
    )

    # Word-boundary regex to avoid false positives (e.g. 'ad' in 'leading-relaxed').
    _JUNK_RE = re.compile(
        r'\b(?:' + '|'.join(re.escape(p) for p in _JUNK_PATTERNS) + r')\b',
        re.IGNORECASE,
    )

    _CONTENT_TAGS = {
        'article', 'main', 'section', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'ul', 'ol', 'li', 'blockquote', 'pre', 'code', 'table', 'thead', 'tbody',
        'tr', 'th', 'td', 'figure', 'figcaption', 'dl', 'dt', 'dd',
        'strong', 'em', 'b', 'i', 'a', 'span', 'br', 'hr', 'img',
        'time', 'address', 'mark', 'abbr', 'cite', 'q', 'sub', 'sup',
    }

    @staticmethod
    def _wraps_article_title(tag) -> bool:
        """True if `tag` wraps an article-title <h1> — a header/container we must
        NOT strip. Common CMS pattern (<header class="entry-header"><h1
        class="entry-title">) otherwise gets decomposed as chrome, silently
        losing the page title on ~1/3 of article pages."""
        for h in tag.find_all(['h1', 'h2'], limit=4):
            cls = ' '.join(h.get('class', [])).lower()
            if (h.get('itemprop') == 'headline'
                    or 'entry-title' in cls or 'post-title' in cls
                    or 'article-title' in cls or 'entry-header' in cls
                    or h.find_parent('article') is not None):
                return True
        # A bare page-title header (<header><h1>Title</h1></header>) with no <nav>
        # and few links is a page title, not the site masthead (which carries a
        # nav menu and many links).
        if tag.name in ('header', 'hgroup') and tag.find('h1') is not None \
                and tag.find('nav') is None and len(tag.find_all('a')) <= 2:
            return True
        return False

    @classmethod
    def _is_junk_element(cls, tag) -> bool:
        classes = ' '.join(tag.get('class', []))
        tag_id = tag.get('id') or ''
        role = (tag.get('role') or '').lower()

        if classes and cls._JUNK_RE.search(classes):
            return True
        if tag_id and cls._JUNK_RE.search(tag_id):
            return True
        if role in ('navigation', 'banner', 'complementary', 'contentinfo', 'menu'):
            return True
        return False

    @staticmethod
    def clean_html(html: str) -> str:
        """Clean HTML, keeping only useful content (~90% size reduction).

        Uses lxml when available (faster). Falls back to html.parser if lxml
        produces suspiciously small output on a large input (signature of
        malformed HTML — lxml is strict and over-nests, html.parser is lenient).
        """
        from rdtextract import PARSER
        result = HTMLCleaner._clean_with(html, PARSER)
        # Heuristic fallback: large input but tiny cleaned output → lxml hit
        # malformed nesting. html.parser is more forgiving on broken markup.
        if PARSER == 'lxml' and len(html) > 50_000 and len(result) < 2000:
            alt = HTMLCleaner._clean_with(html, 'html.parser')
            if len(alt) > len(result) * 3:
                return alt
        return result

    @staticmethod
    def _clean_with(html: str, parser: str) -> str:
        """Internal: do the actual cleaning with a specific parser."""
        # Garde anti-binaire : si le contenu commence par un magic byte de format
        # compressé (gzip 1f 8b, deflate 78 9c/da, brotli) ou par sa forme
        # mojibake après UTF-8 mis-decode, c'est un fetch corrompu (HTTP gzip
        # non décompressé côté client). On retourne vide proprement plutôt que
        # de produire du markdown illisible.
        if not html:
            return ''
        binary_magics = (
            '\x1f\x8b',          # gzip
            '\x78\x9c', '\x78\xda', '\x78\x01',  # zlib/deflate
            '\x1f\xc2\x8b',      # gzip mojibake (1f 8b mal-décodé via UTF-8)
        )
        if any(html.startswith(m) for m in binary_magics):
            return ''
        try:
            from bs4 import BeautifulSoup, Comment
            soup = BeautifulSoup(html, parser)

            for c in list(soup.find_all(string=lambda t: isinstance(t, Comment))):
                c.extract()

            new_head_parts = []

            title = soup.find('title')
            if title and title.string:
                new_head_parts.append(f'<title>{title.string.strip()}</title>')

            new_head_parts.append('<meta charset="utf-8">')

            for tag in soup.find_all('meta'):
                name = (tag.get('name') or '').lower()
                prop = (tag.get('property') or '').lower()
                if name in ('description', 'keywords', 'author', 'robots'):
                    new_head_parts.append(str(tag))
                elif prop.startswith('og:') or prop.startswith('article:'):
                    new_head_parts.append(str(tag))

            for tag in soup.find_all('link', rel='canonical'):
                new_head_parts.append(str(tag))

            # Preserve JSON-LD structured data (used by converter as fallback
            # when <body> is empty — common on SPA pages with SSR JSON only).
            for tag in soup.find_all('script', attrs={'type': 'application/ld+json'}):
                new_head_parts.append(str(tag))

            body = soup.find('body')
            if not body:
                body = soup

            # Known cookie-consent plugin containers are ALWAYS chrome, whatever
            # their size — remove them unconditionally (the generic size/ratio
            # guards otherwise keep a long banner on short pages, e.g. Complianz
            # whose 'cmplz-*' classes don't match the plain 'cookie' pattern).
            for tag in list(body.find_all(class_=HTMLCleaner._COOKIE_BANNER_RE)):
                if tag.parent is not None:
                    tag.decompose()
            for tag in list(body.find_all(id=HTMLCleaner._COOKIE_BANNER_RE)):
                if tag.parent is not None:
                    tag.decompose()

            # Decompose junk tags. For structural semantic tags, apply a size
            # guard: malformed HTML (unclosed <header>/<nav>) makes lxml strictly
            # nest the whole body inside one of these — decomposing it would gut
            # the page. If the tag holds > _STRUCTURAL_KEEP_THRESHOLD chars, it's
            # almost certainly a parser artifact, not real chrome.
            _STRUCTURAL = {'nav', 'header', 'footer', 'aside'}
            _STRUCTURAL_KEEP_THRESHOLD = 1000
            for tag in body.find_all(list(HTMLCleaner._JUNK_TAGS)):
                if tag.parent is None:
                    continue
                if tag.name in _STRUCTURAL:
                    if len(tag.get_text(strip=True)) > _STRUCTURAL_KEEP_THRESHOLD:
                        continue  # likely malformed HTML wrapping real content
                    if HTMLCleaner._wraps_article_title(tag):
                        continue  # e.g. <header class="entry-header"> holds the title
                # A <label> wrapping a heading is a CSS-accordion trigger holding a
                # real question/title (FAQ pattern), not a form-field label —
                # unwrap it so the heading survives instead of being decomposed.
                if tag.name == 'label' and tag.find(['h2', 'h3', 'h4', 'h5', 'h6']):
                    tag.unwrap()
                    continue
                tag.decompose()

            # Strip icon fonts (Material Symbols/Icons, FontAwesome, Glyphicons)
            # whose ligature text leaks into Markdown ("lock", "help", …).
            _icon_re = re.compile(r'material-(symbols|icons)|^fa[brs]?(-|$)|glyphicon', re.I)
            for tag in list(body.find_all(class_=_icon_re)):
                if tag.parent is not None:
                    tag.decompose()

            # Strip responsive duplicates (mobile/desktop variants of same content).
            _hidden_re = re.compile(
                r'\b(?:'
                r'is-hidden-(?:tablet|desktop|widescreen|fullhd)'
                r'|d-(?:md|lg|xl|xxl)-none'
                r'|(?:md|lg|xl|2xl):hidden'
                r'|hidden-(?:md|lg|xl)-up'
                r'|visible-xs(?:-block|-inline|-inline-block)?'
                r'|visible-xs-only'
                r')\b',
                re.IGNORECASE,
            )
            for tag in list(body.find_all(class_=_hidden_re)):
                if tag.parent is not None:
                    tag.decompose()
            # `hidden` attribute : React 18 SSR streaming utilise <div hidden> pour
            # les Suspense boundaries (contenu serveur prêt mais non hydraté).
            # On préserve ces divs si elles contiennent beaucoup de texte.
            for tag in list(body.find_all(attrs={'hidden': True})):
                if tag.parent is None:
                    continue
                if len(tag.get_text(strip=True)) > 1000:
                    continue  # likely React 18 SSR content
                tag.decompose()
            for tag in list(body.find_all(attrs={'aria-hidden': 'true'})):
                if tag.parent is not None:
                    tag.decompose()
            for tag in list(body.find_all(style=re.compile(r'display\s*:\s*none|visibility\s*:\s*hidden', re.I))):
                if tag.parent is not None:
                    tag.decompose()

            # Size guard pour la décomposition par classe/id : si un élément matche
            # junk MAIS contient une part importante du texte du body, c'est presque
            # toujours un faux positif (CMS verbeux : 'main-content with-nav',
            # 'related-page', 'header__wrapper', etc.).
            #
            # Triple critère :
            #   1. seuil absolu 2000c (pour gros sites)
            #   2. ratio > 40% du body (pour petits sites / landing pages)
            #   3. structural + > 1000c (HTML malformé qui wrappe la page)
            _CONTENT_KEEP_THRESHOLD = 2000
            _CONTENT_KEEP_RATIO = 0.40
            body_text_len = max(1, len(body.get_text(strip=True)))

            for tag in list(body.find_all(True)):
                if tag.parent is None:
                    continue
                if HTMLCleaner._is_junk_element(tag):
                    # Never strip a container that holds the article title
                    # (e.g. class="entry-header" matches the 'header' pattern).
                    if HTMLCleaner._wraps_article_title(tag):
                        continue
                    text_len = len(tag.get_text(strip=True))
                    # Structural tag avec gros contenu = HTML malformé
                    if tag.name in _STRUCTURAL and text_len > _STRUCTURAL_KEEP_THRESHOLD:
                        continue
                    # Tag normal contenant beaucoup de texte (absolu OU ratio)
                    if tag.name not in _STRUCTURAL and (
                        text_len > _CONTENT_KEEP_THRESHOLD
                        or text_len / body_text_len > _CONTENT_KEEP_RATIO
                    ):
                        continue
                    tag.decompose()

            _KEEP_ATTRS = {'href', 'src', 'alt', 'datetime', 'title'}
            for tag in list(body.find_all(True)):
                if tag.parent is None:
                    continue
                tag.attrs = {k: v for k, v in tag.attrs.items() if k in _KEEP_ATTRS}

            for tag in list(body.find_all(True)):
                if tag.parent is None:
                    continue
                if tag.name not in ('br', 'hr', 'img') and not tag.get_text(strip=True) and not tag.find('img'):
                    tag.decompose()

            body_html = body.decode_contents().strip()

            head_html = '\n'.join(new_head_parts)
            cleaned = f'<!DOCTYPE html>\n<html>\n<head>\n{head_html}\n</head>\n<body>\n{body_html}\n</body>\n</html>'

            return cleaned

        except Exception as e:
            # Returning the raw input would push unstripped nav/scripts/markup
            # downstream into the converter (and ultimately the corpus). Fail
            # closed with an empty string instead.
            logger.error(f"Error cleaning HTML: {e}")
            return ''
