# Folio

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/许可证-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/AI-多模型-orange" alt="AI">
  <img src="https://img.shields.io/badge/存储-SQLite-lightblue" alt="SQLite">
  <img src="https://img.shields.io/badge/部署-GitHub%20Pages-black?logo=github" alt="GitHub Pages">
</p>

<p align="center">
  <b>微信公众号文章 → 个人知识库</b><br>
  不只是推送转发器，是由 AI 驱动的知识沉淀引擎。
</p>

---

## ✨ 功能特性

- 📥 **双入口采集**：RSS 自动拉取（需 Wechat2RSS/wewe-rss）+ 手动提交 URL
- 🤖 **多模型 AI**：OpenAI · Claude · 通义千问 · Gemini，通过配置切换
- 🏷️ **智能打标签**：类型（干货/新闻/广告/观点）+ 主题（AI/产品/技术）
- ⭐ **质量评分**：每篇文章 1-3 星评级
- 🛡️ **可信度标注**：识别标题党和夸大内容
- 🔍 **全文搜索**：纯前端 Fuse.js，无需后端
- 🌙 **深色/浅色主题**：自动跟随系统设置
- 📄 **静态 HTML 输出**：可部署到 GitHub Pages 或本地直接打开
- 🧹 **去重机制**：URL 去重 + 标题相似度去重
- 🔄 **GitHub Actions**：每小时自动拉取 → 构建 → 部署
- 💻 **本地 Web UI**：Flask 管理面板，访问 `localhost:8080`
- 🗄️ **零外部依赖**：仅需 SQLite，无外部服务

## 🚀 快速开始

### 1. 克隆并安装

```bash
git clone https://github.com/yourusername/Folio.git
cd Folio
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置

```bash
cp config.example.yaml config.yaml
```

编辑 `config.yaml`，至少配置 AI 提供商：

```yaml
ai:
  provider: qwen    # 或: openai | claude | gemini
  qwen:
    api_key: "sk-your-key-here"
    model: "qwen-turbo"
```

### 3. 添加文章

**方式 A — 手动提交 URL（最快验证）：**
```bash
python cli.py add-url "https://mp.weixin.qq.com/s/your-article-url"
```

**方式 B — RSS 订阅：**
```bash
python cli.py add-rss "https://your-rss-service/feed" --name "公众号名称"
python cli.py fetch
```

**方式 C — Web 管理界面：**
```bash
python app.py
# 打开 http://localhost:8080
```

### 4. 构建并预览

```bash
python cli.py build
python cli.py serve
# 打开 http://localhost:8000
```

## 📖 CLI 命令参考

```
python cli.py [命令] [选项]

命令:
  add-url    通过 URL 添加文章并立即处理
  add-rss    添加 RSS 订阅源
  fetch      从所有 RSS 源拉取新文章
  build      生成静态 HTML 网站
  serve      在本地预览生成的网站
  list       列出数据库中所有文章
  stats      显示数据库统计信息
```

## 🔧 RSS 服务配置

Folio 需要第三方服务将公众号转换为 RSS：

| 服务 | 描述 | 地址 |
|------|------|------|
| **Wechat2RSS** | 可自托管，免费 | [xlab.app](https://wechat2rss.xlab.app) |
| **wewe-rss** | 开源，支持 Docker | [GitHub](https://github.com/cooderl/wewe-rss) |
| **RSSHub** | 通用 RSS 聚合 | [rsshub.app](https://rsshub.app) |

## 🚢 部署到 GitHub Pages

### 手动部署

```bash
python cli.py build
git subtree push --prefix site origin gh-pages
```

### 自动部署（GitHub Actions）

1. Fork 本仓库
2. 进入 **Settings → Secrets → Actions**，添加：
   - `QWEN_API_KEY`（或其他 AI 提供商的密钥）
   - `RSS_FEED_URLS`（逗号分隔的 RSS URL，可选）
3. 进入 **Settings → Pages**，将源设置为 `gh-pages` 分支
4. 工作流每小时自动运行

## ❓ 常见问题

**Q: 没有 AI API Key 能用吗？**
> A: 不能，AI 处理（摘要、标签、评分）需要 API Key。通义千问有免费额度且对中文内容效果最好。

**Q: 文章内容会存储在本地吗？**
> A: 是的，完整文章内容存储在 SQLite 中。详细摘要在首次访问时生成并缓存。

**Q: Token 消耗大概多少？**
> A: 每篇文章初始处理约 500-1500 Token，详细页生成约 2000-4000 Token。使用 `qwen-turbo` 成本可忽略不计。

## 📜 许可证

MIT 许可证 — 详见 [LICENSE](LICENSE)。
