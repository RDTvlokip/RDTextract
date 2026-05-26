#!/usr/bin/env python3
"""Génère des outputs côte-à-côte des 4 extracteurs pour comparaison humaine.

Pour N pages aléatoires du cache, écrit dans `comparison/<page_hash>/` :
  - source.html      (HTML brut)
  - rdtextract.md    (notre lib)
  - trafilatura.md
  - html2text.md
  - markdownify.md
  - SUMMARY.txt      (tailles, indicateurs, méta)

Usage :
  python benchmark/compare_outputs.py
  python benchmark/compare_outputs.py --samples 20 --seed 42
"""

import argparse
import random
import shutil
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import rdtextract
import trafilatura
import markdownify
import html2text

CACHE = Path(__file__).parent / 'cache'
DEFAULT_OUTPUT = Path(__file__).parent / 'comparison'


def extract_all(html: str) -> dict:
    """Run all 4 extractors. Catch errors, return dict[name -> markdown]."""
    out = {}
    for name, fn in [
        ('rdtextract',  lambda h: rdtextract.extract(h)),
        ('trafilatura', lambda h: trafilatura.extract(h, output_format='markdown',
                                                      include_links=False, include_images=False,
                                                      include_tables=True) or ''),
        ('html2text',   lambda h: _html2text(h)),
        ('markdownify', lambda h: markdownify.markdownify(h, strip=['script', 'style'])),
    ]:
        try:
            out[name] = fn(html)
        except Exception as e:
            out[name] = f'<<ERR {type(e).__name__}: {e}>>'
    return out


def _html2text(h: str) -> str:
    t = html2text.HTML2Text()
    t.ignore_links = True
    t.ignore_images = True
    t.body_width = 0
    return t.handle(h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--samples', type=int, default=10, help='Pages à comparer (default 10)')
    ap.add_argument('--seed', type=int, default=42, help='Seed random pour reproductibilité')
    ap.add_argument('--output', default=str(DEFAULT_OUTPUT))
    ap.add_argument('--min-size', type=int, default=10_000,
                    help='Skip pages < N bytes HTML (default 10KB)')
    args = ap.parse_args()

    out_dir = Path(args.output)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    random.seed(args.seed)
    files = [p for p in sorted(CACHE.glob('*.html')) if p.stat().st_size >= args.min_size]
    if len(files) < args.samples:
        print(f'Only {len(files)} pages >= {args.min_size} bytes, taking all.')
        sample = files
    else:
        sample = random.sample(files, args.samples)

    print(f'Comparing {len(sample)} pages with 4 extractors → {out_dir}/')
    for i, path in enumerate(sample, 1):
        html = path.read_text(encoding='utf-8', errors='replace')
        outputs = extract_all(html)

        page_dir = out_dir / path.stem
        page_dir.mkdir()

        # Source
        (page_dir / 'source.html').write_text(html, encoding='utf-8')

        # Outputs
        for name, md in outputs.items():
            (page_dir / f'{name}.md').write_text(md, encoding='utf-8')

        # Summary
        sizes = {n: len(m) for n, m in outputs.items()}
        sorted_by_size = sorted(sizes.items(), key=lambda x: -x[1])
        winner = sorted_by_size[0][0] if sorted_by_size[0][1] > 0 else '(all empty)'
        summary = (
            f'Page    : {path.name}\n'
            f'HTML    : {len(html):>7} c ({len(html)/1024:.1f} KB)\n\n'
            f'Outputs (sorted by size):\n'
        )
        for name, sz in sorted_by_size:
            bar = '█' * min(40, sz // 200)
            summary += f'  {name:<12} {sz:>7} c  {bar}\n'
        summary += f'\nLargest output: {winner}\n'
        (page_dir / 'SUMMARY.txt').write_text(summary, encoding='utf-8')

        print(f'  [{i:>2}/{len(sample)}] {path.name}  '
              + ' '.join(f'{n}={sz}' for n, sz in sizes.items()))

    print(f'\nDone. Open the comparison/ folder, then for each page :')
    print(f'  - Read SUMMARY.txt for sizes')
    print(f'  - Open source.html in browser to see the original page')
    print(f'  - Open the 4 .md files side-by-side (VSCode multi-tab) to compare')
    return 0


if __name__ == '__main__':
    sys.exit(main())
