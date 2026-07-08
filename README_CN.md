# Folio

<p align="right">
  <strong>中文</strong> | <a href="README.md">English</a>
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
  <b>微信公众号 → 个人知识库</b><br>
  Folio: AI 驱动的知识沉淀引擎，不只是推送文章的转发器
</p>

---

## ✨ 功能特性

- 📥 **双入口采集**：RSS 自动拉取（需 Wechat2RSS / wewe-rss）+ 手动提交 URL
- 🤖 **多模型 AI**：支持 OpenAI · Claude · Qwen · DeepSeek 等模型，通过配置切换
- 🏷️ **智能打标签**：类型（干货 / 新闻 / 广告 / 观点）+ 主题（AI / 产品 / 技术）
- ⭐ **质量评分**：每篇文章 1-3 星评级
- 🛡️ **可信度标注**：识别标题党和夸大内容
- 📄 **HTML 输出**：可部署到 GitHub Pages 或本地直接打开
- 🧹 **去重机制**：URL 去重 + 标题相似度去重
- 🔄 **GitHub Actions**：每小时自动拉取 → 构建 → 部署
- 🗄️ **零外部依赖**：仅需 SQLite，无外部服务

## 🚀 快速开始

### Step 1. 安装

```bash
git clone https://github.com/yourusername/Folio.git
cd Folio
conda create -n Folio python=3.12 -y
conda activate Folio
pip install -r requirements.txt
```

### Step 2. 配置

编辑 `config.yaml`，最小配置如下：

```yaml
ai:
  provider: deepseek    # 或: openai | claude | gemini
  deepseek:
    api_key: "sk-your-key-here"
    model: "deepseek-v4-flash"
```

### Step 3. 添加文章

**方式 A — Web 管理界面（推荐）：**
```bash
python app.py  # 启动后在浏览器中打开 http://localhost:8080
```

**方式 B — 手动提交 URL：**
```bash
python cli.py add-url "https://mp.weixin.qq.com/s/your-article-url"
```

**方式 C — RSS 订阅（需先配置 RSS 服务，见下文 [🔧 RSS 服务配置](#rss-服务配置)）：**
```bash
python cli.py add-rss "https://your-rss-service/feed" --name "公众号名称"
python cli.py fetch
```

> 注：RSS 是一种聚合协议，可以将公众号的文章聚合，然后通过 Folio 的 RSS 订阅功能自动拉取新文章。

### Step 4. 构建并预览

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

> 注：请确认您的需求，当您真的需要自动拉取的时候再配置 RSS 服务，笔者更推荐手动添加，虽然这听起来有些麻烦，实则过犹不及，自动添加反而容易造成信息过载，缺少了用户的初筛，或许并不利于精准地沉淀有价值的内容。当然，我们尊重每个人的选择，所以这里也做了支持。

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

1. Fork 本仓库（必要步骤）
2. 进入 **Settings → Secrets → Actions**，添加：
   - `API_KEY`（或其他 AI 提供商的密钥，必填）
   - `RSS_FEED_URLS`（逗号分隔的 RSS URL，可选）
3. 进入 **Settings → Pages**，将源设置为 `gh-pages` 分支
4. 工作流每小时自动运行

## 🤔 常见问题

**Q1: 没有 AI API Key 能用吗？**
> A: 不能，AI 处理（摘要、标签、评分）需要 API Key。DeepSeek 和 Qwen 有免费额度，性价比高。

**Q2: 文章内容会存储在本地吗？**
> A: 是的，完整文章内容存储在 SQLite 中。详细摘要在首次访问时生成并缓存。

**Q3: Token 消耗大概多少？**
> A: 每篇文章初始处理约 500-1500 Token，详细页生成约 2000-4000 Token，非常便宜！