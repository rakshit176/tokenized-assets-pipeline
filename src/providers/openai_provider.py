"""OpenAI provider — GPT-4o, GPT-4o-mini, etc."""

from __future__ import annotations

import os
import time

from .base import BaseLLMProvider, ProviderConfig, LLMCallResult

DEFAULT_API_KEY = os.getenv("OPENAI_API_KEY", "")
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT models."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.1,
        max_concurrent: int = 3,
    ) -> None:
        super().__init__(ProviderConfig(
            api_key=api_key or os.getenv("OPENAI_API_KEY", DEFAULT_API_KEY),
            base_url=base_url or os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL),
            model=model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
            max_tokens=max_tokens,
            temperature=temperature,
            max_concurrent=max_concurrent,
        ))
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
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
            response = await client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                response_format={"type": "json_object"},
            )
            latency_ms = int((time.perf_counter() - t0) * 1000)
            usage = response.usage
            return LLMCallResult(
                content=response.choices[0].message.content or "{}",
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
                latency_ms=latency_ms,
                finish_reason=response.choices[0].finish_reason or "",
            )
        except Exception as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return LLMCallResult(
                content="{}",
                latency_ms=latency_ms,
                error=str(e)[:500],
            )
