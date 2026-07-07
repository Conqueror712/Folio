"""
Configuration loader for Folio.

Reads config.yaml (or a path specified by WESUM_CONFIG env var),
validates required fields, and exposes typed config objects.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config file resolution
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_NAMES = ["config.yaml", "config.yml"]


def _find_config_file() -> Optional[Path]:
    """Search for config file: env var → cwd → script dir."""
    env_path = os.environ.get("WESUM_CONFIG")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p
        raise FileNotFoundError(f"WESUM_CONFIG points to non-existent file: {env_path}")

    for name in _DEFAULT_CONFIG_NAMES:
        p = Path(name)
        if p.exists():
            return p

    # Check parent of this file (project root)
    project_root = Path(__file__).parent.parent
    for name in _DEFAULT_CONFIG_NAMES:
        p = project_root / name
        if p.exists():
            return p

    return None


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class AIProviderConfig:
    """Configuration for a single AI provider."""
    api_key: str = ""
    model: str = ""
    base_url: str = ""
    max_tokens: int = 2048
    temperature: float = 0.3


@dataclass
class AIConfig:
    """AI configuration block."""
    provider: str = "qwen"
    openai: AIProviderConfig = field(default_factory=AIProviderConfig)
    claude: AIProviderConfig = field(default_factory=AIProviderConfig)
    qwen: AIProviderConfig = field(default_factory=AIProviderConfig)
    gemini: AIProviderConfig = field(default_factory=AIProviderConfig)
    deepseek: AIProviderConfig = field(default_factory=AIProviderConfig)

    def get_active(self) -> AIProviderConfig:
        """Return the config for the currently selected provider."""
        mapping = {
            "openai": self.openai,
            "claude": self.claude,
            "qwen": self.qwen,
            "gemini": self.gemini,
            "deepseek": self.deepseek,
        }
        # openai-compatible is an alias — use openai config
        if self.provider == "openai-compatible":
            return self.openai
        cfg = mapping.get(self.provider)
        if cfg is None:
            raise ValueError(
                f"Unknown AI provider: '{self.provider}'. "
                f"Choose from: {list(mapping.keys())}"
            )
        return cfg


@dataclass
class RSSFeedConfig:
    """A single RSS feed subscription."""
    url: str
    name: str = ""
    enabled: bool = True


@dataclass
class RSSConfig:
    """RSS configuration block."""
    feeds: List[RSSFeedConfig] = field(default_factory=list)
    fetch_interval: int = 60
    max_articles_per_feed: int = 20
    timeout: int = 30


@dataclass
class ProcessingConfig:
    """Processing pipeline configuration."""
    summarize: bool = True
    tag: bool = True
    score: bool = True
    credibility: bool = True
    dedup: bool = True
    title_similarity_threshold: float = 0.85
    max_workers: int = 3


@dataclass
class SiteConfig:
    """Static site generation configuration."""
    output_dir: str = "site"
    title: str = "Folio - My Knowledge Base"
    description: str = "Personal knowledge base from WeChat public accounts"
    author: str = ""
    language: str = "zh-CN"
    base_url: str = ""
    articles_per_page: int = 50
    search: bool = True
    default_theme: str = "auto"


@dataclass
class DatabaseConfig:
    """Database configuration."""
    path: str = "data/wesum.db"


@dataclass
class WebConfig:
    """Flask web UI configuration."""
    host: str = "127.0.0.1"
    port: int = 8080
    debug: bool = False
    secret_key: str = "change-me"


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    file: str = "data/wesum.log"
    max_size_mb: int = 10
    backup_count: int = 3


@dataclass
class Config:
    """Root configuration object."""
    ai: AIConfig = field(default_factory=AIConfig)
    rss: RSSConfig = field(default_factory=RSSConfig)
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)
    site: SiteConfig = field(default_factory=SiteConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    web: WebConfig = field(default_factory=WebConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _parse_ai(data: dict) -> AIConfig:
    ai = AIConfig()
    ai.provider = data.get("provider", "qwen")

    def _parse_provider(section: dict) -> AIProviderConfig:
        return AIProviderConfig(
            api_key=section.get("api_key", ""),
            model=section.get("model", ""),
            base_url=section.get("base_url", ""),
            max_tokens=int(section.get("max_tokens", 2048)),
            temperature=float(section.get("temperature", 0.3)),
        )

    for name in ("openai", "claude", "qwen", "gemini", "deepseek"):
        section = data.get(name, {})
        if section:
            setattr(ai, name, _parse_provider(section))

    # Apply environment variable overrides
    env_key_map = {
        "openai": "OPENAI_API_KEY",
        "claude": "ANTHROPIC_API_KEY",
        "qwen": "QWEN_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }
    for name, env_var in env_key_map.items():
        env_val = os.environ.get(env_var)
        if env_val:
            getattr(ai, name).api_key = env_val
            logger.debug("Applied %s from environment variable %s", name, env_var)

    return ai


def _parse_rss(data: dict) -> RSSConfig:
    rss = RSSConfig()
    rss.fetch_interval = int(data.get("fetch_interval", 60))
    rss.max_articles_per_feed = int(data.get("max_articles_per_feed", 20))
    rss.timeout = int(data.get("timeout", 30))

    raw_feeds = data.get("feeds", [])
    for f in raw_feeds:
        if isinstance(f, dict) and f.get("url"):
            rss.feeds.append(
                RSSFeedConfig(
                    url=f["url"],
                    name=f.get("name", f["url"]),
                    enabled=bool(f.get("enabled", True)),
                )
            )

    # Also accept RSS URLs from environment variable (comma-separated)
    env_feeds = os.environ.get("RSS_FEED_URLS", "")
    for url in env_feeds.split(","):
        url = url.strip()
        if url:
            rss.feeds.append(RSSFeedConfig(url=url, name=url))

    return rss


def load_config(path: Optional[str] = None) -> Config:
    """
    Load configuration from a YAML file.

    Args:
        path: Explicit path to config file. If None, searches standard locations.

    Returns:
        Populated Config object.

    Raises:
        FileNotFoundError: If no config file found and path not specified.
    """
    if path:
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
    else:
        config_path = _find_config_file()
        if config_path is None:
            logger.warning(
                "No config.yaml found. Using defaults. "
                "Run: cp config.example.yaml config.yaml"
            )
            return Config()

    global _last_config_path
    _last_config_path = config_path
    logger.info("Loading config from: %s", config_path)

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    cfg = Config()
    cfg.ai = _parse_ai(raw.get("ai", {}))
    cfg.rss = _parse_rss(raw.get("rss", {}))

    proc = raw.get("processing", {})
    cfg.processing = ProcessingConfig(
        summarize=bool(proc.get("summarize", True)),
        tag=bool(proc.get("tag", True)),
        score=bool(proc.get("score", True)),
        credibility=bool(proc.get("credibility", True)),
        dedup=bool(proc.get("dedup", True)),
        title_similarity_threshold=float(proc.get("title_similarity_threshold", 0.85)),
        max_workers=int(proc.get("max_workers", 3)),
    )

    site = raw.get("site", {})
    cfg.site = SiteConfig(
        output_dir=site.get("output_dir", "site"),
        title=site.get("title", "Folio - My Knowledge Base"),
        description=site.get("description", "Personal knowledge base from WeChat public accounts"),
        author=site.get("author", ""),
        language=site.get("language", "zh-CN"),
        base_url=site.get("base_url", ""),
        articles_per_page=int(site.get("articles_per_page", 50)),
        search=bool(site.get("search", True)),
        default_theme=site.get("default_theme", "auto"),
    )

    db = raw.get("database", {})
    cfg.database = DatabaseConfig(path=db.get("path", "data/wesum.db"))

    web = raw.get("web", {})
    cfg.web = WebConfig(
        host=web.get("host", "127.0.0.1"),
        port=int(web.get("port", 8080)),
        debug=bool(web.get("debug", False)),
        secret_key=web.get("secret_key", "change-me"),
    )

    log = raw.get("logging", {})
    cfg.logging = LoggingConfig(
        level=log.get("level", "INFO"),
        file=log.get("file", "data/wesum.log"),
        max_size_mb=int(log.get("max_size_mb", 10)),
        backup_count=int(log.get("backup_count", 3)),
    )

    return cfg


# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------

_last_config_path: Optional[Path] = None


def save_config(cfg: "Config", path: Optional[str] = None) -> None:
    """Persist a Config object back to YAML.

    Args:
        cfg: Config object to save.
        path: Target file path. Defaults to the last loaded config path or config.yaml.
    """
    global _last_config_path
    target = Path(path) if path else (_last_config_path or Path("config.yaml"))

    active = cfg.ai.get_active()
    data = {
        "ai": {
            "provider": cfg.ai.provider,
            cfg.ai.provider: {
                "api_key": active.api_key or "",
                "model": active.model,
                **(({"base_url": active.base_url}) if active.base_url else {}),
            },
        },
        "rss": {
            "fetch_interval": cfg.rss.fetch_interval,
            "max_articles_per_feed": cfg.rss.max_articles_per_feed,
            "feeds": [
                {"url": f.url, "name": f.name, "enabled": f.enabled}
                for f in cfg.rss.feeds
            ],
        },
        "processing": {
            "summarize": cfg.processing.summarize,
            "tag": cfg.processing.tag,
            "score": cfg.processing.score,
            "credibility": cfg.processing.credibility,
            "dedup": cfg.processing.dedup,
            "title_similarity_threshold": cfg.processing.title_similarity_threshold,
            "max_workers": cfg.processing.max_workers,
        },
        "site": {
            "output_dir": cfg.site.output_dir,
            "title": cfg.site.title,
            "description": cfg.site.description,
            "author": cfg.site.author,
            "language": cfg.site.language,
            "base_url": cfg.site.base_url,
            "articles_per_page": cfg.site.articles_per_page,
            "search": cfg.site.search,
            "default_theme": cfg.site.default_theme,
        },
        "database": {"path": cfg.database.path},
        "web": {
            "host": cfg.web.host,
            "port": cfg.web.port,
            "debug": cfg.web.debug,
            "secret_key": cfg.web.secret_key,
        },
        "logging": {
            "level": cfg.logging.level,
            "file": cfg.logging.file,
            "max_size_mb": cfg.logging.max_size_mb,
            "backup_count": cfg.logging.backup_count,
        },
    }

    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    logger.info("Config saved to: %s", target)


def setup_logging(cfg: LoggingConfig) -> None:
    """Configure root logger based on LoggingConfig."""
    import logging.handlers

    log_level = getattr(logging, cfg.level.upper(), logging.INFO)

    # Ensure log directory exists
    log_path = Path(cfg.file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handlers: list[logging.Handler] = [
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            cfg.file,
            maxBytes=cfg.max_size_mb * 1024 * 1024,
            backupCount=cfg.backup_count,
            encoding="utf-8",
        ),
    ]

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )
