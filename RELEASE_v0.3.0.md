# RDTextract v0.3.0

Large output-quality release. Every change was validated on a **205,000-page**
French crawl — each candidate fix run over 10k+ random pages, with false positives
verified line-by-line and several tempting heuristics **backed out** when the audit
showed them removing real content.

## Recovered content (highest impact)

- **`overlay` junk pattern narrowed.** The bare `overlay` class matched content
  cards on many themes (Joomla Helix, news grids) and silently gutted whole
  articles — up to **+90k chars/page** recovered. Validated: **105 pages recovered
  on 12k, zero regressions**, content confirmed by reading full outputs. Genuine
  junk overlays are still stripped via their primary word (`modal-overlay`, …).

## Markdown structure

- **Heading in a list item → bold.** `- ### Title` (invalid Markdown) becomes
  `- **Title**` (2155 → ~0 occurrences on 5k pages).
- **Single-column layout tables → paragraphs**, instead of a 1-wide table with an
  empty `| --- |` header (empty-header 29→5, orphan-separator 29→3).
- **Un-glued dates.** `18avr.2024` → `18 avr. 2024` when day/month/year sit in
  separate styled `<span>`s. Anchored on FR months + a 4-digit year, so non-dates
  (`12mai500`) are untouched. 0 false positives on 10k.

## UI-noise removal

- **Invisible / format characters** normalised: zero-width space, ZWNJ, BOM, word
  joiner, soft hyphen and bidi marks removed; NBSP / narrow-NBSP folded to a plain
  space.
- **Standalone action labels** (Haut de page, Retour en haut, Partager, Imprimer,
  Tweeter…), **breadcrumb trails** (`Accueil / X / Y`, `Vous êtes ici : …`),
  broadened **skip-link** variants (incl. concatenated skip-nav bars), and generic
  **read-more CTAs** (En savoir plus, Lire la suite, Voir plus — 6.5k removed on
  10k, 0 FP).
- **Repeated per-item CTAs** deduped ("RDV sur le site" ×14 → 1) and **consecutive
  duplicate captions** collapsed.
- **Cookie-consent banners** now flagged by `is_low_value_stub`.

## Discipline: false positives held

Backed out after large audits proved them unsafe:
- **ALL-CAPS mega-menu** stripper — removed team rosters and org directories.
- **`<form>`-wrapped content** — mostly genuine form pages; too ambiguous.
- **`display:none` content** — 87% of large hidden blocks are menus/modals/forms.
- **Lone-digit strip** — ate date fragments (`04`←`JUIN`) and numbered lists.

## Robustness (from v0.2.1, included here)

Python 3.9 import fix, fail-closed conversion, recursion guard, CI 3.9–3.12.

## Tests

**26 → 48.** 100% backward-compatible API; output is cleaner for the same input.
