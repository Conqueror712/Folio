"""
Abstract base class for AI providers.

All providers must implement the `analyze` method which returns a
structured AIResponse. The base class provides convenience wrappers
for individual tasks (summarize, tag, score, etc.).
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Response dataclass
# ---------------------------------------------------------------------------


@dataclass
class AIResponse:
    """Structured output from AI analysis of an article."""
    summary: str = ""              # One-sentence summary
    type_tag: str = ""             # 干货/新闻/广告/观点/其他
    topic_tags: List[str] = field(default_factory=list)  # [AI, 产品, 技术, ...]
    quality_score: int = 0         # 1-3
    credibility: str = "ok"        # ok/clickbait/exaggerated
    credibility_note: str = ""     # Explanation if not ok
    detailed_summary: str = ""     # Full structured summary (lazy-generated)
    raw: str = ""                  # Raw model output for debugging


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_ANALYZE_SYSTEM = """你是一个专业的文章分析助手，专注于微信公众号内容分析。
你需要用中文回答，输出严格的JSON格式，不要有任何额外说明。"""

_ANALYZE_PROMPT_TEMPLATE = """请分析以下文章，返回JSON格式的分析结果：

标题：{title}
正文（前2000字）：
{content}

请返回以下JSON（只返回JSON，无其他内容）：
{{
  "summary": "一句话摘要（30字以内，概括核心观点）",
  "type_tag": "文章类型（只能选一个：干货/新闻/广告/观点/其他）",
  "topic_tags": ["主题标签数组，如AI、产品、技术、商业、生活等，最多3个"],
  "quality_score": 质量评分（整数1-3，1=一般，2=不错，3=优质）,
  "credibility": "可信度（只能选一个：ok/clickbait/exaggerated）",
  "credibility_note": "如果credibility不是ok，简要说明原因；否则留空字符串"
}}"""

_DETAIL_SYSTEM = """你是一个专业的文章深度分析助手。
你需要生成结构化、带Emoji的完整摘要，帮助读者快速掌握文章精华。
用中文回答，使用Markdown格式。"""

_DETAIL_PROMPT_TEMPLATE = """请对以下文章生成详细的结构化摘要：

标题：{title}
作者：{author}
来源：{source}
正文：
{content}

请生成包含以下部分的Markdown格式摘要：

## 📌 核心观点
（2-3句话总结文章最重要的观点）

## 🔍 关键内容
（用bullet point列出3-5个关键信息/数据/结论）

## 💡 亮点摘录
（原文中最有价值的1-2个句子，加引号）

## 🎯 适合人群
（这篇文章对谁最有价值？）

## ⚡ 行动建议
（读完这篇文章，读者可以做什么？）

## 📎 相关资源
（文章中提到的工具、链接、书籍等，如无则写"无"）"""


# ---------------------------------------------------------------------------
# Abstract provider
# ---------------------------------------------------------------------------


class AIProvider(ABC):
    """
    Abstract base class for AI providers.

    Subclasses must implement `_chat_completion(messages)` which
    calls the underlying API and returns the assistant's text response.
    """

    def __init__(self, api_key: str, model: str, max_tokens: int = 2048, temperature: float = 0.3):
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    @abstractmethod
    def _chat_completion(self, messages: list[dict]) -> str:
        """
        Call the AI API with a list of chat messages.

        Args:
            messages: List of {"role": "...", "content": "..."} dicts.

        Returns:
            The assistant's text response.
        """

    def _safe_json_parse(self, text: str) -> dict:
        """Parse JSON from model output, handling markdown code fences."""
        text = text.strip()
        # Strip markdown code fences
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(
                line for line in lines if not line.strip().startswith("```")
            )
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON object from surrounding text
            import re
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        logger.warning("Failed to parse JSON from AI response: %s", text[:200])
        return {}

    def analyze(self, title: str, content: str) -> AIResponse:
        """
        Run the full analysis pipeline on an article.

        Args:
            title: Article title.
            content: Article text content (will be truncated to ~2000 chars).

        Returns:
            AIResponse with all fields populated.
        """
        truncated_content = content[:2000] if len(content) > 2000 else content
        prompt = _ANALYZE_PROMPT_TEMPLATE.format(
            title=title, content=truncated_content
        )

        messages = [
            {"role": "system", "content": _ANALYZE_SYSTEM},
            {"role": "user", "content": prompt},
        ]

        try:
            raw = self._chat_completion(messages)
        except Exception as e:
            logger.error("AI analyze failed: %s", e)
            return AIResponse(
                summary="AI分析失败",
                type_tag="其他",
                topic_tags=[],
                quality_score=1,
                credibility="ok",
                raw=str(e),
            )

        data = self._safe_json_parse(raw)

        response = AIResponse(raw=raw)
        response.summary = str(data.get("summary", "")).strip()[:100]
        response.type_tag = str(data.get("type_tag", "其他")).strip()
        response.topic_tags = list(data.get("topic_tags", []))[:5]
        try:
            score = int(data.get("quality_score", 1))
            response.quality_score = max(1, min(3, score))
        except (ValueError, TypeError):
            response.quality_score = 1
        response.credibility = str(data.get("credibility", "ok")).strip()
        response.credibility_note = str(data.get("credibility_note", "")).strip()

        # Validate type_tag
        valid_types = {"干货", "新闻", "广告", "观点", "其他"}
        if response.type_tag not in valid_types:
            response.type_tag = "其他"

        # Validate credibility
        valid_cred = {"ok", "clickbait", "exaggerated"}
        if response.credibility not in valid_cred:
            response.credibility = "ok"

        return response

    def generate_detailed_summary(
        self, title: str, content: str, author: str = "", source: str = ""
    ) -> str:
        """
        Generate a full structured Markdown summary for the detail page.

        This is called lazily (on first detail page view) and cached in DB.

        Args:
            title: Article title.
            content: Full article content.
            author: Article author.
            source: Source public account name.

        Returns:
            Markdown-formatted detailed summary string.
        """
        content_trimmed = content[:6000] if len(content) > 6000 else content
        prompt = _DETAIL_PROMPT_TEMPLATE.format(
            title=title,
            author=author or "未知",
            source=source or "未知",
            content=content_trimmed,
        )

        messages = [
            {"role": "system", "content": _DETAIL_SYSTEM},
            {"role": "user", "content": prompt},
        ]

        try:
            return self._chat_completion(messages)
        except Exception as e:
            logger.error("generate_detailed_summary failed: %s", e)
            return f"## 生成失败\n\n{e}"

    def test_connection(self) -> bool:
        """Test if the API connection works. Returns True on success."""
        try:
            result = self._chat_completion([
                {"role": "user", "content": "Reply with OK"}
            ])
            return bool(result)
        except Exception as e:
            logger.error("Connection test failed: %s", e)
            return False
