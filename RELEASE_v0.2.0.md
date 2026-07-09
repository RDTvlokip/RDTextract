# v0.2.0 — lxml backend, JSON-LD fallback, multi-language stubs

Major release with gains across every metric measured on the **Tranco top-1000 .fr** benchmark (672 pages). 100% backward-compatible with v0.1.x.

```bash
pip install -U RDTextract           # minimal
pip install -U RDTextract[fast]     # recommended: adds lxml (2-3x faster)
```

## Highlights

- **`[fast]` extra** — opt-in `lxml` backend, **107 ms/page** (vs 152 ms with `html.parser`), with automatic fallback on malformed HTML.
- **JSON-LD fallback** — Schema.org structured data (Article, NewsArticle, BlogPosting, Recipe, FAQPage, HowTo, Product, with `@graph` wrapper) extracted when the body is empty -> **recoverable empty pages 14 -> 0**.
- **Multi-language stub detection** — `is_low_value_stub(md, language="en")` now supports `fr`, `en`, `es`, `de`, `it` (paywall, login, skip-link markers).
- **`PARSER` constant** — module-level value exposing the active parser (`'lxml'` or `'html.parser'`).

## Benchmark — v0.1.x -> v0.2.0 (Tranco top-1000 .fr, 672 pages)

| Metric                  | v0.1.x | **v0.2.0** | Delta      |
|-------------------------|--------|------------|------------|
| Quality (corrected)     | 98.3   | **99.3**   | **+1.0**   |
| Avg markdown size       | 5 538c | **6 875c** | **+24%**   |
| Speed (with `lxml`)     | 152 ms | **107 ms** | **-30%**   |
| Empty pages             | 39     | **21**     | **-46%**   |
| Recoverable empty pages | 14     | **0**      | **-100%**  |
| Total artifacts         | 9      | **0**      | **-100%**  |

## vs other extractors (Q.corr / total artifacts)

| Extractor       | Q.corr   | Total artifacts |
|-----------------|----------|-----------------|
| **RDTextract**  | **99.3** | **0**           |
| html2text       | 96.2     | 2 592           |
| trafilatura     | 96.1     | 1 117           |
| markdownify     | 85.5     | 5 395           |

## Robustness fixes (no regression, all gains)

- React 18 SSR Suspense boundaries (`<div hidden>` with content) preserved.
- WordPress Elementor pages no longer destroyed by `widget` pattern over-match.
- Drupal pages with malformed `<header>` wrappers now extract the real content.
- Layout-tables (image + caption WordPress) collapsed cleanly to paragraphs.
- Gzipped HTML leaks (corrupted fetcher) detected -> empty output instead of mojibake.

## Tooling

- `benchmark/find_outliers.py` — classifies suspicious extractions (EMPTY_LARGE / TINY_RATIO / HUGE_RATIO / ARTIFACTS / SPA_NO_FALLBACK) for human review.
- `benchmark/compare_outputs.py` — side-by-side `.md` outputs of the 4 extractors for any sample of pages.
- Test suite **6 -> 17** tests (JSON-LD types, multi-lang, layout-tables, parser detection).

## Compatibility

100% backward-compatible with v0.1.x. Existing code keeps working; new features are opt-in.

**Full changelog**: https://github.com/RDTvlokip/RDTextract/compare/v0.1.1...v0.2.0
