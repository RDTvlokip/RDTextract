"""Markdown converter: walks a (cleaned) HTML tree and emits Markdown.

Custom implementation, no external Markdown lib (markdownify is buggy on many
edge cases). Output is optimized for LLM training: keeps semantic structure
(headings, lists, tables, code), drops UI/technical noise (forms, media, links).
"""

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

    @classmethod
    def to_markdown(cls, cleaned_html: str) -> str:
        """Convert HTML (ideally pre-cleaned) to Markdown."""
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(cleaned_html, 'html.parser')
            root = soup.find('body') or soup
            text = cls._render(root, list_indent=0)

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

            # Strip lines containing only orphan punctuation.
            text = re.sub(r'^[ \t]*[-.>·][ \t]*$', '', text, flags=re.MULTILINE)
            # Strip lines containing only a bare URL (canonical/logo href leaks).
            text = re.sub(r'^[ \t]*https?://\S+[ \t]*$', '', text, flags=re.MULTILINE)
            text = re.sub(r'\n{3,}', '\n\n', text)

            for i, code in enumerate(placeholders):
                text = text.replace(f'\x00CODEBLOCK{i}\x00', code)

            text = cls._dedup_consecutive_blocks(text)
            text = cls._dedup_global_blocks(text)
            text = text.strip()

            # Fallback: SPA / atypical layouts where walker yields empty
            # but <title> + meta description carry real content.
            if not text:
                fallback = cls._extract_meta_fallback(soup)
                if fallback:
                    return fallback
            return text

        except Exception as e:
            logger.error(f"Error converting HTML to Markdown: {e}")
            return cleaned_html

    # Stub markers (4 cases): empty, paywall, login, lone skip-link.
    _LOW_VALUE_MARKERS = (
        # FR paywall
        'réservé aux abonnés', 'la suite est réservée', 'pour lire la suite',
        'déjà abonné', 'abonnez-vous pour lire', 'contenu réservé aux abonnés',
        'cet article est réservé',
        # Login/auth (long phrasings to avoid false positives in real articles)
        'connectez-vous pour', 'connectez-vous à votre compte',
        'créer un compte pour', 'sign in to continue', 'log in to continue',
        'please sign in',
    )
    _LOW_VALUE_EXACT = frozenset({
        'aller au contenu',
        'impossible de générer le snapcode',
    })
    _LOW_VALUE_MAX_CHARS = 500

    @classmethod
    def is_low_value_stub(cls, markdown: str) -> bool:
        """True if markdown carries no LLM training value (paywall/login/empty/skip-link)."""
        text = markdown.strip()
        if not text:
            return True
        if len(text) > cls._LOW_VALUE_MAX_CHARS:
            return False
        lower = text.lower()
        if lower in cls._LOW_VALUE_EXACT:
            return True
        return any(m in lower for m in cls._LOW_VALUE_MARKERS)

    @staticmethod
    def _extract_meta_fallback(soup, min_total_chars: int = 200) -> str:
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

        if len(title) + len(desc) < min_total_chars:
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

    @classmethod
    def _render(cls, node, list_indent: int = 0) -> str:
        from bs4 import NavigableString, Tag

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
            level = int(name[1])
            text = cls._inline(node).strip()
            return f"\n\n{'#' * level} {text}\n\n" if text else ''

        if name == 'p':
            text = cls._inline(node).strip()
            return f"\n\n{text}\n\n" if text else ''

        if name == 'br':
            return '  \n'
        if name == 'hr':
            # Skip <hr> inside <li> (would produce "- ---" glued to next item).
            if node.find_parent('li'):
                return ''
            return '\n\n---\n\n'

        if name == 'blockquote':
            inner = cls._render_children(node, list_indent).strip()
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
            return cls._render_list(node, list_indent)

        if name == 'dl':
            parts = []
            for child in node.children:
                if isinstance(child, Tag):
                    inner = cls._inline(child).strip()
                    if not inner:
                        continue
                    if child.name == 'dt':
                        parts.append(f"\n**{inner}**")
                    elif child.name == 'dd':
                        parts.append(f"\n: {inner}")
            return '\n\n' + ''.join(parts).strip() + '\n\n' if parts else ''

        if name == 'table':
            return cls._render_table(node)

        if name in ('strong', 'b'):
            inner = cls._inline(node).strip()
            return f"**{inner}**" if inner else ''
        if name in ('em', 'i'):
            inner = cls._inline(node).strip()
            return f"*{inner}*" if inner else ''
        if name in ('s', 'del'):
            inner = cls._inline(node).strip()
            return f"~~{inner}~~" if inner else ''
        if name == 'u':
            inner = cls._inline(node).strip()
            return f"__{inner}__" if inner else ''
        if name == 'mark':
            inner = cls._inline(node).strip()
            return f"=={inner}==" if inner else ''
        if name in ('kbd', 'samp', 'var'):
            inner = cls._inline(node).strip()
            return f"`{inner}`" if inner else ''

        if name in cls._BLOCK_WRAPPERS:
            inner = cls._render_children(node, list_indent).strip()
            return f"\n{inner}\n" if inner else ''

        # Passthrough (span, a, …): keep text, drop URL.
        return cls._render_children(node, list_indent)

    @classmethod
    def _render_children(cls, node, list_indent: int) -> str:
        return ''.join(cls._render(c, list_indent) for c in node.children)

    @classmethod
    def _inline(cls, node) -> str:
        """Render inline content only (for headings, paragraphs, cells)."""
        from bs4 import NavigableString, Tag
        out = ''
        for child in node.children:
            if isinstance(child, NavigableString):
                text = re.sub(r'\s+', ' ', str(child))
            elif isinstance(child, Tag) and child.name not in cls._SKIP_TAGS:
                text = cls._render(child, 0)
            else:
                continue
            if text:
                out += text
        out = re.sub(r'[ \t]+', ' ', out)
        out = re.sub(r' *\n *', '\n', out)
        return out.strip()

    @classmethod
    def _render_list(cls, node, list_indent: int) -> str:
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
                flattened = cls._render_children(child, list_indent).strip()
                if flattened:
                    items.append(flattened)
                continue

            marker = f'{idx}.' if is_ordered else '-'
            content = cls._render_children(child, list_indent + 1).strip()
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
    def _render_table(cls, table) -> str:
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
                txt = cls._inline(cell).replace('|', '\\|').replace('\n', ' ').strip()
                cells.append(txt or ' ')
                for _ in range(colspan - 1):
                    cells.append(' ')
            if cells:
                rows.append(cells)

        if not rows:
            return ''

        ncols = max(len(r) for r in rows)
        rows = [r + [' '] * (ncols - len(r)) for r in rows]

        lines = ['| ' + ' | '.join(rows[0]) + ' |']
        lines.append('|' + '|'.join([' --- '] * ncols) + '|')
        for r in rows[1:]:
            lines.append('| ' + ' | '.join(r) + ' |')

        return '\n\n' + '\n'.join(lines) + '\n\n'
