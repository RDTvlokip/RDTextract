"""Smoke tests for RDTextract. To be expanded with edge cases (paywall variants,
hr-in-li, dedup, meta fallback, table colspan, …)."""

import rdtextract


def test_extract_simple_article():
    html = """
    <html><head><title>Hello</title></head>
    <body><article><h1>Title</h1><p>Some content here.</p></article></body></html>
    """
    md = rdtextract.extract(html)
    assert "# Title" in md
    assert "Some content here." in md


def test_strips_nav_and_footer():
    html = """
    <html><body>
      <nav>Home About Contact</nav>
      <main><p>Real content.</p></main>
      <footer>Copyright 2026</footer>
    </body></html>
    """
    md = rdtextract.extract(html)
    assert "Real content." in md
    assert "Home About Contact" not in md
    assert "Copyright 2026" not in md


def test_paywall_detected_as_low_value():
    md = "Cet article est réservé aux abonnés. Connectez-vous."
    assert rdtextract.is_low_value_stub(md)


def test_real_article_not_low_value():
    md = "# Real article\n\n" + ("This is genuine content. " * 50)
    assert not rdtextract.is_low_value_stub(md)


def test_meta_fallback_on_empty_body():
    html = """
    <html><head>
      <title>Page Title That Is Long Enough</title>
      <meta name="description" content="A description that is reasonably long, well over the minimum threshold for the meta fallback to trigger when the body is empty — needs at least 200 characters total combined with the title.">
    </head><body></body></html>
    """
    md = rdtextract.extract(html)
    assert "Page Title" in md
    assert "description" in md.lower()


def test_hr_inside_li_skipped():
    html = "<html><body><ul><li>Item A<hr>still A</li><li>Item B</li></ul></body></html>"
    md = rdtextract.extract(html)
    assert "- ---" not in md
    assert "Item A" in md
    assert "Item B" in md
