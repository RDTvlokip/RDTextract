# RDTextract

HTML→Markdown extractor built for **AI / LLM training corpora** — every byte should carry signal, not boilerplate.

> **Language scope (current):** filters, paywall markers, and the `is_low_value_stub()` heuristic are tuned for **French** content (the corpus this lib was extracted from is FR-only). Core extraction is language-agnostic and works on any language; only the stub detector is FR-specific. Multi-language support is on the roadmap.

- **Zero noise artifacts** — no double-bullets, no orphan punctuation, no link dumps, no widget repetition.
- **Integrated quality scoring** — `is_low_value_stub()` filters paywalls, login walls, skip-link stubs, empty pages.
- **Meta fallback** — degrades gracefully on SPA / React pages where the body is empty (extracts `<title>` + meta description instead of returning nothing).
- **One dependency**: `beautifulsoup4`.

## Install

```bash
pip install RDTextract
```

## Quick start

```python
import rdtextract

html = open("page.html", encoding="utf-8", errors="replace").read()

# One-shot
markdown = rdtextract.extract(html)

# Or two-step (re-use cleaned HTML for caching, debugging, etc.)
cleaned = rdtextract.clean_html(html)
markdown = rdtextract.to_markdown(cleaned)

# Filter low-value pages before writing to your corpus
if not rdtextract.is_low_value_stub(markdown):
    with open("page.md", "w", encoding="utf-8") as f:
        f.write(markdown)
    print(f"Saved {len(markdown)} chars to page.md")
else:
    print("Page is low-value (paywall/login/empty), skipped.")
```

> **Note** : PyPI distribution is `RDTextract`, Python module is `rdtextract` (PEP 8 lowercase).

## Why another HTML→Markdown lib?

Existing tools target *human readability* (newsletters, archive). `RDTextract` targets *LLM training data*: every byte should carry signal.

Benchmark on **Tranco top-1000 .fr** homepages (672 pages successfully fetched and processed), measured against a corpus quality scorer (lower artifact counts = cleaner output):

| Extractor       | Quality (corrected) | double-bullet | orphan punct | http dump | para dup |
|-----------------|---------------------|---------------|--------------|-----------|----------|
| **RDTextract**  | **98.3**            | **0**         | **0**        | **0**     | **0**    |
| html2text       | 96.2                | 1             | 148          | 70        | 2 373    |
| trafilatura     | 96.1                | 18            | 780          | 10        | 309      |
| markdownify     | 85.5                | 0             | 246          | 107       | 5 042    |

RDTextract wins on **quality** and on **all 4 artifact metrics** — zero artifacts on every counter. Reproducible: see [`benchmark/`](benchmark/) — domain list is committed (Tranco, deterministic), HTML cache is .gitignored.

Trade-off: RDTextract is **~3× slower than html2text** (filtering + walking + dedup) and filters more aggressively, so a handful of content-light landing pages return empty — by design.

## API

### `clean_html(html: str) -> str`
Strip nav/footer/scripts/ads/hidden elements. Drops responsive duplicates (mobile/desktop variants), icon font ligatures, role-based junk (`role=navigation`, `role=banner`, …).

### `to_markdown(cleaned_html: str) -> str`
Walk the cleaned tree and emit Markdown. Includes:
- Heading levels, lists (with sublist flattening), tables (colspan, nested), code blocks, blockquotes, definition lists.
- Post-processing: collapse whitespace, restore breadcrumb separators, dedup consecutive blocks, dedup global blocks (UI widgets repeated ≥3×).
- Meta fallback for SPA pages.

### `extract(html: str) -> str`
Convenience: `to_markdown(clean_html(html))`.

### `is_low_value_stub(markdown: str) -> bool`
True if the markdown is a paywall (FR markers), login stub, MediaWiki skip-link alone, or empty. Combined length + marker check (avoids false positives on real articles that happen to mention these phrases).

## License

MIT
