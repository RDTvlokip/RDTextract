# RDTextract benchmark

Comparative benchmark of `rdtextract` against `trafilatura`, `markdownify`, `html2text`
on the **Tranco top-100 .fr** homepages.

## Reproduce

```bash
pip install -e ".[benchmark]"          # install rdtextract + benchmark deps
python benchmark/fetch.py --top 100    # download Tranco list, fetch HTML to cache/
python benchmark/run.py                # run extractors, print comparative table
```

## Methodology

- **Domain selection**: Tranco top-1M (https://tranco-list.eu/), filtered to first 100
  `.fr` domains. Tranco aggregates Alexa/Cisco/Majestic/Quantcast over 30 days for stability.
  The filtered list is committed to `tranco_top_fr.txt` for bit-exact reproducibility.
- **Pages**: homepage of each domain (`https://<domain>/`).
- **Cache**: HTML files in `cache/` (.gitignored — re-fetched on first run).
- **Quality score** (0-100): inspired by an audit of a 1M+ page corpus. Penalties:
  empty output, link dump, double-bullet, duplicated paragraphs ≥3×, low FR-stopword
  ratio, missing headers on long pages.
- **"Legit empty"**: a page where trafilatura (the closest curatorial peer) also
  returned <1500c — i.e. the page has no extractable server content (SPA/React,
  body filled by JS). These are excluded from the corrected score (`Q.corr`).

## Why Tranco?

Reproducibility. Tranco is the academically-cited replacement for Alexa: stable,
versioned, free, and resistant to manipulation. Every benchmark run on the same
date produces the same list.
