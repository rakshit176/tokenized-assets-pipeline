"""Base LLM provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ProviderConfig:
    api_key: str
    base_url: str
    model: str
    timeout: int = 90
    max_tokens: int = 8192
    temperature: float = 0.1
    max_concurrent: int = 1


@dataclass
class LLMCallResult:
    """Result from a single LLM API call with usage metadata."""
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0
    finish_reason: str = ""
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None


class BaseLLMProvider(ABC):
    """All providers implement this interface."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    @abstractmethod
    async def complete(self, system: str, user: str) -> str:
        """Send a chat completion request and return the raw text response."""
        ...

    @abstractmethod
    async def complete_with_usage(self, system: str, user: str) -> LLMCallResult:
        """Send a chat completion request and return result with usage metadata."""
        ...
