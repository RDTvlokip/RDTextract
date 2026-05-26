#!/usr/bin/env python3
"""Fetch step for the RDTextract benchmark.

1. Download the latest Tranco top-1M list (https://tranco-list.eu/), pick the
   first N .fr domains for a stable, reproducible French web sample.
2. Cache the filtered list to `tranco_top_fr.txt` (commitable).
3. Fetch the homepage of each domain into `cache/<sha>.html`.

The cache is .gitignored — re-running on a fresh clone re-fetches everything,
which is slow but bit-exact reproducible because the domain list is committed.

Usage:
  python benchmark/fetch.py --top 100
  python benchmark/fetch.py --top 100 --refresh-list   # re-download Tranco
"""

import argparse
import hashlib
import io
import os
import ssl
import sys
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

DEFAULT_WORKERS = max(1, (os.cpu_count() or 2) - 1)

TRANCO_URL = 'https://tranco-list.eu/top-1m.csv.zip'
ROOT = Path(__file__).parent
LIST_PATH = ROOT / 'tranco_top_fr.txt'
CACHE_DIR = ROOT / 'cache'
USER_AGENT = 'Mozilla/5.0 (compatible; RDTextract-Benchmark/0.1; +https://github.com/RDTvlokip/RDTextract)'
TIMEOUT = 20


def download_tranco_fr(top: int) -> list[str]:
    """Download Tranco top-1M, keep first `top` domains ending in .fr."""
    print(f'Downloading Tranco list from {TRANCO_URL} …')
    req = urllib.request.Request(TRANCO_URL, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    print(f'  {len(data) / 1024:.0f} KB downloaded.')

    fr_domains: list[str] = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        name = next(n for n in zf.namelist() if n.endswith('.csv'))
        with zf.open(name) as f:
            for raw in f:
                line = raw.decode('utf-8', errors='ignore').strip()
                if not line:
                    continue
                _, domain = line.split(',', 1)
                if domain.endswith('.fr'):
                    fr_domains.append(domain)
                    if len(fr_domains) >= top:
                        break
    print(f'  Selected {len(fr_domains)} .fr domains.')
    return fr_domains


def load_or_fetch_list(top: int, refresh: bool) -> list[str]:
    if LIST_PATH.exists() and not refresh:
        domains = [d for d in LIST_PATH.read_text(encoding='utf-8').splitlines() if d.strip()]
        if len(domains) >= top:
            print(f'Using cached domain list: {LIST_PATH} ({len(domains)} domains).')
            return domains[:top]
    domains = download_tranco_fr(top)
    LIST_PATH.write_text('\n'.join(domains) + '\n', encoding='utf-8')
    print(f'Wrote {LIST_PATH}.')
    return domains


def fetch_html(url: str) -> tuple[bytes | None, str]:
    """Fetch URL, return (bytes_or_none, error_msg). Thread-safe."""
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            return resp.read(), ''
    except Exception as e:
        return None, f'{type(e).__name__}: {e}'


def _fetch_one(domain: str, refresh_html: bool) -> tuple[str, str, int]:
    """Worker: fetch one domain, write to cache. Returns (domain, status, size)."""
    url = f'https://{domain}/'
    key = hashlib.sha256(url.encode()).hexdigest()[:16]
    path = CACHE_DIR / f'{key}.html'
    if path.exists() and not refresh_html:
        return domain, 'skip', path.stat().st_size

    t0 = time.perf_counter()
    raw, err = fetch_html(url)
    elapsed = time.perf_counter() - t0
    if raw is None:
        return domain, f'err {err[:60]} ({elapsed:.1f}s)', 0
    try:
        html = raw.decode('utf-8')
    except UnicodeDecodeError:
        html = raw.decode('latin-1', errors='replace')
    path.write_text(html, encoding='utf-8')
    return domain, f'ok ({elapsed:.1f}s)', len(html)


def main():
    ap = argparse.ArgumentParser(description='Fetch Tranco top-N .fr homepages for benchmark.')
    ap.add_argument('--top', type=int, default=100, help='Number of .fr domains to fetch')
    ap.add_argument('--workers', type=int, default=DEFAULT_WORKERS,
                    help=f'Parallel fetch workers (default {DEFAULT_WORKERS} = cpu_count-1)')
    ap.add_argument('--refresh-list', action='store_true', help='Re-download Tranco list')
    ap.add_argument('--refresh-html', action='store_true', help='Re-fetch HTML even if cached')
    args = ap.parse_args()

    domains = load_or_fetch_list(args.top, args.refresh_list)
    CACHE_DIR.mkdir(exist_ok=True)

    print(f'\nFetching {len(domains)} domains with {args.workers} workers …\n')
    counts = {'ok': 0, 'skip': 0, 'err': 0}
    counts_lock = Lock()
    t_start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(_fetch_one, d, args.refresh_html): d for d in domains}
        for i, fut in enumerate(as_completed(futures), 1):
            domain, status, size = fut.result()
            kind = 'ok' if status.startswith('ok') else ('skip' if status == 'skip' else 'err')
            with counts_lock:
                counts[kind] += 1
            if i % 25 == 0 or kind == 'err':
                rate = i / (time.perf_counter() - t_start)
                eta = (len(domains) - i) / rate if rate else 0
                print(f'  [{i:>4}/{len(domains)}] {domain:<40} {status:<35} '
                      f'({size/1024:>6.1f}KB)  rate={rate:.1f}/s eta={eta/60:.1f}min')

    elapsed = time.perf_counter() - t_start
    total_files = len(list(CACHE_DIR.glob('*.html')))
    print(f'\nDone in {elapsed/60:.1f}min. ok={counts["ok"]} skip={counts["skip"]} err={counts["err"]} '
          f'total_cache={total_files}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
