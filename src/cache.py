"""Simple file-based cache for LLM responses."""
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any


class LLmCache:
    """File-based cache for LLM responses keyed by prompt hash."""

    def __init__(self, cache_dir: Path | str = "cache", ttl_hours: float = 24):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.ttl_seconds = ttl_hours * 3600
        self.hits = 0
        self.misses = 0

    def _hash_key(self, prompt: str, model: str, system_prompt: str = "") -> str:
        """Generate cache key from prompt and model."""
        content = f"{model}:{system_prompt}:{prompt}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def get(self, prompt: str, model: str, system_prompt: str = "") -> Any | None:
        """Get cached response if available and not expired."""
        key = self._hash_key(prompt, model, system_prompt)
        cache_file = self.cache_dir / f"{key}.json"

        if not cache_file.exists():
            self.misses += 1
            return None

        try:
            data = json.loads(cache_file.read_text())
            # Check TTL
            if time.time() - data.get("timestamp", 0) > self.ttl_seconds:
                cache_file.unlink()
                self.misses += 1
                return None

            self.hits += 1
            return data.get("response")
        except (json.JSONDecodeError, KeyError, IOError):
            self.misses += 1
            return None

    def set(self, prompt: str, model: str, response: Any, system_prompt: str = "") -> None:
        """Cache a response."""
        key = self._hash_key(prompt, model, system_prompt)
        cache_file = self.cache_dir / f"{key}.json"

        data = {
            "timestamp": time.time(),
            "model": model,
            "prompt": prompt[:500],  # Truncate for debugging
            "system_prompt": system_prompt[:500] if system_prompt else "",
            "response": response,
        }

        try:
            cache_file.write_text(json.dumps(data, default=str))
        except IOError:
            pass  # Fail silently

    def clear(self) -> None:
        """Clear all cached entries."""
        for f in self.cache_dir.glob("*.json"):
            f.unlink()
        self.hits = 0
        self.misses = 0

    def stats(self) -> dict:
        """Return cache statistics."""
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{hit_rate*100:.1f}%",
            "cache_files": len(list(self.cache_dir.glob("*.json"))),
        }


_global_cache: LLmCache | None = None


def get_cache() -> LLmCache:
    """Get global cache instance."""
    global _global_cache
    if _global_cache is None:
        ttl = float(os.getenv("CACHE_TTL_HOURS", "24"))
        cache_dir = Path(os.getenv("CACHE_DIR", "cache"))
        _global_cache = LLmCache(cache_dir, ttl)
    return _global_cache
