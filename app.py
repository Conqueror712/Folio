#!/usr/bin/env python3
"""
Folio Flask Web UI — Local administration panel.

Run: python app.py
Open: http://localhost:8080

Features:
  - RSS subscription management
  - Manual article URL submission
  - Task status / logs
  - Settings editor
  - One-click static site rebuild
  - Lazy detailed summary generation
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, url_for

sys.path.insert(0, str(Path(__file__).parent))

from wesum.ai import get_provider
from wesum.builder import SiteBuilder
from wesum.config import load_config, setup_logging
from wesum.database import Database, RSSFeed
from wesum.processor import Processor

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(
    __name__,
    template_folder="web/templates",
    static_folder="web/static",
)

cfg = load_config()
app.secret_key = cfg.web.secret_key

setup_logging(cfg.logging)
logger = logging.getLogger(__name__)

db = Database(cfg.database.path)
ai = get_provider(cfg.ai)
processor = Processor(cfg, db, ai)

# Ensure data directories exist
Path("data").mkdir(exist_ok=True)
Path("site").mkdir(exist_ok=True)

# In-memory task queue for the UI
task_queue = []
task_history = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_status() -> dict:
    """Return current system status summary."""
    stats = db.get_stats()
    return {
        "processed": stats.get("processed", stats.get("total_articles", 0)),
        "pending": stats.get("pending", 0),
        "errors": stats.get("errors", 0),
        "feeds": stats.get("feeds", stats.get("total_feeds", 0)),
        "queue": len(task_queue),
        "is_running": len(task_queue) > 0,
    }


def safe_redirect(url: str):
    """Redirect helper that falls back safely."""
    return redirect(url)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Dashboard / overview page."""
    articles = db.get_articles(status="processed", limit=10)
    feeds = db.get_feeds()
    logs = db.get_recent_logs(limit=10)
    stats = db.get_stats()

    # Check if all visible articles are demo articles
    total = db.count_articles()
    demo_count = 0
    if total > 0:
        with db._cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM articles WHERE url LIKE '%/demo-%'")
            demo_count = cur.fetchone()[0]
    demo_mode = total > 0 and demo_count == total

    return render_template(
        "index.html",
        articles=articles,
        feeds=feeds,
        logs=logs,
        stats=stats,
        status=get_status(),
        status_dict=get_status(),
        demo_mode=demo_mode,
    )


@app.route("/articles")
def articles():
    """List all articles in the database."""
    page = request.args.get("page", 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page

    all_articles = db.get_articles(
        status=request.args.get("status"),
        source=request.args.get("source"),
        limit=per_page,
        offset=offset,
    )
    total = db.count_articles(status=request.args.get("status"))
    sources = db.get_sources()

    return render_template(
        "articles.html",
        articles=all_articles,
        page=page,
        per_page=per_page,
        total=total,
        sources=sources,
        status=request.args.get("status"),
        source_filter=request.args.get("source"),
        status_dict=get_status(),
    )


@app.route("/articles/<int:article_id>")
def article_detail(article_id: int):
    """Show article detail and trigger summary if needed."""
    article = db.get_article_by_id(article_id)
    if not article:
        return render_template("error.html", message="Article not found"), 404

    generated_summary = None
    if request.args.get("generate") == "1" and not article.detailed_summary:
        generated_summary = processor.get_or_generate_detailed_summary(article_id)
        article = db.get_article_by_id(article_id)  # refresh

    related = []
    if article.status == "processed":
        candidates = db.get_articles(status="processed", limit=200)
        scored = []
        for c in candidates:
            if c.id == article.id:
                continue
            score = 0
            if c.type_tag == article.type_tag:
                score += 1
            shared = set(article.topic_tags_list()) & set(c.topic_tags_list())
            score += len(shared)
            if score > 0:
                scored.append((score, c))
        scored.sort(key=lambda x: -x[0])
        related = [r[1] for r in scored[:5]]

    return render_template(
        "article_detail.html",
        article=article,
        related=related,
        generated_summary=generated_summary,
        status_dict=get_status(),
    )


@app.route("/articles/<int:article_id>/regenerate", methods=["POST"])
def regenerate_summary(article_id: int):
    """Force regenerate the detailed summary for an article."""
    article = db.get_article_by_id(article_id)
    if not article:
        return jsonify({"success": False, "error": "Article not found"}), 404

    try:
        db.update_detailed_summary(article_id, "")
        summary = processor.get_or_generate_detailed_summary(article_id)
        return jsonify({"success": True, "summary": summary})
    except Exception as e:
        logger.error("Regenerate failed: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/clear-demo", methods=["POST"])
def clear_demo():
    """Remove demo articles."""
    removed = db.delete_demo_articles()
    logger.info("Removed %d demo articles", removed)
    return redirect(url_for("index"))


@app.route("/feeds")
def feeds():
    """RSS feed management page."""
    all_feeds = db.get_feeds()
    return render_template(
        "feeds.html",
        feeds=all_feeds,
        status_dict=get_status(),
    )


@app.route("/feeds/add", methods=["POST"])
def add_feed():
    """Add a new RSS feed."""
    url = request.form.get("url", "").strip()
    name = request.form.get("name", "").strip()

    if not url:
        return render_template("error.html", message="URL is required"), 400

    existing = db.get_feed_by_url(url)
    if existing:
        return render_template("error.html", message="Feed already exists"), 409

    feed = RSSFeed(url=url, name=name or url, enabled=True)
    db.insert_feed(feed)
    db.log_action(url, "add_feed", "success", f"Name: {name or url}")

    return redirect(url_for("feeds"))


@app.route("/feeds/<int:feed_id>/delete", methods=["POST"])
def delete_feed(feed_id: int):
    """Delete an RSS feed."""
    if db.delete_feed(feed_id):
        db.log_action("", "delete_feed", "success", f"Feed #{feed_id} deleted")
    return redirect(url_for("feeds"))


@app.route("/feeds/<int:feed_id>/fetch", methods=["POST"])
def fetch_single_feed(feed_id: int):
    """Fetch articles from a single RSS feed."""
    feed = next((f for f in db.get_feeds() if f.id == feed_id), None)
    if not feed:
        return jsonify({"success": False, "error": "Feed not found"}), 404

    def do_fetch():
        task_history.append({
            "action": f"fetch_feed:{feed_id}",
            "status": "running",
            "started": time.time(),
        })
        try:
            from wesum.fetcher import fetch_rss_feed
            entries = fetch_rss_feed(feed.url, cfg.rss.max_articles_per_feed)
            new_count = 0
            for entry in entries:
                if not db.article_exists(entry["url"]):
                    result = processor.process_url(entry["url"])
                    if result.success:
                        new_count += 1
            db.update_feed_fetched(feed_id, new_count)
            task_history[-1].update({"status": "done", "new": new_count, "fetched": len(entries)})
        except Exception as e:
            task_history[-1].update({"status": "error", "error": str(e)})

    thread = threading.Thread(target=do_fetch, daemon=True)
    thread.start()

    return redirect(url_for("feeds"))


@app.route("/submit-url", methods=["GET", "POST"])
def submit_url():
    """Manual URL submission page."""
    if request.method == "GET":
        return render_template(
            "submit_url.html",
            status_dict=get_status(),
        )

    url = request.form.get("url", "").strip()
    if not url:
        return render_template("error.html", message="URL is required"), 400

    def do_process():
        task_history.append({
            "action": f"process_url:{url}",
            "status": "running",
            "started": time.time(),
        })
        try:
            result = processor.process_url(url)
            task_history[-1].update({
                "status": "done" if result.success else "skipped",
                "message": result.message,
            })
        except Exception as e:
            task_history[-1].update({"status": "error", "error": str(e)})

    thread = threading.Thread(target=do_process, daemon=True)
    thread.start()

    # Give immediate feedback
    time.sleep(0.3)
    return redirect(url_for("logs"))


@app.route("/build", methods=["POST"])
def build_site():
    """Rebuild the static HTML site."""
    def do_build():
        task_history.append({
            "action": "build_site",
            "status": "running",
            "started": time.time(),
        })
        try:
            builder = SiteBuilder(cfg.site, db)
            builder.build()
            stats = db.get_stats()
            task_history[-1].update({
                "status": "done",
                "articles": stats["processed"],
            })
        except Exception as e:
            task_history[-1].update({"status": "error", "error": str(e)})

    thread = threading.Thread(target=do_build, daemon=True)
    thread.start()

    return redirect(url_for("index"))


@app.route("/settings", methods=["GET", "POST"])
def settings():
    """Configuration editor page."""
    config_path = Path("config.yaml")

    if request.method == "POST":
        content = request.form.get("config_content", "")
        try:
            # Validate YAML syntax
            import yaml
            yaml.safe_load(content)
            config_path.write_text(content, encoding="utf-8")
            return redirect(url_for("settings"))
        except Exception as e:
            return render_template(
                "settings.html",
                config_content=content,
                error=str(e),
                status_dict=get_status(),
            )

    if config_path.exists():
        content = config_path.read_text(encoding="utf-8")
    else:
        content = Path("config.example.yaml").read_text(encoding="utf-8")

    return render_template(
        "settings.html",
        config_content=content,
        status_dict=get_status(),
    )


@app.route("/logs")
def logs():
    """Processing logs page."""
    recent_logs = db.get_recent_logs(limit=100)
    return render_template(
        "logs.html",
        logs=recent_logs,
        task_history=task_history[-50:],
        status_dict=get_status(),
    )


@app.route("/api/status")
def api_status():
    """JSON status endpoint for AJAX polling."""
    return jsonify(get_status())



@app.route("/api/stats")
def api_stats():
    """JSON statistics endpoint."""
    return jsonify(db.get_stats())


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", message="Page not found"), 404


@app.errorhandler(500)
def internal_error(e):
    logger.exception("Internal server error")
    return render_template("error.html", message="Internal server error"), 500


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    host = cfg.web.host
    port = cfg.web.port
    debug = cfg.web.debug

    print(f"🚀 Folio Web UI: http://{host}:{port}")
    print("   Press Ctrl+C to stop")

    app.run(host=host, port=port, debug=debug)
