"""RDTextract — HTML→Markdown extractor optimized for LLM training corpora."""

from rdtextract.cleaner import HTMLCleaner
from rdtextract.converter import MarkdownConverter

__version__ = "0.1.1"

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


def is_low_value_stub(markdown: str) -> bool:
    """True if the markdown is a paywall, login stub, skip-link, or empty page (no LLM training value)."""
    return MarkdownConverter.is_low_value_stub(markdown)
