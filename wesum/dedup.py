"""
Deduplication engine for Folio.

Provides two deduplication strategies:
  1. URL-based: Exact URL match (handled by DB unique constraint)
  2. Title-based: Fuzzy title similarity using SequenceMatcher

Both checks are performed before inserting an article.
"""

from __future__ import annotations

import logging
from difflib import SequenceMatcher
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


def _normalize_title(title: str) -> str:
    """Normalize title for comparison: lowercase, strip punctuation/spaces."""
    import re
    # Remove common WeChat title suffixes/prefixes
    title = re.sub(r"[【】\[\]《》「」『』\(\)（）]", " ", title)
    title = re.sub(r"\s+", " ", title)
    return title.strip().lower()


def title_similarity(title_a: str, title_b: str) -> float:
    """
    Compute similarity ratio between two titles.

    Uses SequenceMatcher for a balance of speed and accuracy.

    Args:
        title_a: First title string.
        title_b: Second title string.

    Returns:
        Float between 0.0 (completely different) and 1.0 (identical).
    """
    a = _normalize_title(title_a)
    b = _normalize_title(title_b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


class DedupEngine:
    """
    Checks new articles for duplicates against existing database entries.

    Usage:
        engine = DedupEngine(db, threshold=0.85)
        dup_id = engine.find_duplicate_title("新文章标题")
        if dup_id:
            print(f"Duplicate of article #{dup_id}")
    """

    def __init__(self, threshold: float = 0.85) -> None:
        """
        Args:
            threshold: Similarity score above which articles are considered duplicates.
                       0.85 works well for Chinese article titles.
        """
        self.threshold = threshold
        self._title_cache: List[Tuple[int, str]] = []  # (id, normalized_title)

    def load_titles(self, titles: List[Tuple[int, str]]) -> None:
        """
        Load existing (id, title) pairs from the database.

        Args:
            titles: List of (article_id, title) tuples.
        """
        self._title_cache = [
            (article_id, _normalize_title(title))
            for article_id, title in titles
        ]
        logger.debug("DedupEngine loaded %d titles", len(self._title_cache))

    def find_duplicate_title(self, new_title: str) -> Optional[int]:
        """
        Search for an existing article with a similar title.

        Args:
            new_title: Title of the new article to check.

        Returns:
            ID of the duplicate article if found, else None.
        """
        normalized = _normalize_title(new_title)
        if not normalized:
            return None

        best_score = 0.0
        best_id: Optional[int] = None

        for article_id, existing_title in self._title_cache:
            score = SequenceMatcher(None, normalized, existing_title).ratio()
            if score > best_score:
                best_score = score
                best_id = article_id

        if best_score >= self.threshold:
            logger.info(
                "Duplicate detected: '%s' ~ existing #%d (score=%.2f)",
                new_title,
                best_id,
                best_score,
            )
            return best_id

        return None

    def add_title(self, article_id: int, title: str) -> None:
        """Add a newly inserted article to the in-memory cache."""
        self._title_cache.append((article_id, _normalize_title(title)))
