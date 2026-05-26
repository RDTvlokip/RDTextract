#!/usr/bin/env python3
"""Identifie les pages où RDTextract a un comportement suspect, pour review humaine.

Détecte 5 catégories :
1. EMPTY_LARGE   : HTML > 50 KB mais markdown < 500 c (extraction quasi-vide)
2. TINY_RATIO    : ratio md/html < 0.5% (compression anormalement forte)
3. HUGE_RATIO    : ratio md/html > 30% (markdown bizarrement long)
4. ARTIFACTS     : double-bullet, orphan punct, http dump ou para dup détecté
5. SPA_NO_FALLBACK : body vide ET fallback JSON-LD/meta a échoué

Pour chaque outlier, sauve dans `outliers/<category>/` :
- {hash}.html  (source HTML)
- {hash}.md    (sortie RDTextract)
- {hash}.txt   (méta : URL si dispo, raison du flag, taille, lignes)

Usage:
  python benchmark/find_outliers.py
  python benchmark/find_outliers.py --max-per-category 50
  python benchmark/find_outliers.py --output /tmp/outliers
"""

import argparse
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

# Windows console = cp1252 par défaut → reconfigure en UTF-8 pour les caractères
# unicode (→, séparateurs, etc.) dans les print finaux.
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import rdtextract

CACHE_DIR = Path(__file__).parent / 'cache'
DEFAULT_OUTPUT = Path(__file__).parent / 'outliers'

# Mêmes regex que run.py (pour cohérence) — sauf double_bullet qui utilise un
# look-ahead pour exclure les promos -15%/-40% (faux positifs WordPress).
_RX_DOUBLE_BULLET = re.compile(r'\n- -(?!\d+\s*[%€$£])[ \w]')
_RX_ORPHAN_PUNCT  = re.compile(r'^[ \t]*[-.>·][ \t]*$', re.MULTILINE)
_RX_HTTP_LINE     = re.compile(r'^https?://', re.MULTILINE)


def classify(html: str, md: str) -> list[tuple[str, str]]:
    """Renvoie une liste de (catégorie, raison) pour cette page. Vide = OK."""
    flags = []
    h_len, m_len = len(html), len(md)
    ratio = m_len / max(1, h_len)

    if h_len > 50_000 and m_len < 500:
        flags.append(('EMPTY_LARGE', f'html={h_len/1024:.0f}KB, md={m_len}c'))

    if h_len > 5_000 and ratio < 0.005:
        flags.append(('TINY_RATIO', f'md/html={ratio*100:.2f}% (md={m_len}c)'))

    # HUGE_RATIO : seulement si le ratio est anormalement élevé ET le markdown est
    # exceptionnellement gros — sinon c'est juste du contenu dense bien extrait.
    if ratio > 0.50 and m_len > 50_000:
        flags.append(('HUGE_RATIO', f'md/html={ratio*100:.0f}% (md={m_len/1024:.0f}KB)'))

    db = len(_RX_DOUBLE_BULLET.findall(md))
    op = len(_RX_ORPHAN_PUNCT.findall(md))
    hp = len(_RX_HTTP_LINE.findall(md))
    paras = [p.strip() for p in re.split(r'\n{2,}', md) if len(p.strip()) >= 50]
    pd = sum(n - 1 for n in Counter(paras).values() if n >= 3)
    if db or op or hp or pd:
        flags.append(('ARTIFACTS', f'double_bullet={db} orphan={op} http={hp} para_dup={pd}'))

    # SPA detection : html contient marqueurs SPA + md vide
    if not md.strip() and any(s in html for s in (
        'id="__next"', 'id="root"', 'data-reactroot', 'ng-version', 'data-server-rendered'
    )):
        flags.append(('SPA_NO_FALLBACK', 'SPA marker present, fallback failed'))

    return flags


def main():
    ap = argparse.ArgumentParser(description='Find suspicious extraction outliers for human review.')
    ap.add_argument('--cache', default=str(CACHE_DIR), help='HTML cache directory')
    ap.add_argument('--output', default=str(DEFAULT_OUTPUT), help='Output dir for outliers')
    ap.add_argument('--max-per-category', type=int, default=20,
                    help='Max samples to save per category (default 20)')
    ap.add_argument('--clean', action='store_true', help='Wipe output dir before run')
    args = ap.parse_args()

    cache = Path(args.cache)
    out = Path(args.output)
    if args.clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    files = sorted(cache.glob('*.html'))
    if not files:
        print(f'No HTML files in {cache}. Run `python benchmark/fetch.py` first.')
        return 1

    print(f'Scanning {len(files)} pages …')
    counts = Counter()
    saved = Counter()
    examples = {}  # category → list of (fname, reasons, html, md)

    for i, path in enumerate(files, 1):
        try:
            html = path.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        if len(html) < 500:
            continue

        try:
            md = rdtextract.extract(html)
        except Exception as e:
            print(f'  [extract err] {path.name}: {e}')
            continue

        flags = classify(html, md)
        for cat, _ in flags:
            counts[cat] += 1

        for cat, reason in flags:
            if saved[cat] >= args.max_per_category:
                continue
            cat_dir = out / cat
            cat_dir.mkdir(exist_ok=True)
            stem = path.stem
            (cat_dir / f'{stem}.html').write_text(html, encoding='utf-8')
            (cat_dir / f'{stem}.md').write_text(md, encoding='utf-8')
            (cat_dir / f'{stem}.txt').write_text(
                f'category : {cat}\nreason   : {reason}\n'
                f'cache    : {path.name}\n'
                f'html_len : {len(html)} ({len(html)/1024:.1f} KB)\n'
                f'md_len   : {len(md)} ({len(md)/1024:.1f} KB)\n'
                f'md_lines : {len(md.splitlines())}\n',
                encoding='utf-8'
            )
            saved[cat] += 1

        if i % 100 == 0:
            print(f'  [{i}/{len(files)}] flagged so far: {dict(counts)}')

    print(f'\n{"="*60}\nResults\n{"="*60}')
    if not counts:
        print('No outliers detected. RDTextract handled all pages cleanly.')
        return 0

    for cat in ('EMPTY_LARGE', 'TINY_RATIO', 'HUGE_RATIO', 'ARTIFACTS', 'SPA_NO_FALLBACK'):
        if counts[cat]:
            print(f'  {cat:<18} {counts[cat]:>5} pages  →  saved {saved[cat]} samples in {out / cat}/')

    print(f'\nReview the .html + .md side-by-side for patterns:')
    print(f'  cd {out}')
    print(f'  ls EMPTY_LARGE/    # à inspecter en premier (cas à faible coût d\'amélioration)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
