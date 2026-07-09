"""RDTextract — HTML→Markdown extractor optimized for LLM training corpora."""

from __future__ import annotations

from rdtextract.cleaner import HTMLCleaner
from rdtextract.converter import MarkdownConverter

__version__ = "0.2.1"


def _detect_parser() -> str:
    """Use lxml if available (2-3× faster), fall back to stdlib html.parser."""
    try:
        import lxml  # noqa: F401
        return 'lxml'
    except ImportError:
        return 'html.parser'


PARSER = _detect_parser()

__all__ = [
    "HTMLCleaner",
    "MarkdownConverter",
    "clean_html",
    "to_markdown",
    "extract",
    "is_low_value_stub",
]


def clean_html(html: str) -> str:
    """Strip nav/footer/scripts/ads/hidden elements from HTML, keep semantic content."""
    return HTMLCleaner.clean_html(html)


def to_markdown(cleaned_html: str) -> str:
    """Convert (already cleaned) HTML to Markdown. Falls back to title+meta if walker yields empty."""
    return MarkdownConverter.to_markdown(cleaned_html)


def extract(html: str) -> str:
    """One-shot: clean raw HTML then convert to Markdown."""
    return MarkdownConverter.to_markdown(HTMLCleaner.clean_html(html))


def is_low_value_stub(markdown: str, language: str | None = None) -> bool:
    """True if the markdown is a paywall, login stub, skip-link, or empty page (no LLM training value).

    Args:
        markdown: text to evaluate.
        language: ISO 639-1 code ('fr', 'en', 'es', 'de', 'it'). None = check all supported languages.
    """
    return MarkdownConverter.is_low_value_stub(markdown, language=language)
