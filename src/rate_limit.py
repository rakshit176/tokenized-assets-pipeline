"""Rate limiting protection for LLM API calls.

Provides token-based rate limiting to stay within API quotas and prevent
429 errors. Tracks usage per provider and implements exponential backoff.
"""
import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RateLimit:
    """Rate limit configuration for a provider."""
    requests_per_minute: int = 60
    requests_per_hour: int = 3000
    tokens_per_minute: int = 90000
    retry_after_base: int = 3  # Base retry delay in seconds
    max_retries: int = 5


# Provider-specific limits (conservative defaults)
PROVIDER_LIMITS = {
    "openai": RateLimit(
        requests_per_minute=50,
        requests_per_hour=3000,
        tokens_per_minute=90000,
    ),
    "zai": RateLimit(
        requests_per_minute=30,
        requests_per_hour=1000,
        tokens_per_minute=40000,
    ),
    "anthropic": RateLimit(
        requests_per_minute=50,
        requests_per_hour=2000,
        tokens_per_minute=80000,
    ),
    "openrouter": RateLimit(
        requests_per_minute=20,
        requests_per_hour=500,
        tokens_per_minute=30000,
    ),
}


class RateLimiter:
    """Token-based rate limiter with sliding window tracking."""

    def __init__(self, limits: dict[str, RateLimit] | None = None):
        self.limits = limits or PROVIDER_LIMITS
        self._request_times: dict[str, list[float]] = defaultdict(list)
        self._token_usage: dict[str, list[tuple[float, int]]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._last_429: dict[str, float] = {}  # Track last 429 per provider

    async def acquire(
        self,
        provider: str,
        estimated_tokens: int = 0,
    ) -> None:
        """Wait until a request can be made for the provider.

        Args:
            provider: Provider name (e.g., "openai", "zai")
            estimated_tokens: Estimated tokens for this request (for limiting)
        """
        limit = self.limits.get(provider, RateLimit())

        # Check if we were recently rate limited
        last_429 = self._last_429.get(provider, 0)
        if last_429:
            wait_time = last_429 + limit.retry_after_base - time.time()
            if wait_time > 0:
                logger.info(f"Rate limit cooldown for {provider}: waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
                del self._last_429[provider]

        async with self._lock:
            now = time.time()

            # Clean old entries (older than 1 hour)
            cutoff = now - 3600
            self._request_times[provider] = [
                t for t in self._request_times[provider] if t > cutoff
            ]
            self._token_usage[provider] = [
                (t, tok) for t, tok in self._token_usage[provider] if t > cutoff
            ]

            # Check per-minute limits
            minute_ago = now - 60
            recent_requests = [
                t for t in self._request_times[provider] if t > minute_ago
            ]
            recent_tokens = sum(
                tok for t, tok in self._token_usage[provider] if t > minute_ago
            )

            # Wait if we'd exceed limits
            if len(recent_requests) >= limit.requests_per_minute:
                oldest = min(recent_requests)
                wait_time = 60 - (now - oldest) + 0.1
                logger.debug(
                    f"{provider}: RPM limit, waiting {wait_time:.1f}s "
                    f"({len(recent_requests)}/{limit.requests_per_minute})"
                )
                await asyncio.sleep(wait_time)

            if recent_tokens + estimated_tokens > limit.tokens_per_minute:
                # Need to wait for token bucket to drain
                tokens_over = (recent_tokens + estimated_tokens) - limit.tokens_per_minute
                wait_time = (tokens_over / limit.tokens_per_minute) * 60 + 0.5
                logger.debug(
                    f"{provider}: TPM limit, waiting {wait_time:.1f}s "
                    f"({recent_tokens + estimated_tokens}/{limit.tokens_per_minute} tokens)"
                )
                await asyncio.sleep(wait_time)

            # Check per-hour limits
            hour_ago = now - 3600
            hour_requests = [
                t for t in self._request_times[provider] if t > hour_ago
            ]
            if len(hour_requests) >= limit.requests_per_hour:
                oldest = min(hour_requests)
                wait_time = 3600 - (now - oldest) + 1.0
                logger.warning(
                    f"{provider}: Hourly limit hit, waiting {wait_time:.1f}s "
                    f"({len(hour_requests)}/{limit.requests_per_hour})"
                )
                await asyncio.sleep(wait_time)

            # Record this request
            self._request_times[provider].append(now)
            if estimated_tokens:
                self._token_usage[provider].append((now, estimated_tokens))

    def record_429(self, provider: str) -> None:
        """Record that we got a 429 error from this provider."""
        self._last_429[provider] = time.time()
        logger.warning(f"Recorded 429 for {provider}, will back off")

    def record_usage(
        self,
        provider: str,
        actual_tokens: int,
    ) -> None:
        """Update token usage after request completes.

        Args:
            provider: Provider name
            actual_tokens: Actual tokens used in the request
        """
        now = time.time()
        # Find the most recent request and update its token count
        if self._token_usage[provider]:
            # Replace the last entry with actual tokens
            self._token_usage[provider][-1] = (now, actual_tokens)

    def get_stats(self, provider: str) -> dict[str, Any]:
        """Get current rate limit stats for a provider."""
        now = time.time()
        minute_ago = now - 60
        hour_ago = now - 3600

        recent_requests = [
            t for t in self._request_times[provider] if t > minute_ago
        ]
        hour_requests = [
            t for t in self._request_times[provider] if t > hour_ago
        ]
        recent_tokens = sum(
            tok for t, tok in self._token_usage[provider] if t > minute_ago
        )

        limit = self.limits.get(provider, RateLimit())

        return {
            "provider": provider,
            "requests_last_minute": len(recent_requests),
            "requests_limit_rpm": limit.requests_per_minute,
            "requests_last_hour": len(hour_requests),
            "requests_limit_rph": limit.requests_per_hour,
            "tokens_last_minute": recent_tokens,
            "tokens_limit_tpm": limit.tokens_per_minute,
            "last_429_seconds_ago": now - self._last_429.get(provider, 0),
        }


_global_limiter: RateLimiter | None = None


def get_limiter() -> RateLimiter:
    """Get global rate limiter instance."""
    global _global_limiter
    if _global_limiter is None:
        _global_limiter = RateLimiter()
    return _global_limiter
