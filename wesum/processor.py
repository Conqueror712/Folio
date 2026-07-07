"""
Article processing pipeline for Folio.

Orchestrates:
  1. Content fetching
  2. Deduplication check
  3. AI analysis (summary, tags, score, credibility)
  4. Database insertion
  5. Processing log
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from wesum.ai.base import AIProvider
from wesum.config import Config
from wesum.database import Article, Database
from wesum.dedup import DedupEngine
from wesum.fetcher import fetch_article, fetch_rss_feed

logger = logging.getLogger(__name__)


class ProcessingResult:
    """Result of processing a single article."""

    def __init__(
        self,
        success: bool,
        article: Optional[Article] = None,
        message: str = "",
        duplicate_of: Optional[int] = None,
    ) -> None:
        self.success = success
        self.article = article
        self.message = message
        self.duplicate_of = duplicate_of

    def __repr__(self) -> str:
        return f"ProcessingResult(success={self.success}, message={self.message!r})"


class Processor:
    """
    Main article processing pipeline.

    Usage:
        processor = Processor(config, db, ai_provider)
        result = processor.process_url("https://mp.weixin.qq.com/s/xxx")
    """

    def __init__(self, config: Config, db: Database, ai_provider: AIProvider) -> None:
        self.config = config
        self.db = db
        self.ai = ai_provider
        self._dedup = DedupEngine(
            threshold=config.processing.title_similarity_threshold
        )
        self._dedup_loaded = False

    def _ensure_dedup_loaded(self) -> None:
        """Lazily load titles for deduplication."""
        if not self._dedup_loaded:
            titles = self.db.get_all_titles()
            self._dedup.load_titles(titles)
            self._dedup_loaded = True

    def process_url(self, url: str) -> ProcessingResult:
        """
        Full pipeline: fetch → dedup → AI → store.

        Args:
            url: Article URL to process.

        Returns:
            ProcessingResult indicating success or failure.
        """
        logger.info("Processing URL: %s", url)

        # Step 1: URL dedup (check DB)
        if self.db.article_exists(url):
            msg = f"URL already in database: {url}"
            logger.info(msg)
            self.db.log_action(url, "process_url", "skipped", msg)
            return ProcessingResult(success=False, message=msg)

        # Step 2: Fetch content
        article = fetch_article(url, timeout=self.config.rss.timeout)
        if article is None:
            msg = f"Failed to fetch article content: {url}"
            logger.error(msg)
            self.db.log_action(url, "fetch", "error", msg)
            return ProcessingResult(success=False, message=msg)

        # Step 3: Title dedup
        if self.config.processing.dedup:
            self._ensure_dedup_loaded()
            dup_id = self._dedup.find_duplicate_title(article.title)
            if dup_id is not None:
                msg = f"Duplicate title detected (similar to article #{dup_id}): {article.title}"
                logger.info(msg)
                self.db.log_action(url, "dedup", "skipped", msg)
                return ProcessingResult(
                    success=False, message=msg, duplicate_of=dup_id
                )

        # Step 4: AI analysis
        article = self._run_ai_analysis(article)

        # Step 5: Insert into database
        try:
            article.status = "processed"
            article_id = self.db.insert_article(article)
            article.id = article_id

            # Update dedup cache
            if self.config.processing.dedup:
                self._dedup.add_title(article_id, article.title)

            self.db.log_action(url, "process_url", "success", f"Article #{article_id} inserted")
            logger.info("Article #%d inserted: %s", article_id, article.title)
            return ProcessingResult(success=True, article=article, message="OK")

        except Exception as e:
            msg = f"Database insert failed: {e}"
            logger.error(msg)
            self.db.log_action(url, "insert", "error", msg)
            return ProcessingResult(success=False, message=msg)

    def _run_ai_analysis(self, article: Article) -> Article:
        """
        Run AI analysis on an article and populate AI fields.

        Safe: catches exceptions and falls back to defaults.
        """
        proc = self.config.processing

        if not (proc.summarize or proc.tag or proc.score or proc.credibility):
            logger.info("AI processing disabled, skipping: %s", article.url)
            article.summary = article.title
            return article

        try:
            logger.info("Running AI analysis: %s", article.title)
            response = self.ai.analyze(article.title, article.content)

            if proc.summarize:
                article.summary = response.summary or article.title[:50]

            if proc.tag:
                article.type_tag = response.type_tag
                article.topic_tags = json.dumps(response.topic_tags, ensure_ascii=False)

            if proc.score:
                article.quality_score = response.quality_score

            if proc.credibility:
                article.credibility = response.credibility
                article.credibility_note = response.credibility_note

        except Exception as e:
            logger.error("AI analysis failed for %s: %s", article.url, e)
            article.summary = article.title[:80] if article.title else "摘要生成失败"
            article.type_tag = "其他"
            article.topic_tags = "[]"
            article.quality_score = 1
            article.credibility = "ok"

        return article

    def fetch_and_process_rss(self) -> dict:
        """
        Fetch all enabled RSS feeds and process new articles.

        Returns:
            Summary dict: {feed_url: {"fetched": N, "new": N, "errors": N}}
        """
        feeds = self.db.get_feeds()
        enabled_feeds = [f for f in feeds if f.enabled]

        if not enabled_feeds:
            logger.info("No enabled RSS feeds configured")
            return {}

        summary = {}

        for feed in enabled_feeds:
            logger.info("Processing RSS feed: %s (%s)", feed.name, feed.url)
            try:
                entries = fetch_rss_feed(
                    feed.url,
                    max_articles=self.config.rss.max_articles_per_feed,
                    timeout=self.config.rss.timeout,
                )
            except Exception as e:
                logger.error("RSS fetch error for %s: %s", feed.url, e)
                summary[feed.url] = {"fetched": 0, "new": 0, "errors": 1}
                continue

            new_count = 0
            error_count = 0

            for entry in entries:
                url = entry.get("url", "")
                if not url:
                    continue

                if self.db.article_exists(url):
                    continue

                result = self.process_url(url)
                if result.success:
                    new_count += 1
                elif "Failed to fetch" in result.message or "error" in result.message.lower():
                    error_count += 1

            # Update feed stats
            self.db.update_feed_fetched(feed.id, new_count)

            summary[feed.url] = {
                "name": feed.name,
                "fetched": len(entries),
                "new": new_count,
                "errors": error_count,
            }
            logger.info(
                "Feed '%s': %d entries, %d new, %d errors",
                feed.name,
                len(entries),
                new_count,
                error_count,
            )

        return summary

    def get_or_generate_detailed_summary(self, article_id: int) -> str:
        """
        Return cached detailed summary, or generate and cache it.

        This implements the lazy-load pattern for detail pages.

        Args:
            article_id: Database ID of the article.

        Returns:
            Markdown-formatted detailed summary string.
        """
        article = self.db.get_article_by_id(article_id)
        if not article:
            return "## 文章不存在"

        # Return cached version if available
        if article.detailed_summary:
            return article.detailed_summary

        # Generate and cache
        logger.info("Generating detailed summary for article #%d", article_id)
        try:
            detailed = self.ai.generate_detailed_summary(
                title=article.title,
                content=article.content,
                author=article.author,
                source=article.source,
            )
            self.db.update_detailed_summary(article_id, detailed)
            return detailed
        except Exception as e:
            logger.error("Failed to generate detailed summary for #%d: %s", article_id, e)
            return f"## 摘要生成失败\n\n{e}"
