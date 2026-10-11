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

## What's new in v0.4.0

Content-recovery release + a new batch API. Every fix was found by reading full
HTML↔Markdown pairs on a 205k-page French crawl, then measured at scale.

- **Article titles no longer lost.** The `<header class="entry-header"><h1
  class="entry-title">` pattern (WordPress/Astra and most CMS themes) was being
  stripped as chrome — **31.5 % of article pages silently lost their title**. A
  new title-preserving guard keeps it (down to ~17 %, the rest being page-labels /
  site names that *should* drop), while site mastheads are still removed.
- **FAQ accordion questions kept.** CSS accordions wrap the question heading in a
  `<label>` (a form tag); it was decomposed, leaving answers without questions.
  A `<label>` holding a heading is now unwrapped, so the Q&A survives.
- **Cookie-plugin banners removed even on short pages.** Complianz (`cmplz-*`),
  Cookie Law Info, Tarteaucitron, OneTrust, Didomi, Axeptio… containers are
  stripped unconditionally (their class names hide the word "cookie", and a long
  banner on a short page slipped past the ratio guard).
- **`extract_site(htmls)` — new API.** Give it every page you have for one site;
  text that repeats across the site (mega-menus, footers, cookie text, per-item
  CTAs) is detected from the page set itself — **no keyword lists** — and removed,
  with a thin-site guard that never guts near-duplicate pages and headings kept.
  `extract()` (single page) is unchanged.

Test suite **26 → 58**. 100 % backward-compatible.

## What's new in v0.3.0

Large output-quality release, every change validated on a **205k-page** French
crawl (10k+ random pages per audit, false-positives verified line-by-line):

- **Recovered lost content** — the over-broad `overlay` junk pattern was silently
  destroying whole articles on ~3% of pages that use it (news/heritage/HR content,
  up to +90k chars/page). Validated: 105 pages recovered on 12k, **zero regressions**.
- **Cleaner Markdown structure** — a heading nested in a list item now renders as
  bold (`- **Title**`) instead of invalid `- ### Title` (2155→~0 occurrences); a
  single-column layout table collapses to paragraphs instead of an empty-header
  1-wide table.
- **Un-glued dates** — `18avr.2024` → `18 avr. 2024` (day/month/year split across
  styled `<span>`s), anchored on FR months so non-dates are untouched.
- **More UI noise removed** — invisible/zero-width characters (ZWSP, BOM, soft
  hyphen; NBSP→space), standalone action labels (Haut de page, Partager, Imprimer),
  breadcrumb trails (Accueil / X / Y), broadened skip-link variants, generic
  read-more CTAs (En savoir plus, Lire la suite), repeated per-item CTAs, and
  consecutive duplicate captions.
- **Cookie-banner stubs** flagged by `is_low_value_stub`.
- **Held the line on false positives** — attempted mega-menu (ALL-CAPS), form-wrapped,
  display:none and lone-digit strips were **backed out** after large audits showed
  them eating real content (team rosters, directories, dates).

Test suite **26 → 48**. 100% backward-compatible API.

## What's new in v0.2.1

Bug-fix + quality release. **v0.2.0 fails to import on Python 3.9** (a `str | None`
annotation evaluated at import time) — v0.2.1 restores the advertised 3.9 support.

- **Python 3.9 import fixed** — `from __future__ import annotations` added; the CI
  matrix now covers 3.9 → 3.12 so this can't regress.
- **Fail-closed conversion** — on any internal error the converter/cleaner now
  return `""` instead of leaking raw HTML into the corpus.
- **Recursion guard** — pathological nesting (thousands of unclosed tags) is
  flattened past a depth cap instead of aborting the whole page.
- **Skip-link stripping** — accessibility skip-links ("Aller au contenu", "Skip to
  content", concatenated skip-nav bars) are removed from the output. They opened
  **20 % of pages** in the 672-page benchmark; now **0 %**, with zero false
  positives on that corpus.
- **Space-before-punctuation fix** — the `<a>`-renderer no longer leaves `"lien ."`;
  1 805 → 41 occurrences across the benchmark, while `.com`/`.fr` extensions,
  decimals, and French typography (space before `; : ! ?`) are preserved.
- **Single-sourced version** + `is_low_value_stub(None)` no longer raises.

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
- Test suite expanded from **6 → 48 tests** (JSON-LD types, multi-lang, layout-tables, parser detection, robustness, skip-link/punctuation/overlay/date/heading/table regressions).

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

Measured on the full 672-page benchmark (single pass; figures are
machine-dependent):

- **~115 ms/page** with the `[fast]` extra (`lxml` backend)
- **~135 ms/page** without `lxml` (pure-Python `html.parser`) — only ~1.2× slower,
  because most of the time is the Markdown walker, not the parser
- Roughly 3× slower than `html2text` (~40 ms/page): we filter + walk + dedup far
  more aggressively, but produce **zero artifacts** vs html2text's 2 592.

## API

### `extract(html: str) -> str`
Convenience: `to_markdown(clean_html(html))`. The main entry point.

### `extract_site(htmls, *, threshold=0.6, min_pages=5, min_unique_chars=400) -> list[str]`
Extract **many pages of the same site** and remove cross-page boilerplate. Text
that appears on ≥`threshold` of the pages (mega-menus, footers, cookie banners,
per-item CTAs) is detected from the page set itself — no keyword lists — and
stripped. A thin-site guard leaves a page untouched if fewer than
`min_unique_chars` non-boilerplate characters would remain (on near-duplicate
sites the shared text *is* the content); Markdown headings are preserved. Below
`min_pages` non-empty pages, nothing is stripped. Returns Markdown in input order.

```python
pages = rdtextract.extract_site([html1, html2, html3])   # all from example.com
```

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
pytest -q                          # 58 tests
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
