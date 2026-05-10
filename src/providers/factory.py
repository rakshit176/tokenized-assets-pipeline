"""Provider factory — select LLM provider via LLM_PROVIDER env var."""

from __future__ import annotations

import os

from .base import BaseLLMProvider
from .zai_provider import ZAIProvider
from .openai_provider import OpenAIProvider
from .anthropic_provider import AnthropicProvider
from .openrouter_provider import OpenRouterProvider

PROVIDERS: dict[str, type[BaseLLMProvider]] = {
    "zai": ZAIProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "openrouter": OpenRouterProvider,
}


def get_provider(name: str | None = None) -> BaseLLMProvider:
    """Return an instantiated provider based on name or LLM_PROVIDER env var.

    Falls back to 'zai' if not specified.
    """
    provider_name = (name or os.getenv("LLM_PROVIDER", "zai")).lower().strip()
    cls = PROVIDERS.get(provider_name)
    if cls is None:
        raise ValueError(
            f"Unknown provider '{provider_name}'. "
            f"Available: {', '.join(PROVIDERS)}"
        )
    return cls()
