#!/usr/bin/env python3
"""Find pages where rdtextract emits `\n- -` patterns (double_bullet artifact).

For each match, show:
- the cache filename
- the surrounding markdown context
- the HTML snippet around the offending <li> (best-effort)
"""

import re
from pathlib import Path
import rdtextract

CACHE = Path(__file__).parent / 'cache'
PATTERN = re.compile(r'\n- -[ \w]')


def find_html_context(html: str, marker_text: str, ctx: int = 200) -> str:
    """Try to find marker_text in html and return surrounding bytes."""
    # Marker is the few words after `- -`. Strip markdown noise.
    needle = marker_text.strip().split('\n')[0][:30]
    needle = re.sub(r'[^\w ]', '', needle).strip()
    if not needle or len(needle) < 4:
        return '(no usable needle)'
    idx = html.lower().find(needle.lower())
    if idx < 0:
        return f'(needle not found: {needle!r})'
    start = max(0, idx - ctx)
    end = min(len(html), idx + len(needle) + ctx)
    return html[start:end]


def main():
    files = sorted(CACHE.glob('*.html'))
    hits = []
    for path in files:
        try:
            html = path.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        if len(html) < 500:
            continue
        md = rdtextract.extract(html)
        for m in PATTERN.finditer(md):
            start = max(0, m.start() - 80)
            end = min(len(md), m.end() + 200)
            snippet = md[start:end]
            hits.append((path.name, snippet, m.group(0), html))

    print(f'{len(hits)} double_bullet occurrences across {len(set(h[0] for h in hits))} pages\n')
    seen_pages = set()
    for fname, snippet, match, html in hits:
        if fname in seen_pages:
            continue
        seen_pages.add(fname)
        print('=' * 80)
        print(f'FILE: {fname}')
        print('--- MARKDOWN context ---')
        print(snippet)
        # Get text after `- -` to use as needle
        after = snippet[snippet.find('- -') + 3:].strip()[:50]
        print('--- HTML context ---')
        print(find_html_context(html, after))
        print()


if __name__ == '__main__':
    main()
