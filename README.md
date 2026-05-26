# RDTextract

[![PyPI](https://img.shields.io/pypi/v/RDTextract)](https://pypi.org/project/RDTextract/)
[![Python](https://img.shields.io/pypi/pyversions/RDTextract)](https://pypi.org/project/RDTextract/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

HTML→Markdown extractor built for **AI / LLM training corpora** — every byte should carry signal, not boilerplate.

> **Language scope:** core extraction is **language-agnostic** and works on any language. The `is_low_value_stub()` heuristic (paywall / login / skip-link detection) supports **French, English, Spanish, German, Italian** out of the box. The library was originally built for a French corpus, so FR is the most battle-tested.

- **Zero noise artifacts** — no double-bullets, no orphan punctuation, no link dumps, no widget repetition (validated on 672 real `.fr` pages).
- **Smart fallback chain** — JSON-LD structured data (Recipe, Article, FAQ, HowTo, Product) → `<title>` + meta description, for SPA / React / Next.js pages with empty bodies.
- **Robust against malformed HTML** — auto-detects and recovers from unclosed tags, gzip leaks, and CMS quirks (Drupal, WordPress Elementor, React 18 SSR Suspense, etc.).
- **Multi-language stub detection** — paywall / login / skip-link markers in FR / EN / ES / DE / IT.
- **`is_low_value_stub()`** filter for paywalls, login walls, skip-link stubs, empty pages.
- **One required dependency**: `beautifulsoup4`. Optional `[fast]` extra adds `lxml` for 2-3× speed.

## What's new in v0.2.0

Major release with substantial gains across every metric measured on the **Tranco top-1000 .fr** benchmark (672 pages):

| Metric                  | v0.1.x | **v0.2.0** | Δ          |
|-------------------------|--------|------------|------------|
| Quality (corrected)     | 98.3   | **99.3**   | **+1.0**   |
| Avg markdown size       | 5 538c | **6 875c** | **+24%**   |
| Speed (with `lxml`)     | 152ms  | **107ms**  | **-30%**   |
| Empty pages             | 39     | **21**     | **-46%**   |
| Recoverable empty pages | 14     | **0**      | **-100%**  |
| Total artifacts         | 9      | **0**      | **-100%**  |

**New features**:
- **`[fast]` extra** — opt-in `lxml` backend for 2-3× faster parsing, with automatic fallback to `html.parser` on malformed HTML.
- **JSON-LD fallback** — Schema.org structured data (Article, NewsArticle, BlogPosting, Recipe, FAQPage, HowTo, Product, with `@graph` wrapper) extracted when the body is empty.
- **Multi-language stub detection** — `is_low_value_stub(md, language="en")` supports `fr`, `en`, `es`, `de`, `it` (paywall, login, skip-link markers).
- **`PARSER` constant** — module-level value exposing the active parser (`'lxml'` or `'html.parser'`).

**Robustness fixes** (no regression, all gains):
- React 18 SSR Suspense boundaries (`<div hidden>` with content) preserved.
- WordPress Elementor pages no longer destroyed by `widget` pattern over-match.
- Drupal pages with malformed `<header>` wrappers now extract the real content.
- Layout-tables (image + caption WordPress) collapsed cleanly to paragraphs.
- Gzipped HTML leaks (corrupted fetcher) detected → empty output instead of mojibake.

**Tooling**:
- New `benchmark/find_outliers.py` — classifies suspicious extractions (EMPTY_LARGE / TINY_RATIO / HUGE_RATIO / ARTIFACTS / SPA_NO_FALLBACK) for human review.
- New `benchmark/compare_outputs.py` — generates side-by-side `.md` outputs of the 4 extractors for any sample of pages.
- Test suite expanded from **6 → 17 tests** (JSON-LD types, multi-lang, layout-tables, parser detection).

**API compatibility**: 100% backward-compatible with v0.1.x. Existing code keeps working; new features are opt-in.

## Install

```bash
pip install RDTextract           # minimal install (html.parser only)
pip install RDTextract[fast]     # recommended: adds lxml for faster parsing
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

# Multi-language: target one specific language for stub detection
if not rdtextract.is_low_value_stub(markdown, language="en"):
    save(markdown)
```

> **Note** : PyPI distribution is `RDTextract`, Python module is `rdtextract` (PEP 8 lowercase).

## Why another HTML→Markdown lib?

Existing tools target *human readability* (newsletters, archive). `RDTextract` targets *LLM training data*: every byte should carry signal.

Benchmark on **Tranco top-1000 .fr** homepages (672 pages successfully fetched and processed), measured against a corpus quality scorer (lower artifact counts = cleaner output):

| Extractor       | Quality (corrected) | double-bullet | orphan punct | http dump | para dup | Total artifacts |
|-----------------|---------------------|---------------|--------------|-----------|----------|-----------------|
| **RDTextract**  | **99.3**            | **0**         | **0**        | **0**     | **0**    | **0**           |
| html2text       | 96.2                | 1             | 148          | 70        | 2 373    | 2 592           |
| trafilatura     | 96.1                | 18            | 780          | 10        | 309      | 1 117           |
| markdownify     | 85.5                | 0             | 246          | 107       | 5 042    | 5 395           |

RDTextract wins on **quality** AND on **all 4 artifact metrics** — zero artifacts on every counter. Reproducible: see [`benchmark/`](benchmark/) — domain list is committed (Tranco, deterministic), HTML cache is `.gitignored`.

### Validated by human review

On 4 randomly-sampled pages (Université Paris Cité, Sport 2000, Élysée.fr, Polytechnique), reading the markdown outputs side-by-side confirms:

- **trafilatura** misses entire structured sections (cards, lists) and duplicates paragraphs (`"Découvrir le campus"` ×2, legal disclaimers ×6)
- **html2text** captures everything but the first 1000-2000 chars are systematically the navigation mega-menu
- **markdownify** dumps everything raw (often >100 KB per page, unusable for LLM training)
- **RDTextract** captures the structured cards trafilatura misses, drops the menu nav html2text keeps, and dedupes what trafilatura repeats

Use `python benchmark/compare_outputs.py` to generate side-by-side comparisons on your own pages.

### Performance

- **107 ms/page** on average (with `[fast]` extra installed — `lxml` backend)
- **152 ms/page** without `lxml` (pure-Python `html.parser`)
- Roughly 2-3× slower than `html2text` (we filter + walk + dedup more aggressively), but produces **zero artifacts** vs html2text's 2 592.

## API

### `extract(html: str) -> str`
Convenience: `to_markdown(clean_html(html))`. The main entry point.

### `clean_html(html: str) -> str`
Strip nav/footer/scripts/ads/hidden elements. Drops responsive duplicates (mobile/desktop variants), icon font ligatures, role-based junk (`role=navigation`, `role=banner`, …). Preserves `<script type="application/ld+json">` for structured data fallback.

Smart guards built in:
- Auto-falls back from `lxml` to `html.parser` when malformed HTML over-nests content into a single `<header>`/`<nav>`.
- Size-guard preserves large `<header>`/`<nav>`/`<div>` elements that match junk patterns but contain real content (e.g. WordPress `with-nav` modifier, Drupal `region-header` wrappers, React 18 `<div hidden>` Suspense boundaries).

### `to_markdown(cleaned_html: str) -> str`
Walk the cleaned tree and emit Markdown. Includes:
- Heading levels, lists (with sublist flattening), tables (colspan, nested, layout-table fix), code blocks, blockquotes, definition lists.
- Post-processing: collapse whitespace, restore breadcrumb separators, dedup consecutive blocks, dedup global blocks (UI widgets repeated ≥3×), strip standalone URL lines, strip orphan punctuation.
- **Fallback chain** for empty body:
    1. **JSON-LD** structured data (Article, NewsArticle, BlogPosting, Recipe, FAQPage, HowTo, Product, with `@graph` wrapper support)
    2. **Meta fallback** (`<title>` + meta description, with smart length thresholds)

### `is_low_value_stub(markdown: str, language: str | None = None) -> bool`
True if the markdown is a paywall, login stub, skip-link, or empty page (no LLM training value). Combined length + marker check (avoids false positives on real articles that happen to mention subscription words in passing).

Supported languages for marker detection: **`fr`, `en`, `es`, `de`, `it`**. Pass `language=None` (default) to check all supported languages.

```python
rdtextract.is_low_value_stub(md)                    # check all languages
rdtextract.is_low_value_stub(md, language="en")     # only EN markers
```

### `PARSER`
Module-level constant exposing the parser actually in use: `'lxml'` if installed, otherwise `'html.parser'`.

```python
import rdtextract
print(rdtextract.PARSER)   # → 'lxml' or 'html.parser'
```

## Architecture

Two stages, ~700 lines of pure Python total:

```
HTML raw
   ↓
HTMLCleaner.clean_html()   ── strip 90% of DOM (nav, footer, ads, scripts, hidden)
   ↓
Cleaned HTML
   ↓
MarkdownConverter.to_markdown()   ── custom walker emitting clean Markdown
   ↓
Markdown
   ↓
[optional] is_low_value_stub()   ── filter paywalls / login / empty
   ↓
LLM training corpus
```

Custom walker (no `markdownify` dependency) avoids ~50% of buggy edge cases that wrap-libraries inherit.

## Testing & benchmarking

```bash
pip install -e ".[dev,benchmark]"
pytest -q                          # 17 tests
python benchmark/fetch.py --top 1000   # download HTML cache
python benchmark/run.py            # 4-extractor comparison
python benchmark/find_outliers.py  # find pages where extraction is suspect
python benchmark/compare_outputs.py --samples 10   # side-by-side review
```

The `benchmark/` directory is reproducible: the Tranco domain list is committed, the HTML cache is `.gitignored` (re-fetched on first run, ~30 min for top-1000).

## License

MIT — see [LICENSE](LICENSE).

## Author

[Théo CHARLET](https://github.com/RDTvlokip) — extracted from the [RDTvlokip Search](https://search.rdtvlokip.fr) crawler stack.
