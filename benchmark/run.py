#!/usr/bin/env python3
"""Comparative benchmark: RDTextract vs trafilatura, markdownify, html2text.

Reads HTML files from `cache/` (populated by `fetch.py`), runs each extractor
with timing, scores quality, counts artifacts. Prints a comparative report.

Quality score (0-100): penalises empty output, link dump, double-bullet,
duplicated paragraphs, low FR-stopword ratio, missing headers.

Usage:
  python benchmark/run.py
"""

import re
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import trafilatura
import markdownify
import html2text

import rdtextract

CACHE_DIR = Path(__file__).parent / 'cache'

FR_TYPICAL = {'le', 'la', 'les', 'de', 'des', 'du', 'un', 'une', 'et', 'à', 'a', 'est', 'sont',
              'pour', 'que', 'qui', 'dans', 'sur', 'avec', 'par', 'au', 'aux', 'ce', 'cette',
              'ces', 'son', 'sa', 'ses', 'mais', 'ou', 'comme', 'plus', 'pas', 'vous', 'nous'}

LEGIT_EMPTY_THRESHOLD = 1500


# ── Adapters ──────────────────────────────────────────────────────────────────

def extract_trafilatura(html: str) -> str:
    return trafilatura.extract(html, output_format='markdown', include_links=False,
                               include_images=False, include_tables=True) or ''


def extract_markdownify(html: str) -> str:
    return markdownify.markdownify(html, strip=['script', 'style'])


def extract_html2text(html: str) -> str:
    h = html2text.HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    h.body_width = 0
    return h.handle(html)


def extract_ours(html: str) -> str:
    return rdtextract.extract(html)


EXTRACTORS = {
    'trafilatura': extract_trafilatura,
    'markdownify': extract_markdownify,
    'html2text':   extract_html2text,
    'rdtextract':  extract_ours,
}


# ── Quality scoring ───────────────────────────────────────────────────────────

def fr_word_ratio(text: str) -> float:
    words = re.findall(r'\b[a-zàâäéèêëïîôöùûüÿç]+\b', text.lower())[:500]
    if not words:
        return 0.0
    return sum(1 for w in words if w in FR_TYPICAL) / len(words)


def quality_score(text: str) -> float:
    if not text or not text.strip():
        return 0.0
    score = 100.0
    lines = text.split('\n')
    n = len(lines)

    empty = sum(1 for l in lines if not l.strip())
    if n > 10 and empty / n > 0.5:
        score -= 15

    links = sum(1 for l in lines if l.strip().startswith('http'))
    if n > 10 and links / n > 0.3:
        score -= 15

    if len(re.findall(r'\n- -(?!\d+\s*%)[ \w]', text)) >= 3:
        score -= 10

    paras = [p.strip() for p in re.split(r'\n{2,}', text) if len(p.strip()) >= 50]
    if paras:
        c = Counter(paras)
        if any(n >= 3 for n in c.values()):
            score -= 10

    if len(text) > 500 and fr_word_ratio(text) < 0.05:
        score -= 15

    if len(text) > 1000 and not re.search(r'(?:^|\n)#{1,6} ', text):
        score -= 10

    return max(0.0, score)


def count_artifacts(text: str) -> dict:
    return {
        'double_bullet':   len(re.findall(r'\n- -(?!\d+\s*%)[ \w]', text)),
        'orphan_punct':    len(re.findall(r'^[ \t]*[-.>·][ \t]*$', text, re.MULTILINE)),
        'http_dump_lines': sum(1 for l in text.split('\n') if l.strip().startswith('http')),
        'empty_para_dup':  sum(n - 1 for n in Counter(
            p.strip() for p in re.split(r'\n{2,}', text) if len(p.strip()) >= 50
        ).values() if n >= 3),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    files = sorted(CACHE_DIR.glob('*.html'))
    if not files:
        print(f'No HTML in {CACHE_DIR}. Run `python benchmark/fetch.py` first.')
        return 1

    print('=' * 78)
    print(f'BENCHMARK — {len(files)} pages, {len(EXTRACTORS)} extractors')
    print('=' * 78)

    results = {name: {'sizes': [], 'times_ms': [], 'scores': [], 'scores_corrected': [],
                      'artifacts': Counter(), 'errors': 0, 'empty_outputs': 0,
                      'legit_empty': 0} for name in EXTRACTORS}

    n_ok = 0
    for i, path in enumerate(files, 1):
        try:
            html = path.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        if len(html) < 500:
            continue
        n_ok += 1

        page_outputs = {}
        for name, fn in EXTRACTORS.items():
            try:
                t0 = time.perf_counter()
                out = fn(html) or ''
                elapsed_ms = (time.perf_counter() - t0) * 1000
                page_outputs[name] = (out, elapsed_ms, quality_score(out))
            except Exception as e:
                results[name]['errors'] += 1
                page_outputs[name] = None
                print(f'  [err {name}] {type(e).__name__}: {e}')

        # "Legit empty" iff trafilatura (curatorial peer) also returned tiny output
        traf_payload = page_outputs.get('trafilatura')
        traf_size = len(traf_payload[0]) if traf_payload is not None else 0
        page_is_legit_empty = traf_size < LEGIT_EMPTY_THRESHOLD

        for name, payload in page_outputs.items():
            if payload is None:
                continue
            out, elapsed_ms, qs = payload
            r = results[name]
            r['sizes'].append(len(out))
            r['times_ms'].append(elapsed_ms)
            r['scores'].append(qs)
            if not out.strip():
                r['empty_outputs'] += 1
                if page_is_legit_empty:
                    r['legit_empty'] += 1
                else:
                    r['scores_corrected'].append(qs)
            else:
                r['scores_corrected'].append(qs)
                arts = count_artifacts(out)
                for k, v in arts.items():
                    r['artifacts'][k] += v

    # ── Report ────────────────────────────────────────────────────────────
    print()
    print('=' * 78)
    print(f'RESULTS ({n_ok} pages processed)')
    print('=' * 78)
    print(f'\n{"Extractor":<14} {"Avg size":>10} {"Speed":>10} {"Quality":>9} {"Q.corr":>8} {"Empty":>6} {"Legit":>6} {"Err":>4}')
    print('-' * 78)
    for name in EXTRACTORS:
        r = results[name]
        if not r['sizes']:
            continue
        avg_size = statistics.mean(r['sizes'])
        avg_time = statistics.mean(r['times_ms'])
        avg_score = statistics.mean(r['scores'])
        avg_corr = statistics.mean(r['scores_corrected']) if r['scores_corrected'] else 0.0
        print(f'{name:<14} {avg_size:>10,.0f} {avg_time:>8.1f}ms {avg_score:>8.1f} {avg_corr:>8.1f} {r["empty_outputs"]:>6} {r["legit_empty"]:>6} {r["errors"]:>4}')

    print('\nLegend:')
    print('  Quality  = mean (empties counted as 0)')
    print('  Q.corr   = mean excluding "legit empty" pages (where trafilatura also returned <1500c)')
    print('  Legit    = empties classified as legitimate (page has no extractable server content)')

    print(f'\n{"Extractor":<14} {"double_bullet":>14} {"orphan_punct":>13} {"http_dump":>10} {"para_dup":>9}')
    print('-' * 78)
    for name in EXTRACTORS:
        a = results[name]['artifacts']
        print(f'{name:<14} {a["double_bullet"]:>14} {a["orphan_punct"]:>13} {a["http_dump_lines"]:>10} {a["empty_para_dup"]:>9}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
