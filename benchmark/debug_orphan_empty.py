#!/usr/bin/env python3
"""Find: (1) the page producing the 1 remaining orphan_punct line,
        (2) all empty-output pages (split legit vs non-legit)."""

import re
from pathlib import Path
import trafilatura
import rdtextract

CACHE = Path(__file__).parent / 'cache'
LEGIT = 500
ORPHAN = re.compile(r'^[ \t]*[-.>·][ \t]*$', re.MULTILINE)


def main():
    orphan_hits, empties = [], []
    for path in sorted(CACHE.glob('*.html')):
        try:
            html = path.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        if len(html) < 500:
            continue
        md = rdtextract.extract(html)

        for m in ORPHAN.finditer(md):
            s, e = max(0, m.start() - 80), min(len(md), m.end() + 80)
            orphan_hits.append((path.name, md[s:e], m.group(0)))

        if not md.strip():
            traf = trafilatura.extract(html, output_format='markdown') or ''
            empties.append((path.name, len(traf), len(html)))

    print(f'\n=== ORPHAN_PUNCT: {len(orphan_hits)} ===')
    for fname, ctx, match in orphan_hits:
        print(f'\n{fname}  matched={match!r}')
        print(ctx.encode('ascii', 'replace').decode())

    legit = [e for e in empties if e[1] < LEGIT]
    nonleg = [e for e in empties if e[1] >= LEGIT]
    print(f'\n=== EMPTIES: {len(empties)} total, {len(legit)} legit, {len(nonleg)} non-legit ===')
    print('\n-- LEGIT (trafilatura also empty) --')
    for f, t, h in legit:
        print(f'  {f}  traf={t:>5}c  html={h:>7}c')
    print('\n-- NON-LEGIT (trafilatura has content, we do not) --')
    for f, t, h in nonleg:
        print(f'  {f}  traf={t:>5}c  html={h:>7}c')


if __name__ == '__main__':
    main()
