# RDTextract v0.4.0

Content-recovery release plus a new batch API. Every fix in this release was found
by reading **complete HTML ↔ complete Markdown** pairs of the *same* page (not
snippets, not aggregate scores) on a 205,000-page French crawl, then measured at
scale before shipping.

## Recovered content

- **Article titles.** The near-universal CMS pattern `<header
  class="entry-header"><h1 class="entry-title">…</h1></header>` (WordPress, Astra,
  and many themes) was decomposed as chrome, so the page title vanished from the
  Markdown. Measured on 4,000 pages: **31.5 % of titled pages lost their title.**
  A new `_wraps_article_title` guard preserves any container holding an
  article-title heading (`entry-title`/`post-title`/`itemprop=headline`, inside
  `<article>`, or a bare page-title `<header>` with no nav), bringing loss down to
  ~17 % — the remainder being page-type labels ("Connexion", "Mentions légales")
  and site names in mastheads that *should* be dropped. Site mastheads stay
  stripped.
- **FAQ accordion questions.** CSS-only accordions put the question in
  `<label><h3>Question ?</h3></label>` next to a hidden checkbox. `<label>` is a
  form tag and was decomposed, so the answers survived without their questions. A
  `<label>` that contains a heading is now unwrapped, so the whole Q&A is kept.
- **Cookie-plugin banners on short pages.** Complianz (`cmplz-*`), Cookie Law Info
  (`cli-*`), Tarteaucitron, OneTrust, Didomi, Axeptio, Borlabs, cookieconsent.js…
  banner containers are stripped unconditionally. Their class names glue the word
  "cookie" (so the plain pattern missed them) and a long banner on a short article
  otherwise survived the content-ratio guard.

## New API — cross-page boilerplate removal

- **`extract_site(htmls, *, threshold=0.6, min_pages=5, min_unique_chars=400)`** —
  pass every page you have for one site. Text that appears on ≥`threshold` of the
  pages (mega-menus, footers, cookie text, per-item CTAs) is identified from the
  site's own page set — **no keyword lists** — and removed. Guards:
  - **thin-site**: a page is left untouched if stripping would leave it under
    `min_unique_chars` (on near-duplicate sites the shared text *is* the content);
  - **headings preserved** to keep per-page structure;
  - **below `min_pages`** non-empty pages, nothing is stripped.

  Validated on 15+ sites by reading full before/after Markdown: mega-menus
  (ardeche.fr), cookie-category text (c-campus.fr) and widget CTAs removed while
  clean sites (5/12) were left 100 % untouched and thin sites fully guarded.
  `extract()` (single page) is unchanged.

## Also

- "top of page" / "bottom of page" a11y region labels stripped.

## Tests

**48 → 58** (title preservation, FAQ-label accordion, cookie-plugin banner,
`extract_site` behaviour + thin-site guard).

100 % backward-compatible: `extract`, `clean_html`, `to_markdown`,
`is_low_value_stub` unchanged; `extract_site` is additive.
