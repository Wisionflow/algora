"""Relevance scoring for incoming messages."""

from . import config


def compute_relevance(text: str) -> float:
    """Simple keyword-based relevance score (0.0 – 1.0)."""
    if not text:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for kw in config.RELEVANCE_KEYWORDS if kw in text_lower)
    # Normalize: 3+ hits → 1.0
    return min(hits / 3.0, 1.0)
