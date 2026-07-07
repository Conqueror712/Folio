"""
Article fetcher for Folio.

Handles two ingestion paths:
  1. RSS feed fetching (via feedparser)
  2. Direct WeChat article URL scraping (via requests + BeautifulSoup)
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

from wesum.database import Article

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTTP session setup
# ---------------------------------------------------------------------------

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}

_WECHAT_HEADERS = {
    **_DEFAULT_HEADERS,
    "Referer": "https://mp.weixin.qq.com/",
}

_TIMEOUT = 30


def _make_session() -> requests.Session:
    """Create a requests Session with sensible defaults."""
    session = requests.Session()
    session.headers.update(_DEFAULT_HEADERS)
    return session


# ---------------------------------------------------------------------------
# WeChat article scraper
# ---------------------------------------------------------------------------

def _clean_text(text: str) -> str:
    """Strip excessive whitespace from extracted text."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _extract_wechat_article(html: str, url: str) -> dict:
    """
    Parse HTML from a WeChat article page.

    Args:
        html: Raw HTML content.
        url: Source URL (for logging).

    Returns:
        Dict with keys: title, author, source, published_at, content, word_count
    """
    soup = BeautifulSoup(html, "lxml")

    # Title
    title = ""
    title_elem = soup.find("h1", {"id": "activity-name"}) or \
                 soup.find("h1", class_=re.compile(r"rich_media_title")) or \
                 soup.find("meta", property="og:title")
    if title_elem:
        if title_elem.name == "meta":
            title = title_elem.get("content", "")
        else:
            title = title_elem.get_text(strip=True)

    if not title:
        og_title = soup.find("meta", property="og:title")
        if og_title:
            title = og_title.get("content", "")

    # Author
    author = ""
    author_elem = soup.find("strong", class_="profile-nickname") or \
                  soup.find("span", id="profileBt") or \
                  soup.find("span", class_="rich_media_meta_nickname")
    if author_elem:
        author = author_elem.get_text(strip=True)

    # Source (public account name)
    source = author  # WeChat: author is usually the account name
    source_meta = soup.find("meta", property="og:site_name")
    if source_meta:
        source = source_meta.get("content", source)

    # Published time
    published_at = None
    time_elem = soup.find("em", id="publish_time") or \
                soup.find("span", id="publish_time")
    if time_elem:
        time_text = time_elem.get_text(strip=True)
        try:
            published_at = datetime.strptime(time_text, "%Y-%m-%d")
        except ValueError:
            pass

    # Try script-based time extraction
    if not published_at:
        script_match = re.search(r'var ct\s*=\s*"(\d+)"', html)
        if script_match:
            try:
                ts = int(script_match.group(1))
                published_at = datetime.fromtimestamp(ts)
            except (ValueError, OSError):
                pass

    # Content
    content_elem = soup.find("div", id="js_content") or \
                   soup.find("div", class_="rich_media_content")

    content = ""
    if content_elem:
        # Remove script/style/img tags to get clean text
        for tag in content_elem.find_all(["script", "style", "img"]):
            tag.decompose()
        content = _clean_text(content_elem.get_text(separator="\n"))
    else:
        # Fallback: get page body text
        body = soup.find("body")
        if body:
            for tag in body.find_all(["script", "style", "nav", "header", "footer"]):
                tag.decompose()
            content = _clean_text(body.get_text(separator="\n"))

    word_count = len(content.replace(" ", "").replace("\n", ""))

    return {
        "title": title or "未知标题",
        "author": author,
        "source": source,
        "published_at": published_at,
        "content": content,
        "word_count": word_count,
    }


def _extract_generic_article(html: str, url: str) -> dict:
    """
    Generic article extractor for non-WeChat URLs.
    """
    soup = BeautifulSoup(html, "lxml")

    # Title
    title = ""
    title_elem = (
        soup.find("meta", property="og:title") or
        soup.find("h1") or
        soup.find("title")
    )
    if title_elem:
        if title_elem.name == "meta":
            title = title_elem.get("content", "")
        else:
            title = title_elem.get_text(strip=True)

    # Author
    author = ""
    author_meta = soup.find("meta", property="article:author") or \
                  soup.find("meta", attrs={"name": "author"})
    if author_meta:
        author = author_meta.get("content", "")

    # Published time
    published_at = None
    time_meta = soup.find("meta", property="article:published_time")
    if time_meta:
        try:
            dt_str = time_meta.get("content", "")
            published_at = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except ValueError:
            pass

    # Source from domain
    parsed = urlparse(url)
    source = parsed.netloc

    # Content — try main/article tags first
    content_elem = (
        soup.find("article") or
        soup.find("main") or
        soup.find("div", class_=re.compile(r"content|post|article", re.I))
    )
    if not content_elem:
        content_elem = soup.find("body")

    content = ""
    if content_elem:
        for tag in content_elem.find_all(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        content = _clean_text(content_elem.get_text(separator="\n"))

    word_count = len(content.replace(" ", "").replace("\n", ""))

    return {
        "title": title or "未知标题",
        "author": author,
        "source": source,
        "published_at": published_at,
        "content": content,
        "word_count": word_count,
    }


# ---------------------------------------------------------------------------
# Public fetcher API
# ---------------------------------------------------------------------------

def fetch_article(url: str, timeout: int = _TIMEOUT) -> Optional[Article]:
    """
    Fetch and parse an article from a URL.

    Supports WeChat articles (mp.weixin.qq.com) and generic web pages.

    Args:
        url: Full article URL.
        timeout: Request timeout in seconds.

    Returns:
        Partially populated Article object (no AI fields yet), or None on failure.
    """
    session = _make_session()
    is_wechat = "mp.weixin.qq.com" in url

    if is_wechat:
        session.headers.update(_WECHAT_HEADERS)

    try:
        logger.info("Fetching article: %s", url)
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "utf-8"
        html = response.text
    except requests.RequestException as e:
        logger.error("Failed to fetch %s: %s", url, e)
        return None

    if is_wechat:
        data = _extract_wechat_article(html, url)
    else:
        data = _extract_generic_article(html, url)

    if not data.get("content"):
        logger.warning("No content extracted from %s", url)
        return None

    article = Article(
        url=url,
        title=data["title"],
        author=data["author"],
        source=data["source"],
        published_at=data["published_at"] or datetime.now(),
        fetched_at=datetime.now(),
        content=data["content"],
        word_count=data["word_count"],
        status="pending",
    )

    logger.info(
        "Fetched: '%s' (%d chars) from %s",
        article.title,
        article.word_count,
        article.source,
    )
    return article


# ---------------------------------------------------------------------------
# RSS feed fetcher
# ---------------------------------------------------------------------------

def fetch_rss_feed(
    feed_url: str,
    max_articles: int = 20,
    timeout: int = _TIMEOUT,
) -> List[dict]:
    """
    Fetch and parse an RSS feed, returning article entries.

    Args:
        feed_url: RSS feed URL.
        max_articles: Maximum entries to return.
        timeout: Request timeout in seconds.

    Returns:
        List of dicts with keys: url, title, published_at, source
    """
    logger.info("Fetching RSS feed: %s", feed_url)

    try:
        # feedparser can accept URLs directly
        feed = feedparser.parse(feed_url, request_headers=_DEFAULT_HEADERS)
    except Exception as e:
        logger.error("feedparser error for %s: %s", feed_url, e)
        return []

    if feed.bozo and not feed.entries:
        logger.warning("RSS feed parse warning for %s: %s", feed_url, feed.bozo_exception)

    feed_title = feed.feed.get("title", feed_url)
    entries = feed.entries[:max_articles]

    results = []
    for entry in entries:
        url = entry.get("link", "")
        if not url:
            continue

        title = entry.get("title", "")

        # Parse published date
        published_at = None
        for date_field in ("published_parsed", "updated_parsed", "created_parsed"):
            parsed = entry.get(date_field)
            if parsed:
                try:
                    published_at = datetime(*parsed[:6])
                    break
                except (TypeError, ValueError):
                    pass

        results.append({
            "url": url,
            "title": title,
            "published_at": published_at,
            "source": feed_title,
        })

    logger.info("RSS feed '%s': %d entries found", feed_title, len(results))
    return results
