"""
OpenAI provider implementation for Folio.

Supports GPT-4o, GPT-4o-mini, GPT-3.5-turbo, and any OpenAI-compatible
endpoint (e.g., Azure OpenAI, local proxies).
"""

from __future__ import annotations

import logging

from wesum.ai.base import AIProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(AIProvider):
    """
    AI provider backed by OpenAI's chat completions API.

    Configuration example (config.yaml):
        ai:
          provider: openai
          openai:
            api_key: "sk-..."
            model: "gpt-4o-mini"
            base_url: "https://api.openai.com/v1"
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> None:
        super().__init__(api_key=api_key, model=model, max_tokens=max_tokens, temperature=temperature)
        self.base_url = base_url
        self._client = None

    def _get_client(self):
        """Lazily initialize the OpenAI client."""
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            except ImportError:
                raise ImportError(
                    "openai package not installed. Run: pip install openai"
                )
        return self._client

    def _chat_completion(self, messages: list[dict]) -> str:
        client = self._get_client()
        logger.debug("OpenAI request: model=%s, messages=%d", self.model, len(messages))
        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        return response.choices[0].message.content or ""
