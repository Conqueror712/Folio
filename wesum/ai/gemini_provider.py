"""
Google Gemini provider implementation for Folio.

Supports gemini-1.5-pro, gemini-1.5-flash, and other Gemini models.
"""

from __future__ import annotations

import logging

from wesum.ai.base import AIProvider

logger = logging.getLogger(__name__)


class GeminiProvider(AIProvider):
    """
    AI provider backed by Google's Gemini API.

    Configuration example (config.yaml):
        ai:
          provider: gemini
          gemini:
            api_key: "your-api-key"
            model: "gemini-1.5-flash"
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-1.5-flash",
        max_tokens: int = 2048,
        temperature: float = 0.3,
        base_url: str = "",
    ) -> None:
        super().__init__(api_key=api_key, model=model, max_tokens=max_tokens, temperature=temperature)
        self._genai = None

    def _get_genai(self):
        """Lazily initialize the Google generativeai client."""
        if self._genai is None:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._genai = genai
            except ImportError:
                raise ImportError(
                    "google-generativeai package not installed. "
                    "Run: pip install google-generativeai"
                )
        return self._genai

    def _chat_completion(self, messages: list[dict]) -> str:
        genai = self._get_genai()

        model = genai.GenerativeModel(
            model_name=self.model,
            generation_config={
                "max_output_tokens": self.max_tokens,
                "temperature": self.temperature,
            },
        )

        # Convert messages to Gemini's format
        # Merge system + user messages into a single conversation
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"[System]: {content}")
            else:
                parts.append(content)

        combined_prompt = "\n\n".join(parts)

        logger.debug("Gemini request: model=%s", self.model)
        response = model.generate_content(combined_prompt)
        return response.text if response.text else ""
