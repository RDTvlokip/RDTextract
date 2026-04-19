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
import ssl
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

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


def fetch_html(url: str) -> bytes | None:
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            return resp.read()
    except Exception as e:
        print(f'  [skip] {url}: {type(e).__name__}: {e}')
        return None


def main():
    ap = argparse.ArgumentParser(description='Fetch Tranco top-N .fr homepages for benchmark.')
    ap.add_argument('--top', type=int, default=100, help='Number of .fr domains to fetch')
    ap.add_argument('--refresh-list', action='store_true', help='Re-download Tranco list')
    ap.add_argument('--refresh-html', action='store_true', help='Re-fetch HTML even if cached')
    args = ap.parse_args()

    domains = load_or_fetch_list(args.top, args.refresh_list)
    CACHE_DIR.mkdir(exist_ok=True)

    n_ok = n_skip = 0
    for i, domain in enumerate(domains, 1):
        url = f'https://{domain}/'
        key = hashlib.sha256(url.encode()).hexdigest()[:16]
        path = CACHE_DIR / f'{key}.html'
        if path.exists() and not args.refresh_html:
            n_skip += 1
            continue
        print(f'  [{i:3}/{len(domains)}] {url}')
        raw = fetch_html(url)
        if raw is None:
            continue
        try:
            html = raw.decode('utf-8')
        except UnicodeDecodeError:
            html = raw.decode('latin-1', errors='replace')
        path.write_text(html, encoding='utf-8')
        n_ok += 1
        time.sleep(0.3)  # be polite

    print(f'\nDone. Fetched: {n_ok}, cached (skipped): {n_skip}, total cache files: {len(list(CACHE_DIR.glob("*.html")))}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
