"""
AI provider factory for Folio.

Usage:
    from wesum.ai.factory import get_provider
    provider = get_provider(config)
"""

from __future__ import annotations

import logging

from wesum.ai.base import AIProvider
from wesum.config import AIConfig

logger = logging.getLogger(__name__)


def get_provider(ai_config: AIConfig) -> AIProvider:
    """
    Instantiate and return the configured AI provider.

    Args:
        ai_config: AIConfig instance from loaded configuration.

    Returns:
        An AIProvider instance ready for use.

    Raises:
        ValueError: If provider name is unknown.
        ImportError: If required package is not installed.
    """
    provider_name = ai_config.provider
    active = ai_config.get_active()

    logger.info("Initializing AI provider: %s (model: %s)", provider_name, active.model)

    if provider_name == "openai":
        from wesum.ai.openai_provider import OpenAIProvider
        return OpenAIProvider(
            api_key=active.api_key,
            model=active.model or "gpt-4o-mini",
            base_url=active.base_url or "https://api.openai.com/v1",
            max_tokens=active.max_tokens,
            temperature=active.temperature,
        )

    elif provider_name == "claude":
        from wesum.ai.claude_provider import ClaudeProvider
        return ClaudeProvider(
            api_key=active.api_key,
            model=active.model or "claude-3-5-haiku-20241022",
            max_tokens=active.max_tokens,
            temperature=active.temperature,
        )

    elif provider_name == "qwen":
        from wesum.ai.qwen_provider import QwenProvider
        return QwenProvider(
            api_key=active.api_key,
            model=active.model or "qwen-turbo",
            base_url=active.base_url,
            max_tokens=active.max_tokens,
            temperature=active.temperature,
        )

    elif provider_name == "gemini":
        from wesum.ai.gemini_provider import GeminiProvider
        return GeminiProvider(
            api_key=active.api_key,
            model=active.model or "gemini-1.5-flash",
            max_tokens=active.max_tokens,
            temperature=active.temperature,
        )

    elif provider_name in ("deepseek", "openai-compatible"):
        # DeepSeek and other OpenAI-compatible APIs use the same client
        from wesum.ai.openai_provider import OpenAIProvider
        default_base = (
            "https://api.deepseek.com/v1" if provider_name == "deepseek"
            else "https://api.openai.com/v1"
        )
        default_model = "deepseek-chat" if provider_name == "deepseek" else "gpt-4o-mini"
        return OpenAIProvider(
            api_key=active.api_key,
            model=active.model or default_model,
            base_url=active.base_url or default_base,
            max_tokens=active.max_tokens,
            temperature=active.temperature,
        )

    else:
        raise ValueError(
            f"Unknown AI provider: '{provider_name}'. "
            f"Choose from: openai, claude, qwen, gemini, deepseek, openai-compatible"
        )
