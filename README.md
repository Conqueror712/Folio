# Folio

<p align="right">
  <a href="README_CN.md">中文</a> | <strong>English</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/License-MIT-cyan" alt="License">
  <img src="https://img.shields.io/badge/Deploy-GitHub%20Pages-red?logo=github" alt="GitHub Pages">
  <img src="https://img.shields.io/badge/AI-Multi--Model-orange" alt="AI">
  <img src="https://img.shields.io/badge/Storage-SQLite-lightblue" alt="SQLite">
  <img src="https://img.shields.io/badge/UI-Flask-green" alt="UI">
</p>

<p align="center">
  <b>WeChat Public Account → Personal Knowledge Base</b><br>
  Folio: An AI-powered knowledge distillation engine, not just another feed reader.
</p>

---

## ✨ Features

- 📥 **Dual ingestion**: RSS auto-fetch (via Wechat2RSS / wewe-rss) + manual URL submission
- 🤖 **Multi-model AI**: OpenAI · Claude · Qwen · DeepSeek — swap via config
- 🏷️ **Smart tagging**: Type (tutorial / news / ad / opinion) + Topic (AI / product / tech)
- ⭐ **Quality scoring**: 1–3 star rating per article
- 🛡️ **Credibility check**: Flags clickbait and exaggerated claims
- 📄 **Static HTML output**: Deploy to GitHub Pages or open locally
- 🧹 **Deduplication**: URL + title similarity dedup
- 🔄 **GitHub Actions**: Auto-fetch → build → deploy every hour
- 🗄️ **Zero dependencies**: SQLite only, no external services required

## 🚀 Quick Start

### Step 1. Install

```bash
git clone https://github.com/yourusername/Folio.git
cd Folio
conda create -n Folio python=3.12 -y
conda activate Folio
pip install -r requirements.txt
```

### Step 2. Configure

Edit `config.yaml` with your AI provider (minimum required):

```yaml
ai:
  provider: deepseek    # or: openai | claude | gemini
  deepseek:
    api_key: "sk-your-key-here"
    model: "deepseek-v4-flash"
```

### Step 3. Add Articles

**Option A — Web UI (recommended):**
```bash
python app.py  # Open http://localhost:8080 in your browser
```

**Option B — Manual URL:**
```bash
python cli.py add-url "https://mp.weixin.qq.com/s/your-article-url"
```

**Option C — RSS Feed (requires RSS service setup first, see [🔧 RSS Service Setup](#-rss-service-setup)):**
```bash
python cli.py add-rss "https://your-rss-service/feed" --name "Account Name"
python cli.py fetch
```

> Note: RSS is a feed aggregation protocol that allows Folio to automatically pull new articles from WeChat public accounts.

### Step 4. Build & Preview

```bash
python cli.py build
python cli.py serve
# Open http://localhost:8000
```

## 📖 CLI Reference

```
python cli.py [COMMAND] [OPTIONS]

Commands:
  add-url    Add article by URL and process immediately
  add-rss    Add RSS subscription feed
  fetch      Fetch new articles from all RSS feeds
  build      Generate static HTML site
  serve      Serve the generated site locally
  list       List all articles in the database
  stats      Show database statistics
```

## 🔧 RSS Service Setup

> Note: Only set this up if you genuinely need automatic fetching. The author actually recommends manual URL submission instead — it sounds more tedious, but automatic ingestion can easily cause information overload. Without a first-pass filter by the user, it may not help you distill content that truly matters. That said, we respect everyone's workflow, so RSS is fully supported.

Folio requires a third-party service to convert WeChat public accounts into RSS feeds:

| Service | Description | URL |
|---------|-------------|-----|
| **Wechat2RSS** | Self-hostable, free | [xlab.app](https://wechat2rss.xlab.app) |
| **wewe-rss** | Open source, Docker-based | [GitHub](https://github.com/cooderl/wewe-rss) |
| **RSSHub** | Universal RSS hub | [rsshub.app](https://rsshub.app) |

## 🚢 Deploy to GitHub Pages

### Manual Deploy

```bash
python cli.py build
git subtree push --prefix site origin gh-pages
```

### Automatic Deploy (GitHub Actions)

1. Fork this repository (required)
2. Go to **Settings → Secrets → Actions**, add:
   - `API_KEY` (your AI provider's key, required)
   - `RSS_FEED_URLS` (comma-separated RSS URLs, optional)
3. Go to **Settings → Pages**, set source to `gh-pages` branch
4. The workflow runs every hour automatically

## 🤔 FAQ

**Q: Can I use this without an AI API key?**
> No — summarization, tagging, and scoring all require an API call. DeepSeek and Qwen both offer free trial credits and are very affordable.

**Q: Does article content get stored locally?**
> Yes. Full text is stored in SQLite on your machine. Detailed summaries are generated on first access and cached.

**Q: How much does it cost per article?**
> ~500–1500 tokens for initial processing (summary + tags + score). Detailed page: ~2000–4000 tokens. Very cheap!
