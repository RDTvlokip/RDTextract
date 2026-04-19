#!/usr/bin/env python3
"""Diagnose the three residual issue categories in the top-1000 .fr benchmark.

1. http_dump   — pages where rdtextract emits raw `http...` lines
2. double_bullet — remaining `\\n- - X` patterns (post-fix)
3. non-legit empties — rdtextract returns '' but trafilatura returns >=500c
"""

import re
from pathlib import Path

import trafilatura
import rdtextract

CACHE = Path(__file__).parent / 'cache'
LEGIT_EMPTY = 500


def main():
    files = sorted(CACHE.glob('*.html'))
    http_hits, db_hits, empty_hits = [], [], []

    for path in files:
        try:
            html = path.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        if len(html) < 500:
            continue

        md = rdtextract.extract(html)

        # 1. http dump
        http_lines = [l for l in md.split('\n') if l.strip().startswith('http')]
        if http_lines:
            http_hits.append((path.name, http_lines[:3], len(http_lines)))

        # 2. double bullet
        for m in re.finditer(r'\n- -[ \w]', md):
            s = max(0, m.start() - 60)
            e = min(len(md), m.end() + 120)
            db_hits.append((path.name, md[s:e]))

        # 3. non-legit empty
        if not md.strip():
            traf = trafilatura.extract(html, output_format='markdown') or ''
            if len(traf) >= LEGIT_EMPTY:
                empty_hits.append((path.name, len(traf), traf[:300]))

    print(f'\n{"="*78}\n[1] HTTP DUMP — {len(http_hits)} pages\n{"="*78}')
    for fname, sample, n in http_hits:
        print(f'\n{fname}  ({n} http lines)')
        for l in sample:
            print(f'  {l[:150]}')

    print(f'\n{"="*78}\n[2] DOUBLE BULLET — {len(db_hits)} occurrences\n{"="*78}')
    seen = set()
    for fname, snippet in db_hits:
        if fname in seen:
            continue
        seen.add(fname)
        print(f'\n{fname}')
        print(snippet)

    print(f'\n{"="*78}\n[3] NON-LEGIT EMPTIES — {len(empty_hits)} pages\n{"="*78}')
    for fname, traf_size, head in empty_hits:
        print(f'\n{fname}  (trafilatura={traf_size}c)')
        print(head.replace('\n', ' / ')[:250])


if __name__ == '__main__':
    main()
