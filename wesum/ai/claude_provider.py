"""
Anthropic Claude provider implementation for Folio.

Supports claude-3-5-sonnet, claude-3-5-haiku, and other Claude models.
"""

from __future__ import annotations

import logging

from wesum.ai.base import AIProvider

logger = logging.getLogger(__name__)


class ClaudeProvider(AIProvider):
    """
    AI provider backed by Anthropic's Claude API.

    Configuration example (config.yaml):
        ai:
          provider: claude
          claude:
            api_key: "sk-ant-..."
            model: "claude-3-5-haiku-20241022"
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-5-haiku-20241022",
        max_tokens: int = 2048,
        temperature: float = 0.3,
        base_url: str = "",
    ) -> None:
        super().__init__(api_key=api_key, model=model, max_tokens=max_tokens, temperature=temperature)
        self._client = None

    def _get_client(self):
        """Lazily initialize the Anthropic client."""
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError(
                    "anthropic package not installed. Run: pip install anthropic"
                )
        return self._client

    def _chat_completion(self, messages: list[dict]) -> str:
        client = self._get_client()

        # Claude API separates system and user messages
        system_content = ""
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            else:
                user_messages.append(msg)

        logger.debug("Claude request: model=%s", self.model)
        response = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system_content,
            messages=user_messages,
        )
        return response.content[0].text if response.content else ""
