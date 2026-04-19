#!/usr/bin/env python3
"""Trace pipeline for non-legit empty pages: which step kills the content?"""

from pathlib import Path
from bs4 import BeautifulSoup
import rdtextract
from rdtextract.converter import MarkdownConverter as MC

CACHE = Path(__file__).parent / 'cache'

# Picks: small file (5e027523, 1052c traf vs 3KB html), big landing (32b0f4 garde-enfant)
TARGETS = ['5e027523743e9b9d.html', '32b0f4371bc1b950.html', '2afe1638e0189636.html']


def main():
    for fname in TARGETS:
        path = CACHE / fname
        html = path.read_text(encoding='utf-8', errors='replace')
        cleaned = rdtextract.clean_html(html)
        soup = BeautifulSoup(cleaned, 'html.parser')
        root = soup.find('body') or soup
        raw = MC._render(root, list_indent=0)
        final = rdtextract.to_markdown(cleaned)

        print('=' * 78)
        print(f'{fname}  html={len(html)}c  cleaned={len(cleaned)}c  raw_render={len(raw.strip())}c  final={len(final)}c')
        print('-- cleaned head --')
        print(cleaned[:600].replace('\n', ' / '))
        print('-- raw render (first 400c) --')
        print(repr(raw.strip()[:400]))
        print()


if __name__ == '__main__':
    main()
