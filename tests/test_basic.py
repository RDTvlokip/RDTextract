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


# ── v0.2.0 features ──────────────────────────────────────────────────────────

def test_jsonld_recipe_fallback():
    """SPA pages with empty body but Recipe JSON-LD must be recovered."""
    html = """
    <html><head>
      <script type="application/ld+json">
      {"@type":"Recipe","name":"Tarte au citron",
       "description":"Une délicieuse tarte au citron meringuée maison qui ravira tous vos invités.",
       "recipeIngredient":["3 citrons","200g sucre","4 oeufs","pâte sablée"],
       "recipeInstructions":[{"@type":"HowToStep","text":"Préchauffer le four"},
                             {"@type":"HowToStep","text":"Étaler la pâte"}]}
      </script>
    </head><body></body></html>
    """
    md = rdtextract.extract(html)
    assert "Tarte au citron" in md
    assert "3 citrons" in md
    assert "Préchauffer" in md


def test_jsonld_article_fallback():
    html = """
    <html><head>
      <script type="application/ld+json">
      {"@type":"Article","headline":"Mon article",
       "description":"Description de l'article qui doit dépasser le seuil de 200 caractères pour déclencher le fallback JSON-LD lorsque le body est vide.",
       "articleBody":"Le corps de l'article avec du contenu substantiel pour la validation."}
      </script>
    </head><body></body></html>
    """
    md = rdtextract.extract(html)
    assert "# Mon article" in md
    assert "corps de l'article" in md


def test_jsonld_faq_fallback():
    html = """
    <html><head>
      <script type="application/ld+json">
      {"@type":"FAQPage","mainEntity":[
        {"@type":"Question","name":"Question 1 suffisamment longue pour le test FAQ ?",
         "acceptedAnswer":{"@type":"Answer","text":"Réponse détaillée à la première question avec assez de contenu pour passer."}},
        {"@type":"Question","name":"Question 2 également de longueur correcte ?",
         "acceptedAnswer":{"@type":"Answer","text":"Deuxième réponse avec assez de texte pour atteindre le seuil minimum requis."}}
      ]}
      </script>
    </head><body></body></html>
    """
    md = rdtextract.extract(html)
    assert "### Question 1" in md
    assert "### Question 2" in md
    assert "Deuxième réponse" in md


def test_jsonld_graph_array():
    """JSON-LD with @graph wrapper (common WordPress/Yoast pattern)."""
    html = """
    <html><head>
      <script type="application/ld+json">
      {"@context":"https://schema.org","@graph":[
        {"@type":"WebSite","name":"Site"},
        {"@type":"Article","headline":"Article via @graph",
         "description":"Description suffisamment longue pour passer le seuil minimum requis par le fallback JSON-LD, qui attend au moins 200 caractères au total entre titre et description avant d'accepter le rendu."}
      ]}
      </script>
    </head><body></body></html>
    """
    md = rdtextract.extract(html)
    assert "# Article via @graph" in md


def test_low_value_stub_english():
    assert rdtextract.is_low_value_stub("This article is for subscribers. Sign in to continue.")
    assert rdtextract.is_low_value_stub("Subscribe to read", language="en")
    # FR-only marker must not match an EN page
    assert not rdtextract.is_low_value_stub(
        "Subscribe to read", language="fr"
    )


def test_low_value_stub_skip_links_multilang():
    for skip in ("Skip to content", "Skip to main content", "Saltar al contenido",
                 "Zum Inhalt springen", "Vai al contenuto"):
        assert rdtextract.is_low_value_stub(skip), f"failed: {skip}"


def test_low_value_stub_long_real_article_passes():
    """Real article mentioning subscription words in passing must NOT be flagged."""
    md = ("# Comment lire la presse en ligne\n\n"
          "De nombreux journaux proposent désormais un accès payant à leur contenu. "
          "L'utilisateur peut s'abonner pour lire la suite des articles, ou choisir "
          "une formule premium. " * 5)
    assert not rdtextract.is_low_value_stub(md)


def test_layout_table_one_empty_column_collapsed():
    """WordPress-style image+caption table: image cell empty, caption rendered as 1-col."""
    html = """<html><body><table>
      <tr><td>Légende A</td><td></td></tr>
      <tr><td>Légende B</td><td></td></tr>
    </table></body></html>"""
    md = rdtextract.extract(html)
    assert "| Légende A |" in md
    assert "| |" not in md  # empty side cell removed


def test_single_cell_table_becomes_paragraph():
    """1×1 table (WordPress info-box pattern) → plain paragraph, not table syntax."""
    html = "<html><body><table><tr><td>Info importante en encadré</td></tr></table></body></html>"
    md = rdtextract.extract(html)
    assert "Info importante en encadré" in md
    assert "|" not in md  # no table syntax leaked


def test_real_2x2_table_preserved():
    html = """<html><body><table>
      <tr><th>Ville</th><th>Population</th></tr>
      <tr><td>Paris</td><td>2.1M</td></tr>
    </table></body></html>"""
    md = rdtextract.extract(html)
    assert "| Ville | Population |" in md
    assert "| Paris | 2.1M |" in md


def test_parser_detection():
    """PARSER must resolve to either 'lxml' (if installed) or 'html.parser'."""
    assert rdtextract.PARSER in ('lxml', 'html.parser')
