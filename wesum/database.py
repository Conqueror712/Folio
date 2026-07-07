"""
SQLite database layer for Folio.

Schema:
  - articles: main article store
  - rss_feeds: RSS subscription management
  - processing_log: task history
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Generator, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class Article:
    """Represents a single article in the knowledge base."""
    id: Optional[int] = None
    url: str = ""
    title: str = ""
    author: str = ""
    source: str = ""           # Public account name
    published_at: Optional[datetime] = None
    fetched_at: Optional[datetime] = None
    content: str = ""          # Raw HTML/text content
    summary: str = ""          # One-sentence AI summary
    detailed_summary: str = "" # Full structured AI summary (cached)
    type_tag: str = ""         # 干货/新闻/广告/观点
    topic_tags: str = ""       # JSON array of topic tags
    quality_score: int = 0     # 1-3 stars
    credibility: str = ""      # ok/clickbait/exaggerated
    credibility_note: str = "" # Explanation
    word_count: int = 0
    status: str = "pending"    # pending/processed/error
    error_msg: str = ""
    created_at: Optional[datetime] = None

    def topic_tags_list(self) -> List[str]:
        """Parse topic_tags JSON field to list."""
        if not self.topic_tags:
            return []
        try:
            return json.loads(self.topic_tags)
        except (json.JSONDecodeError, TypeError):
            return [self.topic_tags] if self.topic_tags else []

    def quality_stars(self) -> str:
        """Return star emoji string."""
        return "⭐" * max(0, min(3, self.quality_score))


@dataclass
class RSSFeed:
    """Represents an RSS subscription."""
    id: Optional[int] = None
    url: str = ""
    name: str = ""
    enabled: bool = True
    last_fetched_at: Optional[datetime] = None
    article_count: int = 0
    created_at: Optional[datetime] = None


@dataclass
class ProcessingLog:
    """Processing task history entry."""
    id: Optional[int] = None
    article_url: str = ""
    action: str = ""
    status: str = ""
    message: str = ""
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Database class
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS articles (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    url              TEXT    NOT NULL UNIQUE,
    title            TEXT    NOT NULL DEFAULT '',
    author           TEXT    NOT NULL DEFAULT '',
    source           TEXT    NOT NULL DEFAULT '',
    published_at     TEXT,
    fetched_at       TEXT,
    content          TEXT    NOT NULL DEFAULT '',
    summary          TEXT    NOT NULL DEFAULT '',
    detailed_summary TEXT    NOT NULL DEFAULT '',
    type_tag         TEXT    NOT NULL DEFAULT '',
    topic_tags       TEXT    NOT NULL DEFAULT '[]',
    quality_score    INTEGER NOT NULL DEFAULT 0,
    credibility      TEXT    NOT NULL DEFAULT '',
    credibility_note TEXT    NOT NULL DEFAULT '',
    word_count       INTEGER NOT NULL DEFAULT 0,
    status           TEXT    NOT NULL DEFAULT 'pending',
    error_msg        TEXT    NOT NULL DEFAULT '',
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rss_feeds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT    NOT NULL UNIQUE,
    name            TEXT    NOT NULL DEFAULT '',
    enabled         INTEGER NOT NULL DEFAULT 1,
    last_fetched_at TEXT,
    article_count   INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS processing_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    article_url TEXT    NOT NULL DEFAULT '',
    action      TEXT    NOT NULL DEFAULT '',
    status      TEXT    NOT NULL DEFAULT '',
    message     TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_articles_url       ON articles(url);
CREATE INDEX IF NOT EXISTS idx_articles_status    ON articles(status);
CREATE INDEX IF NOT EXISTS idx_articles_source    ON articles(source);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_type_tag  ON articles(type_tag);
"""

_DT_FMT = "%Y-%m-%d %H:%M:%S"


def _dt_to_str(dt: Optional[datetime]) -> Optional[str]:
    return dt.strftime(_DT_FMT) if dt else None


def _str_to_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.strptime(s, _DT_FMT)
    except ValueError:
        # Try ISO format fallback
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None


def _row_to_article(row: sqlite3.Row) -> Article:
    return Article(
        id=row["id"],
        url=row["url"],
        title=row["title"],
        author=row["author"],
        source=row["source"],
        published_at=_str_to_dt(row["published_at"]),
        fetched_at=_str_to_dt(row["fetched_at"]),
        content=row["content"],
        summary=row["summary"],
        detailed_summary=row["detailed_summary"],
        type_tag=row["type_tag"],
        topic_tags=row["topic_tags"],
        quality_score=row["quality_score"],
        credibility=row["credibility"],
        credibility_note=row["credibility_note"],
        word_count=row["word_count"],
        status=row["status"],
        error_msg=row["error_msg"],
        created_at=_str_to_dt(row["created_at"]),
    )


def _row_to_feed(row: sqlite3.Row) -> RSSFeed:
    return RSSFeed(
        id=row["id"],
        url=row["url"],
        name=row["name"],
        enabled=bool(row["enabled"]),
        last_fetched_at=_str_to_dt(row["last_fetched_at"]),
        article_count=row["article_count"],
        created_at=_str_to_dt(row["created_at"]),
    )


class Database:
    """SQLite database wrapper with simple ORM methods."""

    def __init__(self, db_path: str = "data/wesum.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def _cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._cursor() as cur:
            cur.executescript(_SCHEMA_SQL)
        logger.debug("Database schema initialized: %s", self.db_path)

    # ------------------------------------------------------------------
    # Article CRUD
    # ------------------------------------------------------------------

    def article_exists(self, url: str) -> bool:
        """Check if article URL is already in database."""
        with self._cursor() as cur:
            cur.execute("SELECT 1 FROM articles WHERE url = ?", (url,))
            return cur.fetchone() is not None

    def insert_article(self, article: Article) -> int:
        """
        Insert a new article. Returns the new row ID.
        Raises sqlite3.IntegrityError if URL already exists.
        """
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO articles (
                    url, title, author, source, published_at, fetched_at,
                    content, summary, detailed_summary, type_tag, topic_tags,
                    quality_score, credibility, credibility_note, word_count,
                    status, error_msg
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article.url,
                    article.title,
                    article.author,
                    article.source,
                    _dt_to_str(article.published_at),
                    _dt_to_str(article.fetched_at),
                    article.content,
                    article.summary,
                    article.detailed_summary,
                    article.type_tag,
                    article.topic_tags or "[]",
                    article.quality_score,
                    article.credibility,
                    article.credibility_note,
                    article.word_count,
                    article.status,
                    article.error_msg,
                ),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def update_article(self, article: Article) -> None:
        """Update all fields of an existing article by ID."""
        if article.id is None:
            raise ValueError("Cannot update article without ID")
        with self._cursor() as cur:
            cur.execute(
                """
                UPDATE articles SET
                    title=?, author=?, source=?, published_at=?, fetched_at=?,
                    content=?, summary=?, detailed_summary=?, type_tag=?,
                    topic_tags=?, quality_score=?, credibility=?,
                    credibility_note=?, word_count=?, status=?, error_msg=?
                WHERE id=?
                """,
                (
                    article.title,
                    article.author,
                    article.source,
                    _dt_to_str(article.published_at),
                    _dt_to_str(article.fetched_at),
                    article.content,
                    article.summary,
                    article.detailed_summary,
                    article.type_tag,
                    article.topic_tags or "[]",
                    article.quality_score,
                    article.credibility,
                    article.credibility_note,
                    article.word_count,
                    article.status,
                    article.error_msg,
                    article.id,
                ),
            )

    def update_detailed_summary(self, article_id: int, detailed_summary: str) -> None:
        """Cache the detailed summary for an article."""
        with self._cursor() as cur:
            cur.execute(
                "UPDATE articles SET detailed_summary=? WHERE id=?",
                (detailed_summary, article_id),
            )

    def get_article_by_id(self, article_id: int) -> Optional[Article]:
        """Fetch article by primary key."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM articles WHERE id=?", (article_id,))
            row = cur.fetchone()
            return _row_to_article(row) if row else None

    def get_article_by_url(self, url: str) -> Optional[Article]:
        """Fetch article by URL."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM articles WHERE url=?", (url,))
            row = cur.fetchone()
            return _row_to_article(row) if row else None

    def get_articles(
        self,
        status: Optional[str] = None,
        type_tag: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 1000,
        offset: int = 0,
        order_by: str = "published_at DESC",
    ) -> List[Article]:
        """
        Query articles with optional filters.

        Args:
            status: Filter by processing status.
            type_tag: Filter by article type.
            source: Filter by source public account.
            limit: Max results to return.
            offset: Pagination offset.
            order_by: SQL ORDER BY clause.

        Returns:
            List of Article objects.
        """
        conditions = []
        params: list = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if type_tag:
            conditions.append("type_tag = ?")
            params.append(type_tag)
        if source:
            conditions.append("source = ?")
            params.append(source)

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"SELECT * FROM articles {where_clause} ORDER BY {order_by} LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._cursor() as cur:
            cur.execute(sql, params)
            return [_row_to_article(row) for row in cur.fetchall()]

    def get_all_titles(self) -> List[tuple[int, str]]:
        """Return (id, title) pairs for deduplication."""
        with self._cursor() as cur:
            cur.execute("SELECT id, title FROM articles WHERE status='processed'")
            return [(row["id"], row["title"]) for row in cur.fetchall()]

    def count_articles(self, status: Optional[str] = None) -> int:
        """Count articles, optionally filtered by status."""
        with self._cursor() as cur:
            if status:
                cur.execute("SELECT COUNT(*) FROM articles WHERE status=?", (status,))
            else:
                cur.execute("SELECT COUNT(*) FROM articles")
            return cur.fetchone()[0]

    def get_sources(self) -> List[str]:
        """Return distinct source public account names."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT DISTINCT source FROM articles WHERE source != '' ORDER BY source"
            )
            return [row[0] for row in cur.fetchall()]

    def get_type_tags(self) -> List[str]:
        """Return distinct type tags."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT DISTINCT type_tag FROM articles WHERE type_tag != '' ORDER BY type_tag"
            )
            return [row[0] for row in cur.fetchall()]

    def delete_article(self, article_id: int) -> bool:
        """Delete an article by ID. Returns True if deleted."""
        with self._cursor() as cur:
            cur.execute("DELETE FROM articles WHERE id=?", (article_id,))
            return cur.rowcount > 0

    # ------------------------------------------------------------------
    # RSS Feed CRUD
    # ------------------------------------------------------------------

    def get_feeds(self) -> List[RSSFeed]:
        """Return all RSS subscriptions."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM rss_feeds ORDER BY created_at DESC")
            return [_row_to_feed(row) for row in cur.fetchall()]

    def get_feed_by_url(self, url: str) -> Optional[RSSFeed]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM rss_feeds WHERE url=?", (url,))
            row = cur.fetchone()
            return _row_to_feed(row) if row else None

    def insert_feed(self, feed: RSSFeed) -> int:
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO rss_feeds (url, name, enabled) VALUES (?, ?, ?)",
                (feed.url, feed.name, int(feed.enabled)),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def update_feed_fetched(self, feed_id: int, article_count_delta: int = 0) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                UPDATE rss_feeds
                SET last_fetched_at=datetime('now'),
                    article_count=article_count + ?
                WHERE id=?
                """,
                (article_count_delta, feed_id),
            )

    def delete_feed(self, feed_id: int) -> bool:
        with self._cursor() as cur:
            cur.execute("DELETE FROM rss_feeds WHERE id=?", (feed_id,))
            return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Processing Log
    # ------------------------------------------------------------------

    def log_action(self, url: str, action: str, status: str, message: str = "") -> None:
        """Record a processing event."""
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO processing_log (article_url, action, status, message) VALUES (?,?,?,?)",
                (url, action, status, message),
            )

    def get_recent_logs(self, limit: int = 100) -> List[ProcessingLog]:
        """Return recent processing log entries."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM processing_log ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            return [
                ProcessingLog(
                    id=row["id"],
                    article_url=row["article_url"],
                    action=row["action"],
                    status=row["status"],
                    message=row["message"],
                    created_at=_str_to_dt(row["created_at"]),
                )
                for row in cur.fetchall()
            ]

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Web UI helpers
    # ------------------------------------------------------------------

    def delete_demo_articles(self) -> int:
        """Remove demo articles (those with '/demo-' in their URL). Returns count removed."""
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM articles WHERE url LIKE '%/demo-%'")
            count = cur.fetchone()[0]
            cur.execute("DELETE FROM articles WHERE url LIKE '%/demo-%'")
        return count

    def initialize(self) -> None:
        """Public alias for _init_schema — call on startup."""
        self._init_schema()

    def get_stats(self) -> dict:
        """Return stats dict shaped for the dashboard."""
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM articles")
            total_articles = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM articles WHERE status='processed'")
            processed = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM articles WHERE status='pending'")
            pending = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM articles WHERE status='error'")
            errors = cur.fetchone()[0]

            cur.execute("SELECT COUNT(DISTINCT type_tag) FROM articles WHERE type_tag != '' AND type_tag IS NOT NULL")
            total_tags = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM rss_feeds WHERE enabled=1")
            total_feeds = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM rss_feeds")
            feeds = cur.fetchone()[0]

            cur.execute("SELECT AVG(quality_score) FROM articles WHERE quality_score IS NOT NULL AND quality_score > 0")
            row = cur.fetchone()
            avg_quality = row[0] if row and row[0] else 0.0

        return {
            # Dashboard cards
            "total_articles": total_articles,
            "total_tags": total_tags,
            "total_feeds": total_feeds,
            "avg_quality": avg_quality,
            # Status bar (used by get_status() in app.py)
            "processed": processed,
            "pending": pending,
            "errors": errors,
            "feeds": feeds,
        }

    def get_articles_list(self, limit: int = 20, offset: int = 0) -> list:
        """Return a list of articles as plain dicts for templates."""
        with self._cursor() as cur:
            cur.execute(
                """SELECT id, title, url, source, source_name, published_at,
                          summary, type_tag AS content_type, topic_tags AS tags,
                          quality_score, credibility, status
                   FROM articles
                   ORDER BY published_at DESC, created_at DESC
                   LIMIT ? OFFSET ?""",
                (limit, offset),
            )
            return [dict(row) for row in cur.fetchall()]

    def search_articles(
        self,
        query: str = "",
        tag: str = "",
        source: str = "",
        limit: int = 20,
        offset: int = 0,
    ) -> tuple:
        """Search articles with optional filters. Returns (rows, total)."""
        conditions = []
        params: list = []

        if query:
            conditions.append("(title LIKE ? OR summary LIKE ?)")
            params += [f"%{query}%", f"%{query}%"]
        if tag:
            conditions.append("type_tag = ?")
            params.append(tag)
        if source:
            conditions.append("source_name = ?")
            params.append(source)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        with self._cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM articles {where}", params)
            total = cur.fetchone()[0]

            cur.execute(
                f"""SELECT id, title, url, source, source_name, published_at,
                           summary, type_tag AS content_type, topic_tags AS tags,
                           quality_score, credibility, status
                    FROM articles {where}
                    ORDER BY published_at DESC, created_at DESC
                    LIMIT ? OFFSET ?""",
                params + [limit, offset],
            )
            rows = [dict(row) for row in cur.fetchall()]

        return rows, total

    def get_all_tags(self) -> list:
        """Return all distinct type tags."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT DISTINCT type_tag FROM articles WHERE type_tag != '' AND type_tag IS NOT NULL ORDER BY type_tag"
            )
            return [row[0] for row in cur.fetchall()]

    def get_all_sources(self) -> list:
        """Return all distinct source names."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT DISTINCT source_name FROM articles WHERE source_name != '' AND source_name IS NOT NULL ORDER BY source_name"
            )
            return [row[0] for row in cur.fetchall()]

    def get_article(self, article_id: int) -> dict | None:
        """Return a single article as a plain dict, or None."""
        with self._cursor() as cur:
            cur.execute(
                """SELECT id, title, url, source, source_name, published_at,
                          summary, detailed_summary, type_tag AS content_type,
                          topic_tags AS tags, quality_score, credibility, status
                   FROM articles WHERE id = ?""",
                (article_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def url_exists(self, url: str) -> bool:
        """Check whether a URL is already in the database."""
        return self.article_exists(url)


    def get_related_articles(self, article_id: int, limit: int = 5) -> list:
        """Return articles with the same type_tag, excluding the given id."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT type_tag FROM articles WHERE id = ?", (article_id,)
            )
            row = cur.fetchone()
            if not row or not row[0]:
                return []
            tag = row[0]
            cur.execute(
                """SELECT id, title, source_name, published_at
                   FROM articles
                   WHERE type_tag = ? AND id != ?
                   ORDER BY published_at DESC
                   LIMIT ?""",
                (tag, article_id, limit),
            )
            return [dict(r) for r in cur.fetchall()]
