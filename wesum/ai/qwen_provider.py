"""
Alibaba Cloud Qwen (通义千问) provider implementation for Folio.

Uses the OpenAI-compatible endpoint provided by DashScope.
Supports qwen-turbo, qwen-plus, qwen-max.

Best choice for Chinese content — recommended for most users.
"""

from __future__ import annotations

import logging

from wesum.ai.base import AIProvider

logger = logging.getLogger(__name__)

_QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class QwenProvider(AIProvider):
    """
    AI provider backed by Alibaba Cloud's Qwen models via DashScope.

    Uses the OpenAI-compatible API interface, so the openai SDK is used.

    Configuration example (config.yaml):
        ai:
          provider: qwen
          qwen:
            api_key: "sk-..."
            model: "qwen-turbo"
            base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
    """

    def __init__(
        self,
        api_key: str,
        model: str = "qwen-turbo",
        base_url: str = _QWEN_BASE_URL,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> None:
        super().__init__(api_key=api_key, model=model, max_tokens=max_tokens, temperature=temperature)
        self.base_url = base_url or _QWEN_BASE_URL
        self._client = None

    def _get_client(self):
        """Lazily initialize the OpenAI client pointed at DashScope."""
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                )
            except ImportError:
                raise ImportError(
                    "openai package not installed. Run: pip install openai"
                )
        return self._client

    def _chat_completion(self, messages: list[dict]) -> str:
        client = self._get_client()
        logger.debug("Qwen request: model=%s, messages=%d", self.model, len(messages))
        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        return response.choices[0].message.content or ""
