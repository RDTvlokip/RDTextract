"""Smoke tests for RDTextract. To be expanded with edge cases (paywall variants,
hr-in-li, dedup, meta fallback, table colspan, …)."""

import re

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
    """Image+caption layout table: empty image column dropped, captions kept as
    plain paragraphs (a single-column table is layout, not tabular data)."""
    html = """<html><body><table>
      <tr><td>Légende A</td><td></td></tr>
      <tr><td>Légende B</td><td></td></tr>
    </table></body></html>"""
    md = rdtextract.extract(html)
    assert "Légende A" in md and "Légende B" in md  # content preserved
    assert "|" not in md                            # collapsed to paragraphs, no table


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


# ── Robustness fixes ─────────────────────────────────────────────────────────

def test_deeply_nested_html_no_leak_and_keeps_outer_content():
    """Pathological nesting must not leak HTML nor abort: content above the
    depth cap is preserved, the deep subtree is flattened, no exception escapes."""
    html = ('<html><body><article><h1>Real Title</h1>'
            '<p>Intro paragraph.</p>'
            '<div>' + '<div>' * 3000 + 'deep' + '</div>' * 3000 + '</div>'
            '<p>Outro paragraph.</p></article></body></html>')
    md = rdtextract.extract(html)
    assert '<div' not in md.lower() and '<!doctype' not in md.lower()
    assert '# Real Title' in md
    assert 'Intro paragraph.' in md
    assert 'Outro paragraph.' in md


def test_binary_gzip_leak_returns_empty():
    """A gzip magic-byte prefix (undecompressed fetch) yields empty, not mojibake."""
    assert rdtextract.extract('\x1f\x8b\x08\x00garbage bytes here') == ''


def test_low_value_stub_non_str_is_stub():
    """Non-str input (e.g. None from a failed step) is treated as low-value."""
    assert rdtextract.is_low_value_stub(None)
    assert rdtextract.is_low_value_stub(123)


# ── Skip-link stripping ──────────────────────────────────────────────────────

def test_skip_link_stripped_simple():
    html = ("<html><body><a href='#main'>Aller au contenu principal</a>"
            "<main><p>Le vrai contenu de la page.</p></main></body></html>")
    md = rdtextract.extract(html)
    assert 'Aller au contenu principal' not in md
    assert 'Le vrai contenu de la page.' in md


def test_skip_link_stripped_filler_and_multilang():
    for skip in ('Ignorer pour aller au contenu', 'Skip to content',
                 'Skip Navigation', 'Zum Inhalt springen', 'Vai al contenuto'):
        html = f"<html><body><p>{skip}</p><p>Contenu réel ici présent.</p></body></html>"
        md = rdtextract.extract(html)
        assert skip not in md, f"not stripped: {skip}"
        assert 'Contenu réel ici présent.' in md


def test_skip_link_concatenated_nav_bar_stripped():
    """Long concatenated skip-nav bars (no separators) must be dropped too."""
    bar = ('Aller au contenu principal Aller au menu principal '
           'Aller à la recherche Aller au pied de page')
    html = f"<html><body><p>{bar}</p><p>Article véritable et substantiel.</p></body></html>"
    md = rdtextract.extract(html)
    assert 'Aller au menu principal' not in md
    assert 'Article véritable et substantiel.' in md


def test_skip_link_does_not_eat_real_content():
    """A real sentence merely starting with the words must NOT be dropped."""
    html = ("<html><body><p>Comment aller au contenu du coffre-fort numérique "
            "sans perdre ses données personnelles importantes.</p></body></html>")
    md = rdtextract.extract(html)
    assert 'coffre-fort numérique' in md


# ── Space-before-punctuation (the <a> trailing-space artifact) ────────────────

def test_no_space_before_punctuation_after_link():
    html = ("<html><body><p>Rendez-vous sur "
            "<a href='https://x.fr'>ASNR Academy</a>.</p></body></html>")
    md = rdtextract.extract(html)
    assert 'ASNR Academy.' in md
    assert 'Academy .' not in md


def test_punct_fix_preserves_domains_decimals_and_french_typography():
    html = ("<html><body>"
            "<p>Notre site <a href='#'>Domaine</a> .com fonctionne.</p>"
            "<p>Le prix est de <a href='#'>3</a> ,50 euros au total.</p>"
            "<p>Est-ce vrai <a href='#'>vraiment</a> ? Oui bien sûr !</p>"
            "</body></html>")
    md = rdtextract.extract(html)
    assert '.com' in md and 'Domaine.com' not in md   # domain extension kept spaced-safe
    assert ',50' in md and '3,50' not in md            # decimal comma preserved
    assert 'vraiment ?' in md                          # French space before ? preserved


# ── Invisible / zero-width character normalization ───────────────────────────

def test_invisible_characters_normalized():
    html = ("<html><body><p>Zero​width​and﻿bom soft­hyphen</p>"
            "<p>non breaking spaces</p></body></html>")
    md = rdtextract.extract(html)
    for ch in ('​', '﻿', '­', ' ', ' '):
        assert ch not in md, f"invisible char {ch!r} leaked"
    assert 'non breaking spaces' in md   # NBSP/narrow-NBSP folded to plain space


# ── UI-noise standalone lines (share / print / back-to-top) ──────────────────

def test_ui_noise_lines_stripped():
    for label in ('Haut de page', 'Retour en haut', 'Partager', 'Imprimer', 'Tweeter'):
        html = f"<html><body><p>{label}</p><p>Contenu réel de la page ici.</p></body></html>"
        md = rdtextract.extract(html)
        assert not re.search(rf'(?im)^{re.escape(label)}\s*$', md), f"not stripped: {label}"
        assert 'Contenu réel de la page ici.' in md


def test_ui_noise_does_not_eat_real_content():
    """A real heading/sentence that merely starts with the word is kept."""
    html = ("<html><body><h2>Partager votre expérience avec la communauté</h2>"
            "<p>Imprimer les documents administratifs avant le rendez-vous.</p></body></html>")
    md = rdtextract.extract(html)
    assert 'Partager votre expérience' in md
    assert 'Imprimer les documents' in md


def test_skip_link_extra_variants_and_concatenated_no_core():
    """New variants + a concatenated bar that doesn't open with a known core."""
    for bar in ('Skip to the content',
                'Aller au texte Aller aux onglets Politique d’accessibilité du site',
                'Skip to accessibility mode link Aller au contenu principal Skip to main menu'):
        html = f"<html><body><p>{bar}</p><p>Le contenu réel et substantiel de la page.</p></body></html>"
        md = rdtextract.extract(html)
        assert 'Le contenu réel et substantiel de la page.' in md
        assert 'onglets' not in md and 'accessibility mode' not in md


def test_skip_verbs_chain_in_real_sentence_kept():
    """A real sentence chaining 'aller au …' verbs (no skip destination) is kept."""
    html = ("<html><body><p>Ce week-end je vais aller au marché, aller à la plage "
            "et aller au cinéma avec mes amis.</p></body></html>")
    md = rdtextract.extract(html)
    assert 'aller au marché' in md
    assert 'aller au cinéma' in md


# ── Cookie banners flagged as low-value ──────────────────────────────────────

def test_cookie_banner_is_low_value_stub():
    banner = ("Nous utilisons des cookies pour améliorer votre expérience. "
              "En poursuivant votre navigation, vous acceptez le dépôt de cookies.")
    assert rdtextract.is_low_value_stub(banner)
    # A long real article that mentions cookies once is NOT flagged.
    article = ("# Recette de cookies maison\n\n"
               "Ces cookies au chocolat sont délicieux. " * 30)
    assert not rdtextract.is_low_value_stub(article)


# ── Breadcrumb trails ────────────────────────────────────────────────────────

def test_breadcrumb_trail_stripped():
    for trail in ('Accueil / Actualités / Rentrée 2026', 'Accueil > Formation > Master',
                  'Home » News » Podcast', 'Vous êtes ici : Accueil > Agenda'):
        html = f"<html><body><p>{trail}</p><p>Le contenu réel de la page ici présent.</p></body></html>"
        md = rdtextract.extract(html)
        assert 'Le contenu réel de la page ici présent.' in md
        assert 'Actualités / Rentrée' not in md and 'Formation > Master' not in md


def test_breadcrumb_does_not_eat_real_content():
    """A real sentence starting with 'Accueil'/'Vous êtes ici' (no trail) is kept."""
    html = ("<html><body><p>Accueil personnalisé de nos clients toute la journée.</p>"
            "<p>Vous êtes ici pour apprendre et progresser ensemble.</p></body></html>")
    md = rdtextract.extract(html)
    assert 'Accueil personnalisé' in md
    assert 'Vous êtes ici pour apprendre' in md


# ── Repeated-CTA dedup + generic-CTA heuristic ───────────────────────────────

def test_generic_read_more_cta_fully_stripped():
    """Bare generic 'En savoir plus' widgets are pure noise → removed entirely,
    while each item's real content is preserved."""
    items = ''.join(
        f"<div><h3>Produit {i}</h3><p>Description du produit {i}.</p>"
        f"<a href='#'>En savoir plus</a></div>" for i in range(8))
    md = rdtextract.extract(f"<html><body>{items}</body></html>")
    assert md.lower().count('en savoir plus') == 0   # generic CTA removed
    for i in range(8):
        assert f'Description du produit {i}.' in md   # per-item content preserved


def test_specific_cta_repeats_deduplicated_not_erased():
    """A specific (non-generic) repeated CTA is deduped to one, not erased."""
    items = ''.join(
        f"<div><h3>École {i}</h3><p>Description {i}.</p>"
        f"<p>RDV sur le site de l'école</p></div>" for i in range(6))
    md = rdtextract.extract(f"<html><body>{items}</body></html>")
    assert md.lower().count("rdv sur le site de l'école") == 1


def test_standalone_read_more_stripped():
    html = ("<html><body>"
            "<article><h2>Actu</h2><p>Le corps.</p>"
            "<a href='#'>Lire la suite</a></article></body></html>")
    md = rdtextract.extract(html)
    assert 'lire la suite' not in md.lower()             # read-more gone
    assert 'Le corps.' in md


def test_read_more_heuristic_spares_specific_sentences():
    html = ("<html><body><p>En savoir plus sur les modalités d'inscription.</p>"
            "<p>Il reste 3 places disponibles pour l'atelier.</p></body></html>")
    md = rdtextract.extract(html)
    assert "En savoir plus sur les modalités" in md   # specific → kept
    assert "3 places disponibles" in md               # number in a sentence → kept


def test_lone_digit_not_stripped():
    """A standalone number is kept — stripping it ate date fragments / list
    numbers on the corpus, so the counter-badge heuristic was dropped."""
    html = "<html><body><p>Mercredi</p><p>1</p><p>JUIN</p><p>04</p></body></html>"
    md = rdtextract.extract(html)
    assert '1' in md and '04' in md


def test_non_cta_repeats_are_kept():
    """A repeated noun-phrase label (job title) is NOT a CTA and must survive."""
    people = ''.join(
        f"<div><h3>Chercheur {i}</h3><p>Chargé de recherche</p></div>" for i in range(6))
    md = rdtextract.extract(f"<html><body>{people}</body></html>")
    assert md.count('Chargé de recherche') == 6


def test_consecutive_duplicate_line_collapsed():
    """An image alt repeated as the very next caption line is collapsed to one."""
    html = ("<html><body><figure>"
            "<figcaption>Exposition pédagogique de l'ASNR</figcaption>"
            "<figcaption>Exposition pédagogique de l'ASNR</figcaption>"
            "</figure></body></html>")
    md = rdtextract.extract(html)
    assert md.count("Exposition pédagogique de l'ASNR") == 1


# ── Over-broad 'overlay' junk pattern (content-card false positive) ───────────

def test_overlay_content_card_is_kept():
    """A content card using an 'overlay' class (hover caption) must NOT be gutted."""
    html = ("<html><body><main>"
            "<div class='news-card'><figcaption class='uk-overlay-panel'>"
            "<h3>Colloque sur le droit européen</h3>"
            "<p>Un événement scientifique majeur organisé par la faculté.</p>"
            "</figcaption></div></main></body></html>")
    md = rdtextract.extract(html)
    assert 'Colloque sur le droit européen' in md
    assert 'événement scientifique majeur' in md


def test_modal_overlay_still_stripped():
    """Genuine junk overlays (via their primary word) are still removed."""
    html = ("<html><body>"
            "<div class='modal-overlay'>Fenêtre modale à ignorer</div>"
            "<div class='popup-overlay'>Popup promotionnel</div>"
            "<main><p>Le contenu réel de la page.</p></main></body></html>")
    md = rdtextract.extract(html)
    assert 'Le contenu réel de la page.' in md
    assert 'Fenêtre modale' not in md
    assert 'Popup promotionnel' not in md


# ── Glued dates (separate styled <span>s) ────────────────────────────────────

def test_glued_date_is_split():
    html = ("<html><body><p>"
            "<span>18</span><span>avr.</span><span>2024</span>"
            "</p><p>Événement du <span>3</span><span>février</span><span>2025</span>.</p>"
            "</body></html>")
    md = rdtextract.extract(html)
    assert '18 avr. 2024' in md
    assert '3 février 2025' in md


def test_date_deglue_does_not_touch_non_dates():
    html = "<html><body><p>La quantité 12mai500 est un code interne.</p></body></html>"
    md = rdtextract.extract(html)
    assert '12mai500' in md   # 500 is not a 4-digit year → untouched


# ── Heading nested in a list item → bold (not "- ### X") ─────────────────────

def test_heading_in_list_rendered_as_bold():
    html = ("<html><body><ul>"
            "<li><h3>Jean Birnbaum</h3><p>Philosophe et journaliste.</p></li>"
            "<li><h4>Corinne Maier</h4></li></ul></body></html>")
    md = rdtextract.extract(html)
    assert '- ###' not in md and '- ####' not in md
    assert '**Jean Birnbaum**' in md
    assert '**Corinne Maier**' in md
    assert 'Philosophe et journaliste.' in md


def test_standalone_heading_still_a_heading():
    """Headings outside a list are untouched."""
    html = "<html><body><article><h2>Titre de section</h2><p>Texte.</p></article></body></html>"
    md = rdtextract.extract(html)
    assert '## Titre de section' in md


# ── Single-column layout tables → paragraphs ─────────────────────────────────

def test_single_column_multirow_table_becomes_paragraphs():
    html = ("<html><body><table>"
            "<tr><td></td></tr>"
            "<tr><td>Premier paragraphe de contenu.</td></tr>"
            "<tr><td>Deuxième paragraphe distinct.</td></tr>"
            "</table></body></html>")
    md = rdtextract.extract(html)
    assert 'Premier paragraphe de contenu.' in md
    assert 'Deuxième paragraphe distinct.' in md
    assert '|' not in md          # no leftover 1-wide table / empty header


# ── extract_site(): cross-page boilerplate removal ───────────────────────────

# A promotional block in a plain <div> survives single-page cleaning (it is not
# nav/footer/junk-classed) — only cross-page frequency can identify it as chrome.
_SHARED = ("<div><p>Suivez-nous sur les réseaux sociaux et téléchargez notre "
           "application mobile disponible partout.</p></div>")


def _site_pages(bodies):
    return [f"<html><body><main>{_SHARED}{b}</main></body></html>" for b in bodies]


def test_extract_site_strips_shared_block_single_page_keeps_it():
    bodies = [f"<h1>Article {i}</h1><p>{'Contenu unique et substantiel numéro %d. ' % i * 20}</p>"
              for i in range(8)]
    pages = _site_pages(bodies)
    # single-page extraction cannot know the block is chrome → it survives
    assert 'Suivez-nous sur les réseaux sociaux' in rdtextract.extract(pages[0])
    out = rdtextract.extract_site(pages)
    assert len(out) == 8
    for i, md in enumerate(out):
        assert f'Contenu unique et substantiel numéro {i}.' in md   # unique kept
    assert 'Suivez-nous sur les réseaux sociaux' not in '\n'.join(out)  # shared removed


def test_extract_site_thin_site_guard_preserves_pages():
    """Near-identical pages (thin site): the shared text IS the content → kept."""
    bodies = ["<h2>Bienvenue</h2><p>Horaires: 9h-12h.</p>"] * 6
    pages = _site_pages(bodies)
    solo = [rdtextract.extract(p) for p in pages]
    out = rdtextract.extract_site(pages)
    assert out == solo           # guard leaves every page untouched


def test_extract_site_below_min_pages_is_noop():
    bodies = [f"<h1>Page {i}</h1><p>Texte {i}.</p>" for i in range(3)]
    pages = _site_pages(bodies)
    solo = [rdtextract.extract(p) for p in pages]
    assert rdtextract.extract_site(pages, min_pages=5) == solo   # too few pages → no-op


def test_extract_site_leaves_single_page_extract_unchanged():
    html = "<html><body><main><h1>Titre</h1><p>Du contenu.</p></main></body></html>"
    assert rdtextract.extract(html).strip()   # extract() itself is unaffected


# ── Article-title preservation (title was silently lost on ~1/3 of article pages)

def test_wordpress_entry_header_title_kept():
    """WordPress/Astra pattern: <header class="entry-header"> holds the <h1> title
    inside <article>. It must not be stripped as chrome."""
    html = ("<html><body>"
            "<header id='masthead'><nav><a href='#'>Accueil</a><a href='#'>Contact</a>"
            "<a href='#'>Blog</a></nav></header>"
            "<main><article>"
            "<header class='entry-header'><h1 class='entry-title'>Saisie immobilière : procédure et défense</h1>"
            "<span class='posted-on'>12 février 2024</span></header>"
            "<div class='entry-content'><p>Le contenu juridique de l'article.</p></div>"
            "</article></main></body></html>")
    md = rdtextract.extract(html)
    assert '# Saisie immobilière : procédure et défense' in md
    assert "Le contenu juridique de l'article." in md
    assert 'Accueil' not in md                      # site masthead nav still stripped


def test_h2_entry_title_card_kept():
    html = ("<html><body><article class='article-summary'>"
            "<header class='entry-header'><h2 class='entry-title'>La Pharmacie du Grand Siècle</h2></header>"
            "<p>Résumé de l'article.</p></article></body></html>")
    md = rdtextract.extract(html)
    assert 'La Pharmacie du Grand Siècle' in md


def test_bare_page_title_header_kept_but_masthead_stripped():
    # a bare page-title header (no nav, few links) is kept…
    page = "<html><body><header><h1>Doctorats honoris Causa en France</h1></header><p>Texte.</p></body></html>"
    assert 'Doctorats honoris Causa en France' in rdtextract.extract(page)
    # …but a masthead (nav + many links) is still stripped
    masthead = ("<html><body><header><h1>MonSite</h1>"
                "<nav><a href='#'>A</a><a href='#'>B</a><a href='#'>C</a><a href='#'>D</a></nav>"
                "</header><main><p>Contenu de la page.</p></main></body></html>")
    md = rdtextract.extract(masthead)
    assert 'MonSite' not in md
    assert 'Contenu de la page.' in md


def test_cookie_plugin_banner_stripped_even_on_short_page():
    """Complianz & co. banners glue 'cookie' in their class (cmplz-cookiebanner)
    and are large vs a short article — strip them unconditionally by plugin id."""
    banner = ("<div id='cmplz-cookiebanner-container'><div class='cmplz-cookiebanner'>"
              "<div class='cmplz-message'>Nous utilisons des technologies telles que "
              "les cookies pour stocker des informations. " * 5 + "</div>"
              "<button class='cmplz-btn'>Accepter</button></div></div>")
    html = f"<html><body><article><h1>Petit article</h1><p>Corps bref.</p></article>{banner}</body></html>"
    md = rdtextract.extract(html)
    assert '# Petit article' in md and 'Corps bref.' in md
    assert 'cookies pour stocker' not in md
    assert 'Accepter' not in md


def test_faq_accordion_label_question_kept():
    """CSS-accordion FAQ: <label><h3>Question?</h3></label> + answer. The <label>
    is a form tag but here wraps the question heading — it must survive."""
    html = ("<html><body><section><h2>Questions fréquentes</h2>"
            "<div><input type='checkbox' id='q1'>"
            "<label for='q1'><h3>Est-ce remboursé par l'assurance ?</h3></label>"
            "<div><p>Oui, c'est remboursé.</p></div></div>"
            "</section></body></html>")
    md = rdtextract.extract(html)
    assert 'Est-ce remboursé par l'"'"'assurance ?' in md   # question kept
    assert "Oui, c'est remboursé." in md                    # answer kept


def test_plain_form_label_still_stripped():
    """A genuine form-field label (no heading) is still removed."""
    html = ("<html><body><main><p>Contenu réel.</p>"
            "<form><label for='n'>Nom*</label><input id='n'></form></main></body></html>")
    md = rdtextract.extract(html)
    assert 'Contenu réel.' in md
    assert 'Nom*' not in md
