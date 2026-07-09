# RDTextract v0.2.1

Bug-fix and quality release. **v0.2.0 does not import on Python 3.9** — upgrade is
recommended for anyone on 3.9, and this release also removes systematic UI noise
from extracted Markdown.

## Fixes

### Critical
- **Python 3.9 import crash.** `is_low_value_stub(..., language: str | None = None)`
  used a PEP 604 union annotation evaluated at import time, which raises
  `TypeError` on Python 3.9 (`str | None` requires 3.10+). Added
  `from __future__ import annotations` to all modules. A new CI matrix
  (3.9 → 3.12) prevents regressions.

### Robustness
- **Fail-closed conversion.** On any internal exception, `to_markdown()` and
  `clean_html()` previously returned the *raw HTML*, leaking markup into the
  training corpus. They now return `""` (correctly flagged by
  `is_low_value_stub`).
- **Recursion guard on the walker.** Deeply nested / adversarial markup
  (thousands of unclosed `<div>`s) no longer blows the recursion limit and
  aborts the page. Content above the depth cap is preserved; the pathological
  subtree is flattened to text.
- **`is_low_value_stub(None)`** no longer raises `AttributeError`; non-`str`
  input is treated as a low-value stub.

### Output quality (measured on the 672-page Tranco top-1000 .fr benchmark)
- **Accessibility skip-links removed.** "Aller au contenu", "Skip to content",
  "Ignorer pour aller au contenu", and concatenated skip-nav bars opened
  **130 / 650 pages (20 %)**; now **0**, with **zero false positives** verified
  line-by-line across the whole corpus. Multi-language (FR/EN/ES/DE/IT).
- **Space-before-punctuation fixed.** The `<a>`-renderer's trailing space left
  artifacts like `"Visitez ce lien ."`. Occurrences dropped **1 805 → 41**
  (−98 %). Domain extensions (`.com`, `.fr`), decimals, and French typography
  (space before `; : ! ? »`) are deliberately preserved.

### Packaging
- **Single-sourced version** via `[tool.setuptools.dynamic]` (no more drift
  between `pyproject.toml` and `__init__.py`).
- **`.gitignore`** no longer hides `RELEASE_*.md`.

## Tests
Suite grew **17 → 26 tests**, adding robustness (recursion, gzip guard, non-str
stub) and quality regressions (skip-link variants, false-positive protection,
punctuation).

## Compatibility
100 % backward-compatible API. Output is cleaner for the same input; no code
changes required.
