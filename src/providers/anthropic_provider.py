"""Anthropic provider — Claude models via Anthropic API."""

from __future__ import annotations

import os
import time

from .base import BaseLLMProvider, ProviderConfig, LLMCallResult

DEFAULT_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DEFAULT_MODEL = "claude-sonnet-4-20250514"


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude models (Sonnet, Haiku, Opus)."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.1,
        max_concurrent: int = 3,
    ) -> None:
        super().__init__(ProviderConfig(
            api_key=api_key or os.getenv("ANTHROPIC_API_KEY", DEFAULT_API_KEY),
            base_url="https://api.anthropic.com",
            model=model or os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL),
            max_tokens=max_tokens,
            temperature=temperature,
            max_concurrent=max_concurrent,
        ))
        self._client = None

    def _get_client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic(
                api_key=self.config.api_key,
                timeout=self.config.timeout,
                max_retries=2,
            )
        return self._client

    async def complete(self, system: str, user: str) -> str:
        result = await self.complete_with_usage(system, user)
        return result.content

    async def complete_with_usage(self, system: str, user: str) -> LLMCallResult:
        client = self._get_client()
        t0 = time.perf_counter()
        try:
            response = await client.messages.create(
                model=self.config.model,
                system=system,
                messages=[{"role": "user", "content": user}],
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
            latency_ms = int((time.perf_counter() - t0) * 1000)
            content = response.content[0].text if response.content else "{}"
            usage = response.usage
            return LLMCallResult(
                content=content,
                prompt_tokens=usage.input_tokens if usage else 0,
                completion_tokens=usage.output_tokens if usage else 0,
                total_tokens=(usage.input_tokens + usage.output_tokens) if usage else 0,
                latency_ms=latency_ms,
                finish_reason=response.stop_reason or "",
            )
        except Exception as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return LLMCallResult(
                content="{}",
                latency_ms=latency_ms,
                error=str(e)[:500],
            )
