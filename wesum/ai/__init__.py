"""
AI provider package for Folio.

Usage:
    from wesum.ai import get_provider
    provider = get_provider(config)
    summary = provider.summarize(title, content)
"""

from wesum.ai.base import AIProvider, AIResponse
from wesum.ai.factory import get_provider

__all__ = ["AIProvider", "AIResponse", "get_provider"]
