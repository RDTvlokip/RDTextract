#!/usr/bin/env python3
"""Diagnose Q.corr drop 98.3 → 97.8 between v0.1.1 and v0.2.0.

Compare per-page outputs with lxml vs html.parser to isolate parser regressions
from feature regressions (layout-table fix, JSON-LD fallback)."""

from pathlib import Path
import rdtextract

CACHE = Path(__file__).parent / 'cache'

# Force re-extract with both parsers
def extract_with(parser: str, html: str) -> str:
    rdtextract.PARSER = parser
    return rdtextract.extract(html)


def main():
    files = sorted(CACHE.glob('*.html'))
    diffs = []  # (fname, len_lxml, len_htmlp)
    only_empty_in = {'lxml': [], 'htmlp': []}

    for path in files:
        try:
            html = path.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        if len(html) < 500:
            continue
        md_lxml = extract_with('lxml', html)
        md_htmlp = extract_with('html.parser', html)

        if not md_lxml.strip() and md_htmlp.strip():
            only_empty_in['lxml'].append((path.name, len(md_htmlp)))
        elif md_lxml.strip() and not md_htmlp.strip():
            only_empty_in['htmlp'].append((path.name, len(md_lxml)))
        elif md_lxml != md_htmlp:
            ratio = len(md_lxml) / max(1, len(md_htmlp))
            if abs(ratio - 1) > 0.05:  # >5% size diff
                diffs.append((path.name, len(md_lxml), len(md_htmlp), ratio))

    print(f'\nPages where ONLY lxml returns empty (lxml regression): {len(only_empty_in["lxml"])}')
    for fname, sz in only_empty_in['lxml'][:15]:
        print(f'  {fname}  htmlp={sz}c')
    print(f'\nPages where ONLY html.parser returns empty: {len(only_empty_in["htmlp"])}')
    for fname, sz in only_empty_in['htmlp'][:10]:
        print(f'  {fname}  lxml={sz}c')

    diffs.sort(key=lambda x: abs(x[3] - 1), reverse=True)
    print(f'\nTop 10 size differences (>5%):')
    for fname, l_lxml, l_htmlp, ratio in diffs[:10]:
        print(f'  {fname}  lxml={l_lxml:>6}  htmlp={l_htmlp:>6}  ratio={ratio:.2f}')


if __name__ == '__main__':
    main()
