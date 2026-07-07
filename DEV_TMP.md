# DEV_TMP.md — 开发备忘

> 给下一个接手这个项目的 Agent 或开发者看的。记录隐性决策和踩过的坑。

---

## 产品定位

**核心定位**：公众号阅读沉淀工具，不是推送转发器。
用户主动选择想留下的文章（粘贴 URL），而不是把订阅的所有文章全部抓下来。
RSS 自动拉取是辅助功能，手动提交 URL 才是主流程。

类比：Obsidian 的价值不是帮你写笔记，是帮你把笔记组织成知识网络。
Folio 的价值不是「AI 帮你总结」（Claude 已经能做），而是「读过的东西不会消失」。

**目标用户（v1）**：技术用户，会命令行和 git，愿意配置 API Key。

---

## 关键技术决策

- **AI 推荐 Provider**：DeepSeek（便宜、国内可用、兼容 OpenAI 接口）
- **存储**：纯 SQLite + 静态 HTML，零外部服务依赖
- **部署**：用户 fork 自己的仓库，GitHub Pages 自动部署，作者仓库零压力
- **详细摘要**：懒加载 + 缓存到 SQLite，点击时实时生成
- **演示数据**：`python cli.py init --demo` 加载，URL 含 `/demo-` 以便识别和清除

---

## 容易踩的坑

### Article dataclass 字段
```python
# 正确字段名
article.source       # ✅ 来源公众号名称
article.published_at # ✅ datetime 对象

# 不存在的字段（别用）
article.source_name  # ❌ 不存在
```

### get_stats() 返回结构
```python
{
    "total_articles": int,   # 文章总数（用于 Dashboard 卡片）
    "total_feeds": int,      # 订阅源总数
    "total_tags": int,
    "avg_quality": float,
    "processed": int,        # 已处理（用于 navbar 状态栏）
    "pending": int,
    "errors": int,
    "feeds": int,            # 同 total_feeds，navbar 用这个键
}
```

### index() 路由必须同时传两个键
```python
return render_template(
    "index.html",
    status=get_status(),      # 页面内容用
    status_dict=get_status(), # base.html navbar 用
    ...
)
```
其他路由只需要传 `status_dict=get_status()`。

### DeepSeek 路由
DeepSeek 兼容 OpenAI 接口，在 `ai/factory.py` 里直接复用 `OpenAIProvider`，
只是 `base_url` 改为 `https://api.deepseek.com/v1`，`model` 默认 `deepseek-chat`。

### data-raw 属性中的换行符
Jinja2 模板里把 `detailed_summary` 放进 HTML attribute 时，
换行符会破坏 attribute，必须先转义：
```jinja2
data-raw="{{ article.detailed_summary | replace('\n', '&#10;') | replace('\r', '') | e }}"
```
JS 读取时再还原：
```js
const raw = el.dataset.raw.replace(/&#10;/g, '\n');
```

---

## 文件结构速查

```
Folio/
├── app.py              # Flask Web UI 入口（localhost:8080）
├── cli.py              # CLI 入口
├── config.example.yaml # 配置模板（含 DeepSeek 配置段）
├── wesum/
│   ├── config.py       # 配置加载，Config dataclass
│   ├── database.py     # SQLite CRUD，Database 类
│   ├── processor.py    # AI 处理流水线，Processor 类
│   ├── fetcher.py      # RSS 拉取 + 微信文章爬取
│   ├── builder.py      # 静态 HTML 生成器
│   ├── dedup.py        # 去重逻辑
│   └── ai/
│       ├── base.py     # 抽象基类 AIProvider
│       ├── factory.py  # get_provider(ai_config) 工厂函数
│       ├── openai_provider.py   # OpenAI + DeepSeek + 兼容接口
│       ├── qwen_provider.py
│       ├── claude_provider.py
│       └── gemini_provider.py
├── web/templates/      # 12 个 Jinja2 模板（全中文）
├── data/
│   ├── demo_articles.json  # 10 篇演示文章
│   └── folio.db            # SQLite 数据库（运行后生成）
└── site/               # 生成的静态 HTML（git ignore）
```

---

## 常用命令

```bash
# 初始化 + 加载演示数据
python cli.py init --demo

# 添加一篇文章
python cli.py add-url "https://mp.weixin.qq.com/s/..."

# 生成静态站点
python cli.py build

# 启动本地 Web UI
python app.py   # 访问 http://localhost:8080

# 清除演示数据
python cli.py clear-demo
```
