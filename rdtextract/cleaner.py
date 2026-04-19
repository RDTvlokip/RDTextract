"""HTML cleaner: strips nav/footer/scripts/ads/hidden elements, keeps semantic content."""

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
        'modal', 'overlay', 'ad', 'ads', 'advert', 'advertisement',
        'social', 'share', 'sharing', 'comment', 'comments',
        'related', 'recommended', 'newsletter', 'subscribe',
        'widget', 'toolbar', 'pagination',
    }

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
        """Clean HTML, keeping only useful content (~90% size reduction)."""
        try:
            from bs4 import BeautifulSoup, Comment

            soup = BeautifulSoup(html, 'html.parser')

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

            body = soup.find('body')
            if not body:
                body = soup

            for tag in body.find_all(list(HTMLCleaner._JUNK_TAGS)):
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
            for tag in list(body.find_all(attrs={'hidden': True})):
                if tag.parent is not None:
                    tag.decompose()
            for tag in list(body.find_all(attrs={'aria-hidden': 'true'})):
                if tag.parent is not None:
                    tag.decompose()
            for tag in list(body.find_all(style=re.compile(r'display\s*:\s*none|visibility\s*:\s*hidden', re.I))):
                if tag.parent is not None:
                    tag.decompose()

            for tag in list(body.find_all(True)):
                if tag.parent is None:
                    continue
                if HTMLCleaner._is_junk_element(tag):
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
            logger.error(f"Error cleaning HTML: {e}")
            return html
