"""Markdown converter: walks a (cleaned) HTML tree and emits Markdown.

Custom implementation, no external Markdown lib (markdownify is buggy on many
edge cases). Output is optimized for LLM training: keeps semantic structure
(headings, lists, tables, code), drops UI/technical noise (forms, media, links).
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter

logger = logging.getLogger(__name__)


class MarkdownConverter:
    """Convert (cleaned) HTML to Markdown."""

    _SKIP_TAGS = frozenset({
        'script', 'style', 'noscript', 'template', 'meta', 'link', 'base',
        'head', 'title',
        'form', 'input', 'button', 'select', 'option', 'optgroup', 'textarea',
        'label', 'fieldset', 'legend', 'datalist', 'output', 'progress', 'meter',
        'iframe', 'embed', 'object', 'param', 'canvas', 'svg', 'math',
        'audio', 'video', 'track', 'source', 'picture', 'img', 'map', 'area',
        'acronym', 'applet', 'basefont', 'big', 'blink', 'center', 'dir', 'font',
        'frame', 'frameset', 'isindex', 'keygen', 'listing', 'marquee', 'menuitem',
        'multicol', 'nextid', 'nobr', 'noembed', 'noframes', 'plaintext',
        'rb', 'rtc', 'spacer', 'strike', 'tt', 'xmp', 'bgsound', 'image',
        'layer', 'nolayer', 'ilayer',
        'ruby', 'rt', 'rp',
    })

    _BLOCK_WRAPPERS = frozenset({
        'div', 'section', 'article', 'main', 'address', 'hgroup',
        'figure', 'figcaption', 'details', 'summary', 'dialog', 'search',
        'header', 'footer', 'nav', 'aside',
    })

    # Day + FR month (full or abbreviated, optional trailing dot) + 4-digit year,
    # tolerant of missing spaces. Full names precede abbreviations in the
    # alternation so "avril" wins over "avr". Groups: (day)(month)(dot?)(year).
    _DATE_GLUE_RE = re.compile(
        r'(\b\d{1,2}) ?'
        r'(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|'
        r'septembre|octobre|novembre|décembre|decembre|'
        r'janv|févr|fevr|fév|fev|avr|juil|juill|sept|sep|oct|nov|déc|dec)'
        r'(\.?) ?(\d{4}\b)',
        re.IGNORECASE,
    )

    # Invisible / format characters → removed (None) or folded to a plain space.
    _INVISIBLE_TRANS = {
        0x00A0: ' ', 0x2007: ' ', 0x2009: ' ', 0x202F: ' ',  # nbsp, figure, thin, narrow-nbsp
        0x2002: ' ', 0x2003: ' ', 0x2008: ' ', 0x205F: ' ',  # en/em/punct/math spaces
        0x200B: None, 0x200C: None, 0x200D: None, 0x2060: None, 0xFEFF: None,  # zero-width, WJ, BOM
        0x00AD: None,                                          # soft hyphen
        0x200E: None, 0x200F: None,                            # LRM / RLM
        0x202A: None, 0x202B: None, 0x202C: None, 0x202D: None, 0x202E: None,  # bidi embeddings
    }

    @classmethod
    def to_markdown(cls, cleaned_html: str) -> str:
        """Convert HTML (ideally pre-cleaned) to Markdown."""
        try:
            from bs4 import BeautifulSoup

            from rdtextract import PARSER
            soup = BeautifulSoup(cleaned_html, PARSER)
            root = soup.find('body') or soup
            text = cls._render(root, list_indent=0)

            # Normalise invisible/format characters that pollute a text corpus:
            # zero-width spaces/joiners, BOM, soft hyphens and bidi marks are
            # removed; exotic space variants (NBSP, narrow/thin) become a plain
            # space so the whitespace-collapse below can do its job.
            text = text.translate(cls._INVISIBLE_TRANS)

            # Stash code blocks before whitespace cleanup (preserves indentation).
            placeholders: list[str] = []

            def _stash_code(m):
                placeholders.append(m.group(0))
                return f'\x00CODEBLOCK{len(placeholders) - 1}\x00'

            text = re.sub(r'```[^\n]*\n.*?\n```', _stash_code, text, flags=re.DOTALL)

            text = re.sub(r'[ \t]+\n', '\n', text)
            text = re.sub(r'\n{3,}', '\n\n', text)
            text = re.sub(r'(?<=\S) {2,}', ' ', text)
            text = re.sub(r'\n {1,}(?![-*+>\d])', '\n', text)

            # Restore breadcrumb separators between inline siblings.
            text = re.sub(r'(\w)[ \t]*([>›»])[ \t]*(?=\w)', r'\1 \2 ', text)

            # Drop the space our <a> renderer injects when a link is immediately
            # followed by punctuation ("Visitez ce lien ." → "Visitez ce lien.").
            # Guarded so we never touch domain/extension dots (" .com", " .fr"),
            # decimals (" ,5"), or French typography (space before ; : ! ? » is
            # correct in FR and left untouched).
            text = re.sub(r'(\S) +\.(?![\w.])', r'\1.', text)   # " ." but not " .com"
            text = re.sub(r'(\S) +,(?!\d)', r'\1,', text)       # " ," but not " ,5"
            text = re.sub(r'(\S) +([)\]…])', r'\1\2', text)     # " )" " ]" " …"
            text = re.sub(r'(\S) +\.\.\.', r'\1...', text)      # " ..." (ellipsis)

            # Un-glue dates whose day/month/year sit in separate styled <span>s
            # with no whitespace between them ("18avr.2024" → "18 avr. 2024").
            # Anchored on a 1-2 digit day + FR month + 4-digit year, so it fires
            # only on real dates, never on prose.
            text = cls._DATE_GLUE_RE.sub(r'\1 \2\3 \4', text)

            # Strip lines containing only orphan punctuation.
            text = re.sub(r'^[ \t]*[-.>·][ \t]*$', '', text, flags=re.MULTILINE)
            # Strip lines containing only a bare URL (canonical/logo href leaks).
            text = re.sub(r'^[ \t]*https?://\S+[ \t]*$', '', text, flags=re.MULTILINE)
            # Strip standalone UI noise: accessibility skip-links ("Aller au
            # contenu", "Skip to content", skip-nav bars) and action labels
            # ("Haut de page", "Partager", "Imprimer") — pure interface chrome.
            text = cls._strip_ui_lines(text)
            text = cls._strip_breadcrumbs(text)
            text = re.sub(r'\n{3,}', '\n\n', text)

            for i, code in enumerate(placeholders):
                text = text.replace(f'\x00CODEBLOCK{i}\x00', code)

            text = cls._dedup_consecutive_blocks(text)
            text = cls._dedup_consecutive_lines(text)
            text = cls._dedup_repeated_ctas(text)
            text = cls._dedup_global_blocks(text)
            text = text.strip()

            # Fallback chain for SPA / JS-rendered pages with empty body:
            # 1. JSON-LD (rich structured content: Article, Recipe, FAQ, …)
            # 2. <title> + meta description (last resort)
            if not text:
                fallback = cls._extract_jsonld_fallback(soup)
                if fallback:
                    return fallback
                fallback = cls._extract_meta_fallback(soup)
                if fallback:
                    return fallback
            return text

        except Exception as e:
            # Never leak raw HTML into the output: for an LLM training corpus an
            # empty string (correctly flagged by is_low_value_stub) is far safer
            # than markup masquerading as Markdown. Callers treat "" as a skip.
            logger.error(f"Error converting HTML to Markdown: {e}")
            return ''

    # Stub markers per language. Long phrasings reduce false positives on
    # real articles that happen to mention these words in passing.
    _LOW_VALUE_MARKERS = {
        'fr': (
            'réservé aux abonnés', 'la suite est réservée', 'pour lire la suite',
            'déjà abonné', 'abonnez-vous pour lire', 'contenu réservé aux abonnés',
            'cet article est réservé',
            'connectez-vous pour', 'connectez-vous à votre compte',
            'créer un compte pour',
            # Cookie-consent banners that leak as the whole (short) output.
            'nous utilisons des cookies', 'ce site utilise des cookies',
            'ce site web utilise des cookies', 'en poursuivant votre navigation',
            'accepter les cookies', 'gérer mes cookies', 'gérer les cookies',
            'accepter et fermer', 'dépôt de cookies',
        ),
        'en': (
            'subscribers only', 'subscribe to read', 'subscribe to continue reading',
            'this article is for subscribers', 'already a subscriber',
            'sign in to continue', 'log in to continue', 'please sign in',
            'create an account to', 'register to read',
            # Cookie-consent banners.
            'we use cookies', 'this website uses cookies', 'this site uses cookies',
            'accept all cookies', 'manage cookies', 'by continuing to browse',
        ),
        'es': (
            'solo para suscriptores', 'suscríbete para leer', 'contenido exclusivo para suscriptores',
            'inicia sesión para', 'crea una cuenta para',
        ),
        'de': (
            'nur für abonnenten', 'abonnieren sie', 'für abonnenten',
            'melden sie sich an', 'konto erstellen',
        ),
        'it': (
            'riservato agli abbonati', 'abbonati per leggere', 'contenuto riservato agli abbonati',
            'accedi per continuare', 'crea un account per',
        ),
    }
    _LOW_VALUE_EXACT = frozenset({
        # FR
        'aller au contenu', 'impossible de générer le snapcode',
        # EN
        'skip to content', 'skip to main content',
        # ES
        'saltar al contenido',
        # DE
        'zum inhalt springen',
        # IT
        'vai al contenuto',
    })
    _LOW_VALUE_MAX_CHARS = 500

    @classmethod
    def is_low_value_stub(cls, markdown: str, language: str | None = None) -> bool:
        """True if markdown carries no LLM training value (paywall/login/empty/skip-link).

        Args:
            markdown: text to evaluate.
            language: ISO 639-1 code ('fr', 'en', 'es', 'de', 'it') to restrict
                marker check to one language. None = check all supported languages.
        """
        # Non-str (e.g. None from a failed upstream step) carries no training
        # value: treat as a stub to skip rather than raising in the pipeline.
        if not isinstance(markdown, str):
            return True
        text = markdown.strip()
        if not text:
            return True
        if len(text) > cls._LOW_VALUE_MAX_CHARS:
            return False
        lower = text.lower()
        if lower in cls._LOW_VALUE_EXACT:
            return True
        if language:
            markers = cls._LOW_VALUE_MARKERS.get(language, ())
        else:
            markers = tuple(m for ms in cls._LOW_VALUE_MARKERS.values() for m in ms)
        return any(m in lower for m in markers)

    @classmethod
    def _extract_jsonld_fallback(cls, soup, min_total_chars: int = 200) -> str:
        """Build markdown from JSON-LD structured data when walker yields empty.

        Recognises common Schema.org types: Article, NewsArticle, BlogPosting,
        Recipe, FAQPage, HowTo, Product. Many SPA / SSR pages hide their real
        content here while leaving <body> empty.
        """
        scripts = soup.find_all('script', attrs={'type': 'application/ld+json'})
        if not scripts:
            return ''

        candidates: list[dict] = []
        for s in scripts:
            raw = s.string or s.get_text() or ''
            if not raw.strip():
                continue
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue
            # Flatten @graph and lists
            if isinstance(data, list):
                candidates.extend(d for d in data if isinstance(d, dict))
            elif isinstance(data, dict):
                if isinstance(data.get('@graph'), list):
                    candidates.extend(d for d in data['@graph'] if isinstance(d, dict))
                else:
                    candidates.append(data)

        for obj in candidates:
            md = cls._jsonld_to_markdown(obj)
            if md and len(md) >= min_total_chars:
                return md
        return ''

    @staticmethod
    def _jsonld_to_markdown(obj: dict) -> str:
        """Render one JSON-LD object as markdown if its @type is supported."""
        t = obj.get('@type', '')
        if isinstance(t, list):
            t = t[0] if t else ''

        def clean(s) -> str:
            if not isinstance(s, str):
                return ''
            return re.sub(r'\s+', ' ', s).strip()

        def html_to_text(s: str) -> str:
            return clean(re.sub(r'<[^>]+>', ' ', s)) if s else ''

        parts: list[str] = []
        name = clean(obj.get('name') or obj.get('headline'))
        desc = html_to_text(obj.get('description', ''))

        if t in ('Article', 'NewsArticle', 'BlogPosting', 'TechArticle', 'Report'):
            body = html_to_text(obj.get('articleBody', ''))
            if name:
                parts.append(f'# {name}')
            if desc:
                parts.append(desc)
            if body:
                parts.append(body)

        elif t == 'Recipe':
            if name:
                parts.append(f'# {name}')
            if desc:
                parts.append(desc)
            ings = obj.get('recipeIngredient') or []
            if isinstance(ings, list) and ings:
                parts.append('## Ingrédients\n\n' + '\n'.join(f'- {clean(i)}' for i in ings if clean(i)))
            steps = obj.get('recipeInstructions') or []
            if isinstance(steps, list) and steps:
                lines = []
                for i, step in enumerate(steps, 1):
                    txt = step.get('text') if isinstance(step, dict) else step
                    txt = html_to_text(txt) if isinstance(txt, str) else ''
                    if txt:
                        lines.append(f'{i}. {txt}')
                if lines:
                    parts.append('## Préparation\n\n' + '\n'.join(lines))

        elif t == 'FAQPage':
            entities = obj.get('mainEntity') or []
            if isinstance(entities, list):
                for q in entities:
                    if not isinstance(q, dict):
                        continue
                    qtxt = clean(q.get('name'))
                    ans = q.get('acceptedAnswer') or {}
                    atxt = html_to_text(ans.get('text', '')) if isinstance(ans, dict) else ''
                    if qtxt and atxt:
                        parts.append(f'### {qtxt}\n\n{atxt}')

        elif t == 'HowTo':
            if name:
                parts.append(f'# {name}')
            if desc:
                parts.append(desc)
            steps = obj.get('step') or []
            if isinstance(steps, list):
                lines = []
                for i, step in enumerate(steps, 1):
                    if isinstance(step, dict):
                        s_name = clean(step.get('name'))
                        s_text = html_to_text(step.get('text', ''))
                        line = f'{i}. **{s_name}** — {s_text}' if s_name and s_text else (s_name or s_text)
                        if line:
                            lines.append(f'{i}. {line}' if not line.startswith(f'{i}.') else line)
                if lines:
                    parts.append('## Étapes\n\n' + '\n'.join(lines))

        elif t == 'Product':
            if name:
                parts.append(f'# {name}')
            if desc:
                parts.append(desc)

        return '\n\n'.join(p for p in parts if p)

    @staticmethod
    def _extract_meta_fallback(soup, min_total_chars: int = 200, min_desc_alone: int = 80) -> str:
        """Build minimal markdown from <title> + meta description for SPA pages."""
        title_el = soup.find('title')
        title = re.sub(r'\s+', ' ', title_el.get_text()).strip() if title_el else ''

        desc = ''
        for attrs in (
            {'name': 'description'},
            {'property': 'og:description'},
            {'name': 'twitter:description'},
        ):
            m = soup.find('meta', attrs=attrs)
            if m and m.get('content'):
                desc = re.sub(r'\s+', ' ', m['content']).strip()
                if desc:
                    break

        # Seuil double : soit la combinaison title+desc dépasse min_total_chars,
        # soit la desc seule est suffisamment descriptive (>= min_desc_alone).
        # Permet de récupérer les pages où le title est trivial ("Iliad", "Chipstime")
        # mais la meta description porte du vrai contenu.
        if len(title) + len(desc) < min_total_chars and len(desc) < min_desc_alone:
            return ''
        if title and desc:
            return f'# {title}\n\n{desc}'
        return f'# {title}' if title else desc

    @staticmethod
    def _dedup_global_blocks(text: str, min_chars: int = 50, min_repeat: int = 3) -> str:
        """Drop paragraphs ≥min_chars that appear ≥min_repeat times globally.

        Targets repeated UI widgets (gamification cards, horoscope teasers, CTA
        repeated per item). Keeps the 1st occurrence, drops the rest.
        Conservative: 50c protects short markers, 3× protects legitimate refrains.
        """
        blocks = re.split(r'\n{2,}', text)
        counts = Counter(b.strip() for b in blocks if len(b.strip()) >= min_chars)
        repeated = {b for b, n in counts.items() if n >= min_repeat}
        if not repeated:
            return text
        seen = set()
        out = []
        for block in blocks:
            norm = block.strip()
            if norm in repeated:
                if norm in seen:
                    continue
                seen.add(norm)
            out.append(block)
        return '\n\n'.join(out)

    # ── Breadcrumb / caption / repeated-CTA / mega-menu cleanup ──────────────

    _BREADCRUMB_HOME = ('accueil', 'home', 'inicio', 'startseite')
    _BREADCRUMB_SEPS = (' / ', ' > ', ' › ', ' » ', ' — ', ' | ', ' \\ ')

    @classmethod
    def _strip_breadcrumbs(cls, text: str) -> str:
        """Drop breadcrumb trails ("Accueil / X / Y", "Vous êtes ici : …")."""
        out = []
        for line in text.split('\n'):
            s = line.strip()
            low = s.lower()
            if low:
                # "Vous êtes ici" / "You are here" labels (need a trail marker so
                # a real sentence starting that way is not eaten).
                if (low.startswith(('vous êtes ici', 'you are here', 'tu es aquí'))
                        and (':' in low or any(sep in s for sep in cls._BREADCRUMB_SEPS))):
                    continue
                # "Accueil <sep> … <sep> …" trails.
                fw = low.split(' ', 1)[0].rstrip(':')
                if (fw in cls._BREADCRUMB_HOME and len(s) < 200
                        and any(sep in s for sep in cls._BREADCRUMB_SEPS)):
                    continue
            out.append(line)
        return '\n'.join(out)

    @staticmethod
    def _dedup_consecutive_lines(text: str, min_len: int = 15) -> str:
        """Drop a line identical to the previous non-blank one (alt+caption dups)."""
        out = []
        prev = None
        for line in text.split('\n'):
            s = line.strip()
            if s and s == prev and len(s) >= min_len:
                continue
            out.append(line)
            if s:
                prev = s
        return '\n'.join(out)

    # Clear call-to-action openers. A short CTA line repeated many times is a
    # per-item widget ("RDV sur le site" ×14); noun-phrase repeats (job titles,
    # dates) don't match these, so they survive.
    _CTA_MARKERS = (
        'rdv', 'rendez-vous sur', 'en savoir plus', 'en savoir +', 'lire la suite',
        'lire plus', 'voir plus', 'voir le', 'voir la', 'voir les', 'voir tout',
        'voir toute', 'voir l', 'découvrir', 'je découvre', 'télécharger',
        'réserver', "s'inscrire", "je m'inscris", 'consulter', 'commander',
        'ajouter au panier', 'acheter', "plus d'infos", "plus d'informations",
        'nous contacter', 'contactez-nous', 'demander un devis', 'prendre rendez-vous',
        'je participe', 'participer', 'en savoir', 'read more', 'learn more',
        'see more', 'discover', 'download', 'book now', 'sign up', 'add to cart',
    )

    @classmethod
    def _dedup_repeated_ctas(cls, text: str, min_repeat: int = 4, max_len: int = 60) -> str:
        """Keep first, drop repeats of a short CTA line seen ≥min_repeat times."""
        lines = text.split('\n')

        def cta_key(s):
            if not s or len(s) > max_len:
                return None
            low = s.lower().strip('*_ ').strip()
            if any(low.startswith(m) or low == m for m in cls._CTA_MARKERS):
                return s.lower()
            return None

        keys = [cta_key(l.strip()) for l in lines]
        counts = Counter(k for k in keys if k)
        repeated = {k for k, n in counts.items() if n >= min_repeat}
        if not repeated:
            return text
        seen = set()
        out = []
        for line, k in zip(lines, keys):
            if k in repeated:
                if k in seen:
                    continue
                seen.add(k)
            out.append(line)
        return '\n'.join(out)

    # Accessibility skip-links: screen-reader shortcuts that carry no training
    # value. A line is dropped when it *starts with* one of these (word-boundary
    # anchored, so "Comment aller au contenu du coffre" is NOT a skip-link), or
    # starts with a filler verb and contains one, subject to a length/nav guard.
    _SKIP_LINK_CORES = (
        'aller au contenu', 'aller au menu', 'aller au texte', 'aller aux onglets',
        'aller à la navigation', 'aller directement au contenu',
        'accéder au contenu', 'accéder directement au contenu',
        'passer au contenu', 'passer directement au contenu',
        'skip to main content', 'skip to content', 'skip to the content',
        'skip to the main content', 'skip to accessibility', 'skip navigation',
        'skip to navigation', 'jump to content', 'jump to navigation',
        'saltar al contenido', 'ir al contenido',
        'zum inhalt springen', 'zum hauptinhalt springen', 'direkt zum inhalt',
        'vai al contenuto',
    )
    _SKIP_LINK_FILLERS = ('ignorer ', 'passer ', 'cliquez ', 'sauter ', 'aller directement ')
    # Verb-phrases that open a skip-link. ≥3 of them on one line = a concatenated
    # skip-nav bar ("Aller au contenu Aller au menu Aller à la recherche …"),
    # dropped regardless of length even when it doesn't begin with a known core.
    _SKIP_LINK_VERBS = (
        'aller au', 'aller à', 'aller aux', 'skip to', 'passer au', 'passer à',
        'accéder au', 'accéder à', 'saltar al', 'ir al', 'vai al', 'zum ',
    )
    # Destinations a skip-link points at. Requiring one on the concatenated-bar
    # path keeps real sentences ("aller au marché, aller à la plage…") safe.
    _SKIP_LINK_DESTS = (
        'contenu', 'content', 'menu', 'navigation', 'recherche', 'texte',
        'onglets', 'pied de page', 'en-tête', 'accessibilit', 'inhalt', 'contenido',
    )
    # Standalone UI action labels (share / print / back-to-top). Dropped only
    # when they are the *entire* line, so real prose is never touched.
    _UI_NOISE_EXACT = frozenset({
        'haut de page', 'retour en haut', 'retour en haut de page', 'remonter',
        'revenir en haut', 'back to top', 'top of page',
        'imprimer', 'imprimer cette page', 'imprimer la page', 'version imprimable',
        'partager', 'partager cette page', 'partager sur facebook', 'partager sur twitter',
        'partager sur linkedin', 'partager sur x', 'partager par mail', 'partager par email',
        'tweeter', 'envoyer par mail', 'envoyer par email', 'envoyer à un ami',
        'envoyer cette page', "retour à l'accueil", 'retour à l’accueil',
    })
    # First tokens that gate the (cheap) fast-path: every skip-link, filler and
    # UI-noise label above begins with one of these words. Superset of the match
    # set, so behaviour is unchanged — just avoids lowercasing every line.
    _UI_FIRST_WORDS = frozenset({
        'aller', 'skip', 'passer', 'accéder', 'ignorer', 'cliquez', 'sauter',
        'jump', 'saltar', 'ir', 'zum', 'vai', 'direkt',
        'haut', 'retour', 'remonter', 'revenir', 'back', 'top',
        'imprimer', 'version', 'partager', 'tweeter', 'envoyer',
    })
    # Heuristic for standalone UI micro-noise: a *whole* short line that is a
    # generic "read more" call-to-action. Once URLs are dropped it carries no
    # information. Kept to a small, stable stem set (unlike the exhaustive skip
    # lists) and applied only to whole lines, so "En savoir plus sur le concours"
    # (a real, specific sentence) is untouched.
    _READ_MORE_RE = re.compile(
        r'^(?:en savoir (?:plus|\+|davantage)|lire (?:la suite|plus|l[\'’]article)|'
        r'voir (?:plus|tout|la suite|le détail|les? offres?)|tout (?:voir|lire)|'
        r'en lire plus|lire aussi|read more|learn more|see more|discover more|show more)$'
    )

    @classmethod
    def _strip_ui_lines(cls, text: str) -> str:
        """Remove standalone skip-links and UI-action labels (see the constants)."""
        if not text:
            return text
        cores = cls._SKIP_LINK_CORES
        first_words = cls._UI_FIRST_WORDS
        ui_exact = cls._UI_NOISE_EXACT
        out = []
        for line in text.split('\n'):
            stripped = line.lstrip()
            if stripped:
                # Heuristic pass on short whole lines: strip generic read-more
                # CTAs, which carry no information once URLs are dropped. (A lone
                # digit was also tried but a 10k audit showed it eats date
                # fragments like "04"←"JUIN" and numbered lists, so it was dropped.)
                ls = stripped.rstrip()
                if len(ls) <= 25:
                    core = ls.strip('*_ #>»«•·→⭢–—-').strip()
                    if cls._READ_MORE_RE.match(core.lower()):
                        continue
                sp = stripped.find(' ')
                first = (stripped if sp < 0 else stripped[:sp]).lower()
                if first in first_words:
                    norm = stripped.rstrip().lower()
                    # UI-action label as the whole line.
                    if norm in ui_exact:
                        continue
                    # Skip-link: starts with a core, or a filler + contains a core,
                    # or a concatenated nav bar (≥3 skip verb-phrases).
                    verbs = sum(norm.count(v) for v in cls._SKIP_LINK_VERBS)
                    is_skip = norm.startswith(cores) or (
                        norm.startswith(cls._SKIP_LINK_FILLERS) and any(c in norm for c in cores)
                    )
                    if is_skip and (
                        len(norm) <= 60 or '|' in norm or '›' in norm or '·' in norm or verbs >= 3
                    ):
                        continue
                    # Concatenated skip-nav bar that doesn't open with a known core
                    # ("Skip to accessibility … Aller au contenu principal …").
                    # Guarded by a skip destination so real sentences that merely
                    # chain "aller au …" verbs aren't dropped.
                    if (verbs >= 3 and first in ('skip', 'aller', 'passer', 'accéder')
                            and any(d in norm for d in cls._SKIP_LINK_DESTS)):
                        continue
            out.append(line)
        return '\n'.join(out)

    @staticmethod
    def _dedup_consecutive_blocks(text: str) -> str:
        """Drop consecutive identical blocks (responsive mobile/desktop duplicates)."""
        blocks = re.split(r'\n{2,}', text)
        out = []
        prev_norm = None
        for block in blocks:
            norm = block.strip().lower()
            if norm and norm == prev_norm:
                continue
            out.append(block)
            prev_norm = norm
        return '\n\n'.join(out)

    # ── Recursive walker ───────────────────────────────────────────────────

    # Depth cap for the recursive walker. Real pages rarely nest past ~50
    # levels; pathological/adversarial markup (thousands of unclosed <div>s)
    # would otherwise blow Python's recursion limit and abort the whole
    # conversion. Past the cap we flatten the subtree to plain text so content
    # rendered *above* the cap is preserved and no exception escapes. Kept well
    # under Python's ~1000-frame limit (the walker uses ~2 frames per level).
    _MAX_DEPTH = 200

    @classmethod
    def _render(cls, node, list_indent: int = 0, depth: int = 0) -> str:
        from bs4 import NavigableString, Tag

        if depth > cls._MAX_DEPTH:
            if isinstance(node, Tag):
                # get_text() is itself recursive; on a still-deeper subtree it
                # can overflow. Guard it so one pathological branch can't sink
                # the whole document.
                try:
                    return re.sub(r'\s+', ' ', node.get_text(' ', strip=True))
                except RecursionError:
                    return ''
            if isinstance(node, NavigableString):
                text = str(node)
                return re.sub(r'\s+', ' ', text) if text.strip() else ' '
            return ''

        if isinstance(node, NavigableString):
            text = str(node)
            if not text.strip():
                return ' '
            return re.sub(r'\s+', ' ', text)

        if not isinstance(node, Tag) or node.name is None:
            return ''

        name = node.name.lower()

        if name in cls._SKIP_TAGS:
            return ''

        if name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            text = cls._inline(node, depth).strip()
            if not text:
                return ''
            # A heading nested in a list item is not a document heading — it is a
            # styled item title. Rendering it as "### X" produces invalid
            # "- ### X" markdown, so emit bold inline instead.
            if node.find_parent('li'):
                return f"**{text}**"
            level = int(name[1])
            return f"\n\n{'#' * level} {text}\n\n"

        if name == 'p':
            text = cls._inline(node, depth).strip()
            return f"\n\n{text}\n\n" if text else ''

        if name == 'br':
            return '  \n'
        if name == 'hr':
            # Skip <hr> inside <li> (would produce "- ---" glued to next item).
            if node.find_parent('li'):
                return ''
            return '\n\n---\n\n'

        if name == 'blockquote':
            inner = cls._render_children(node, list_indent, depth).strip()
            quoted = '\n'.join(f'> {l}' if l else '>' for l in inner.split('\n'))
            return f"\n\n{quoted}\n\n"

        if name == 'pre':
            lang = ''
            code = node.find('code')
            classes = (code.get('class', []) if code else node.get('class', [])) or []
            for c in classes:
                if c.startswith('language-'):
                    lang = c[len('language-'):]
                    break
            return f"\n\n```{lang}\n{node.get_text().rstrip()}\n```\n\n"

        if name == 'code':
            return f"`{node.get_text()}`"

        if name in ('ul', 'ol', 'menu'):
            return cls._render_list(node, list_indent, depth)

        if name == 'dl':
            parts = []
            for child in node.children:
                if isinstance(child, Tag):
                    inner = cls._inline(child, depth).strip()
                    if not inner:
                        continue
                    if child.name == 'dt':
                        parts.append(f"\n**{inner}**")
                    elif child.name == 'dd':
                        parts.append(f"\n: {inner}")
            return '\n\n' + ''.join(parts).strip() + '\n\n' if parts else ''

        if name == 'table':
            return cls._render_table(node, depth)

        if name in ('strong', 'b'):
            inner = cls._inline(node, depth).strip()
            return f"**{inner}**" if inner else ''
        if name in ('em', 'i'):
            inner = cls._inline(node, depth).strip()
            return f"*{inner}*" if inner else ''
        if name in ('s', 'del'):
            inner = cls._inline(node, depth).strip()
            return f"~~{inner}~~" if inner else ''
        if name == 'u':
            inner = cls._inline(node, depth).strip()
            return f"__{inner}__" if inner else ''
        if name == 'mark':
            inner = cls._inline(node, depth).strip()
            return f"=={inner}==" if inner else ''
        if name in ('kbd', 'samp', 'var'):
            inner = cls._inline(node, depth).strip()
            return f"`{inner}`" if inner else ''

        if name in cls._BLOCK_WRAPPERS:
            inner = cls._render_children(node, list_indent, depth).strip()
            return f"\n{inner}\n" if inner else ''

        # Passthrough (span, a, …): keep text, drop URL.
        # Pour <a> on ajoute un espace trailing pour éviter que des liens
        # adjacents sans whitespace HTML entre eux ne collent leurs textes
        # (ex: deux boutons "Télécharger App Store" + "Google Play" dans
        # le même <div> sans séparateur). Le post-process collapse_whitespace
        # nettoie les espaces multiples si le HTML en contenait déjà.
        inner = cls._render_children(node, list_indent, depth)
        if name == 'a' and inner and not inner.endswith((' ', '\n', '\t')):
            inner += ' '
        return inner

    @classmethod
    def _render_children(cls, node, list_indent: int, depth: int = 0) -> str:
        return ''.join(cls._render(c, list_indent, depth + 1) for c in node.children)

    @classmethod
    def _inline(cls, node, depth: int = 0) -> str:
        """Render inline content only (for headings, paragraphs, cells)."""
        from bs4 import NavigableString, Tag
        out = ''
        for child in node.children:
            if isinstance(child, NavigableString):
                text = re.sub(r'\s+', ' ', str(child))
            elif isinstance(child, Tag) and child.name not in cls._SKIP_TAGS:
                text = cls._render(child, 0, depth + 1)
            else:
                continue
            if text:
                out += text
        out = re.sub(r'[ \t]+', ' ', out)
        out = re.sub(r' *\n *', '\n', out)
        return out.strip()

    @classmethod
    def _render_list(cls, node, list_indent: int, depth: int = 0) -> str:
        from bs4 import Tag
        is_ordered = node.name == 'ol'
        indent_str = '  ' * list_indent
        items = []
        idx = 1
        for child in node.children:
            if not isinstance(child, Tag) or child.name != 'li':
                continue

            # <li> wrapping only a sublist → flatten at current level
            # (avoids "- - X" pattern in directories like service-public.fr).
            if cls._li_is_sublist_only(child):
                flattened = cls._render_children(child, list_indent, depth).strip()
                if flattened:
                    items.append(flattened)
                continue

            marker = f'{idx}.' if is_ordered else '-'
            content = cls._render_children(child, list_indent + 1, depth).strip()
            # Strip a leading bullet from content to avoid "- - X" artifacts.
            # Two distinct triggers:
            #   1. Source HTML has literal "- " in <li> text (CMS quirk where
            #      authors typed dashes manually inside list items).
            #   2. <li> wraps both a nested <ul> AND other content — the inner
            #      <ul> renders first, prefixing with "- ", which collides with
            #      our outer marker.
            if content.startswith(('- ', '* ')):
                content = content[2:].lstrip()
            lines = content.split('\n')
            if lines:
                first = lines[0]
                rest = '\n'.join(lines[1:])
                items.append(f"{indent_str}{marker} {first}")
                if rest:
                    items.append(rest)
            idx += 1
        return '\n\n' + '\n'.join(items) + '\n\n' if items else ''

    @staticmethod
    def _li_is_sublist_only(li) -> bool:
        """True if <li> has no own text — only sublists (possibly wrapped)."""
        sublists = li.find_all(['ul', 'ol', 'menu'])
        if not sublists:
            return False
        sublist_set = set(id(s) for s in sublists)
        for s in li.find_all(string=True):
            if not str(s).strip():
                continue
            in_sublist = False
            for parent in s.parents:
                if id(parent) in sublist_set:
                    in_sublist = True
                    break
                if parent is li:
                    break
            if not in_sublist:
                return False
        return True

    @classmethod
    def _render_table(cls, table, depth: int = 0) -> str:
        """Convert <table> to Markdown table. Handles nested tables and colspan."""
        rows = []
        for tr in table.find_all('tr'):
            if tr.find_parent('table') is not table:
                continue
            cells = []
            for cell in tr.find_all(['th', 'td']):
                if cell.find_parent('tr') is not tr:
                    continue
                try:
                    colspan = max(1, int(cell.get('colspan', '1') or '1'))
                except (ValueError, TypeError):
                    colspan = 1
                for nested in cell.find_all('table'):
                    nested.replace_with(nested.get_text(' ', strip=True))
                txt = cls._inline(cell, depth).replace('|', '\\|').replace('\n', ' ').strip()
                cells.append(txt or ' ')
                for _ in range(colspan - 1):
                    cells.append(' ')
            if cells:
                rows.append(cells)

        if not rows:
            return ''

        ncols = max(len(r) for r in rows)
        rows = [r + [' '] * (ncols - len(r)) for r in rows]

        # Drop fully-empty columns (WordPress layout-tables with image+caption
        # where the image cell is empty after image strip).
        for col_idx in reversed(range(ncols)):
            if all(not r[col_idx].strip() for r in rows):
                for r in rows:
                    del r[col_idx]
                ncols -= 1
        if ncols == 0:
            return ''

        # A single-column table is almost always a layout table (borderless
        # wrapper, "info box", stacked paragraphs) rather than tabular data.
        # Render each non-empty cell as its own paragraph instead of emitting a
        # 1-wide table with an empty "| --- |" header.
        if ncols == 1:
            cells = [r[0].strip() for r in rows if r[0].strip()]
            return '\n\n' + '\n\n'.join(cells) + '\n\n' if cells else ''

        lines = ['| ' + ' | '.join(rows[0]) + ' |']
        lines.append('|' + '|'.join([' --- '] * ncols) + '|')
        for r in rows[1:]:
            lines.append('| ' + ' | '.join(r) + ' |')

        return '\n\n' + '\n'.join(lines) + '\n\n'
