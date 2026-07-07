#!/usr/bin/env python3
"""
Folio CLI — Command line interface for managing the knowledge base.

Usage:
    python cli.py add-url "https://mp.weixin.qq.com/s/..."
    python cli.py add-rss "https://..." --name "公众号名"
    python cli.py fetch
    python cli.py build
    python cli.py serve
    python cli.py stats
    python cli.py list
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))


def _setup(config_path: str | None = None):
    """Load config, setup logging, return (config, db, processor)."""
    from wesum.config import load_config, setup_logging
    from wesum.database import Database
    from wesum.ai import get_provider
    from wesum.processor import Processor

    cfg = load_config(config_path)
    setup_logging(cfg.logging)

    db = Database(cfg.database.path)
    ai = get_provider(cfg.ai)
    processor = Processor(cfg, db, ai)

    return cfg, db, processor


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.option("--config", "-c", default=None, help="Path to config.yaml")
@click.pass_context
def cli(ctx: click.Context, config: str | None) -> None:
    """📚 Folio — WeChat Public Account Knowledge Base Tool"""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@cli.command("add-url")
@click.argument("url")
@click.pass_context
def add_url(ctx: click.Context, url: str) -> None:
    """Fetch and process a single article URL."""
    _, _, processor = _setup(ctx.obj.get("config_path"))

    click.echo(f"🔄 Processing: {url}")
    result = processor.process_url(url)

    if result.success:
        article = result.article
        click.echo(f"✅ Added: [{article.id}] {article.title}")
        click.echo(f"   📌 {article.summary}")
        click.echo(f"   🏷️  {article.type_tag} | ⭐{article.quality_score} | {article.credibility}")
    elif result.duplicate_of:
        click.echo(f"⚠️  Duplicate of article #{result.duplicate_of}: {result.message}")
    else:
        click.echo(f"❌ Failed: {result.message}", err=True)
        sys.exit(1)


@cli.command("add-rss")
@click.argument("url")
@click.option("--name", "-n", default="", help="Display name for this feed")
@click.pass_context
def add_rss(ctx: click.Context, url: str, name: str) -> None:
    """Add a new RSS feed subscription."""
    from wesum.database import RSSFeed
    cfg, db, _ = _setup(ctx.obj.get("config_path"))

    existing = db.get_feed_by_url(url)
    if existing:
        click.echo(f"⚠️  Feed already exists: {existing.name} ({url})")
        return

    feed = RSSFeed(url=url, name=name or url, enabled=True)
    feed_id = db.insert_feed(feed)
    click.echo(f"✅ Added RSS feed #{feed_id}: {name or url}")
    click.echo(f"   Run 'python cli.py fetch' to fetch articles from this feed.")


@cli.command("fetch")
@click.pass_context
def fetch(ctx: click.Context) -> None:
    """Fetch new articles from all enabled RSS feeds."""
    _, _, processor = _setup(ctx.obj.get("config_path"))

    click.echo("🔄 Fetching from all RSS feeds...")
    summary = processor.fetch_and_process_rss()

    if not summary:
        click.echo("ℹ️  No RSS feeds configured. Use 'add-rss' to add feeds.")
        return

    total_new = 0
    total_errors = 0
    for url, stats in summary.items():
        name = stats.get("name", url)
        new = stats.get("new", 0)
        errors = stats.get("errors", 0)
        fetched = stats.get("fetched", 0)
        total_new += new
        total_errors += errors
        click.echo(f"   📡 {name}: {fetched} checked, +{new} new, {errors} errors")

    click.echo(f"\n✅ Done: {total_new} new articles added, {total_errors} errors")


@cli.command("build")
@click.pass_context
def build(ctx: click.Context) -> None:
    """Generate the static HTML knowledge base site."""
    from wesum.builder import SiteBuilder
    cfg, db, _ = _setup(ctx.obj.get("config_path"))

    click.echo(f"🔨 Building site → {cfg.site.output_dir}/")
    builder = SiteBuilder(cfg.site, db)
    builder.build()

    stats = db.get_stats()
    click.echo(f"✅ Site built: {stats['processed']} articles")
    click.echo(f"   📁 Output: {Path(cfg.site.output_dir).absolute()}/index.html")
    click.echo(f"   🌐 Run 'python cli.py serve' to preview locally")


@cli.command("serve")
@click.option("--port", "-p", default=8000, help="Port to serve on (default: 8000)")
@click.pass_context
def serve(ctx: click.Context, port: int) -> None:
    """Serve the generated static site locally."""
    import http.server
    import socketserver
    import threading
    import webbrowser

    cfg, _, _ = _setup(ctx.obj.get("config_path"))
    site_dir = Path(cfg.site.output_dir)

    if not (site_dir / "index.html").exists():
        click.echo("❌ Site not built yet. Run 'python cli.py build' first.", err=True)
        sys.exit(1)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(site_dir), **kwargs)

        def log_message(self, format, *args):
            pass  # Suppress request logs

    url = f"http://localhost:{port}"
    click.echo(f"🌐 Serving site at {url}")
    click.echo(f"   Press Ctrl+C to stop")

    threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    with socketserver.TCPServer(("", port), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            click.echo("\n👋 Stopped.")


@cli.command("list")
@click.option("--limit", "-l", default=20, help="Number of articles to show")
@click.option("--status", "-s", default="processed", help="Filter by status")
@click.option("--source", default=None, help="Filter by source")
@click.pass_context
def list_articles(ctx: click.Context, limit: int, status: str, source: str) -> None:
    """List articles in the database."""
    _, db, _ = _setup(ctx.obj.get("config_path"))

    articles = db.get_articles(status=status, source=source, limit=limit)
    if not articles:
        click.echo("ℹ️  No articles found.")
        return

    click.echo(f"\n{'ID':<6} {'Date':<12} {'Type':<6} {'⭐':<3} {'Source':<16} Title")
    click.echo("-" * 80)
    for a in articles:
        date = a.published_at.strftime("%Y-%m-%d") if a.published_at else "-"
        source_str = (a.source or "")[:14]
        title = a.title[:40] + "..." if len(a.title) > 40 else a.title
        click.echo(f"{a.id:<6} {date:<12} {a.type_tag:<6} {a.quality_score:<3} {source_str:<16} {title}")

    total = db.count_articles(status=status)
    click.echo(f"\n{len(articles)} shown / {total} total (status={status})")


@cli.command("stats")
@click.pass_context
def stats(ctx: click.Context) -> None:
    """Show database statistics."""
    import json as _json
    _, db, _ = _setup(ctx.obj.get("config_path"))

    s = db.get_stats()
    click.echo(f"\n📊 Folio Statistics")
    click.echo(f"{'─' * 40}")
    click.echo(f"  Total articles:    {s['total']}")
    click.echo(f"  Processed:         {s['processed']}")
    click.echo(f"  Pending:           {s['pending']}")
    click.echo(f"  Errors:            {s['errors']}")
    click.echo(f"  RSS feeds (active):{s['feeds']}")

    if s["type_distribution"]:
        click.echo(f"\n  📋 By Type:")
        for tag, count in s["type_distribution"].items():
            click.echo(f"    {tag}: {count}")

    if s["top_sources"]:
        click.echo(f"\n  📡 Top Sources:")
        for src, count in list(s["top_sources"].items())[:5]:
            click.echo(f"    {src}: {count}")


@cli.command("init")
@click.option("--demo", is_flag=True, default=False, help="Load demo articles (skipped if DB already has data)")
@click.pass_context
def init(ctx: click.Context, demo: bool) -> None:
    """Initialize the database and optionally load demo articles."""
    import json as _json
    from datetime import datetime
    from wesum.database import Article

    _, db, _ = _setup(ctx.obj.get("config_path"))
    click.echo("✅ Database initialized")

    if demo:
        total = db.count_articles()
        if total > 0:
            click.echo(f"⏭️  Skipping demo data — database already has {total} articles")
        else:
            demo_path = Path(__file__).parent / "data" / "demo_articles.json"
            if not demo_path.exists():
                click.echo("❌ demo_articles.json not found", err=True)
                return
            items = _json.loads(demo_path.read_text(encoding="utf-8"))
            count = 0
            for item in items:
                try:
                    pub = item.get("published_at", "")
                    pub_dt = datetime.strptime(pub, "%Y-%m-%d %H:%M:%S") if pub else None
                    article = Article(
                        url=item["url"],
                        title=item["title"],
                        author=item.get("author", ""),
                        source=item.get("source", ""),
                        published_at=pub_dt,
                        summary=item.get("summary", ""),
                        detailed_summary=item.get("detailed_summary", ""),
                        type_tag=item.get("type_tag", ""),
                        topic_tags=item.get("topic_tags", "[]"),
                        quality_score=item.get("quality_score", 0),
                        credibility=item.get("credibility", ""),
                        credibility_note=item.get("credibility_note", ""),
                        word_count=item.get("word_count", 0),
                        status=item.get("status", "processed"),
                    )
                    db.insert_article(article)
                    count += 1
                except Exception as e:
                    click.echo(f"  ⚠️  Skipped '{item.get('title', '?')}': {e}")
            click.echo(f"🎉 Loaded {count} demo articles — open the Web UI to explore!")


@cli.command("clear-demo")
@click.pass_context
def clear_demo(ctx: click.Context) -> None:
    """Remove all demo articles (URLs containing '/demo-')."""
    _, db, _ = _setup(ctx.obj.get("config_path"))
    removed = db.delete_demo_articles()
    click.echo(f"🗑️  Removed {removed} demo article(s)")


@cli.command("test-ai")
@click.pass_context
def test_ai(ctx: click.Context) -> None:
    """Test AI provider connection."""
    from wesum.config import load_config
    from wesum.ai import get_provider

    cfg = load_config(ctx.obj.get("config_path"))
    ai = get_provider(cfg.ai)
    active = cfg.ai.get_active()

    click.echo(f"🤖 Testing AI provider: {cfg.ai.provider} (model: {active.model})")

    if ai.test_connection():
        click.echo("✅ AI connection successful!")
    else:
        click.echo("❌ AI connection failed. Check your API key and model settings.", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
