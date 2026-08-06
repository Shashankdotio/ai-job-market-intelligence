"""Reusable text-normalization helpers."""

import html

from bs4 import BeautifulSoup


def clean_html(text: str | None) -> str:
    """Convert HTML or HTML-escaped text into normalized plain text."""
    if not text:
        return ""

    decoded = html.unescape(text)
    soup = BeautifulSoup(decoded, "html.parser")
    return soup.get_text(separator=" ", strip=True)
