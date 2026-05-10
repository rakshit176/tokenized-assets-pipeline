"""Async SearXNG search client — the sole search backend for the pipeline.

Provides:
- Single and parallel search with rate limiting and retry
- deep_search: 20 targeted queries covering all 14 schema tables
- gap_search: targeted queries for missing data fields
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


@dataclass
class SearchResult:
    """A single search result from SearXNG."""

    title: str
    url: str
    snippet: str
    rank: int
    engine: str

    def __repr__(self) -> str:
        return (
            f"SearchResult(title={self.title!r}, url={self.url!r}, "
            f"rank={self.rank}, engine={self.engine!r})"
        )


class SearXNGClient:
    """Async client for querying a SearXNG instance.

    Features:
    - Rate-limited concurrent requests
    - Automatic retry with exponential backoff
    - URL deduplication for parallel searches
    - deep_search and gap_search for pipeline integration
    """

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("SEARXNG_URL", "")).rstrip("/")
        if not self.base_url:
            self.base_url = "http://localhost:8888"
        self._semaphore = asyncio.Semaphore(4)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_params(
        self,
        query: str,
        categories: str = "general",
        pageno: int = 1,
    ) -> dict[str, Any]:
        return {
            "q": query,
            "format": "json",
            "categories": categories,
            "pageno": pageno,
        }

    def _parse_results(self, data: dict[str, Any], max_results: int) -> list[SearchResult]:
        results: list[SearchResult] = []
        raw_results = data.get("results", [])

        for idx, item in enumerate(raw_results[:max_results]):
            title = item.get("title", "")
            url = item.get("url", "")
            snippet = item.get("content", "")
            engines = item.get("engines", [])
            engine = ", ".join(engines) if isinstance(engines, list) else str(engines)

            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    rank=idx + 1,
                    engine=engine,
                )
            )

        return results

    @retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _request(self, params: dict[str, Any]) -> dict[str, Any]:
        async with self._semaphore:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/search",
                    params=params,
                )
                response.raise_for_status()
                return response.json()

    # ------------------------------------------------------------------
    # Public API — basic search
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        categories: str = "general",
        max_results: int = 10,
    ) -> list[SearchResult]:
        """Search SearXNG and return a list of SearchResult objects."""
        params = self._build_params(query, categories)
        data = await self._request(params)
        return self._parse_results(data, max_results)

    async def parallel_search(
        self,
        queries: list[str],
        max_results: int = 8,
    ) -> dict[str, list[dict[str, Any]]]:
        """Run multiple search queries concurrently with deduplication."""
        semaphore = asyncio.Semaphore(3)

        async def _limited(q: str) -> list[dict[str, Any]]:
            async with semaphore:
                results = await self.search(q, max_results=max_results)
                return [
                    {
                        "url": r.url,
                        "name": r.title,
                        "snippet": r.snippet,
                        "host_name": "",
                        "rank": r.rank,
                        "engine": r.engine,
                    }
                    for r in results
                ]

        raw_results = await asyncio.gather(
            *[_limited(q) for q in queries],
            return_exceptions=True,
        )

        results: dict[str, list[dict[str, Any]]] = {}
        for query, result_list in zip(queries, raw_results):
            if isinstance(result_list, Exception):
                results[query] = []
            else:
                results[query] = result_list

        return results

    # ------------------------------------------------------------------
    # Pipeline integration — deep search & gap search
    # ------------------------------------------------------------------

    async def deep_search(
        self,
        company_name: str,
        domain: str,
    ) -> dict[str, list[dict[str, Any]]]:
        """Comprehensive 20-query search covering all 14 schema tables."""
        queries: list[str] = [
            # Company basics
            f"{company_name} tokenized assets company overview",
            f"{company_name} founded year headquarters CEO founder",
            f"{company_name} employees headcount linkedin crunchbase",
            # Products & features
            f"{company_name} products services pricing model",
            f"{company_name} tokenization platform features capabilities",
            f"{company_name} asset classes supported real estate bonds",
            # Technology
            f"{company_name} technology blockchain smart contracts API documentation",
            f"{company_name} tech stack infrastructure chains supported",
            f"{company_name} API capabilities SDK sandbox",
            # Funding & governance
            f"{company_name} funding investors valuation series round raised",
            f"{company_name} governance token DAO voting treasury",
            # Compliance & regulatory
            f"{company_name} compliance SOC2 ISO certification audit regulatory",
            f"{company_name} SEC FINRA broker dealer license registration jurisdiction",
            f"{company_name} regulatory licenses approvals EU MiCA",
            # Partnerships & exchange
            f"{company_name} partnerships integration strategic collaboration",
            f"{company_name} exchange listing trading ATS secondary market",
            # SLA & stability
            f"{company_name} SLA uptime reliability service level agreement",
            f"{company_name} API documentation quality sandbox playground developer experience",
            # Metrics & case studies
            f"{company_name} assets under management AUM tokenized clients deals",
            f"{company_name} case studies notable deals clients institutional",
            # Site-specific
            f"site:{domain}",
        ]
        return await self.parallel_search(queries, max_results=8)

    async def gap_search(
        self,
        company_name: str,
        missing_fields: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        """Targeted search for specific missing data fields."""
        _CATEGORY_MAP: dict[str, list[str]] = {
            "funding": ["funding", "investors", "valuation", "series", "round", "capital", "raised", "amount_usd"],
            "compliance": ["compliance", "soc2", "iso", "certification", "audit", "security", "soc_2", "cert"],
            "license": ["license", "sec", "finra", "broker", "dealer", "registration", "regulated", "jurisdiction", "regulator"],
            "partnership": ["partnership", "integration", "partner", "strategic", "collaboration", "partner_name"],
            "sla": ["sla", "uptime", "reliability", "service_level", "availability", "committed_value", "penalty"],
            "exchange": ["exchange", "listing", "trading", "secondary_market", "ats", "connectivity"],
            "governance": ["governance", "token", "dao", "voting", "treasury", "token_symbol"],
            "aum_clients": ["aum", "clients", "assets_under_management", "deals", "tokenized", "notable_clients", "issuances"],
            "tech_api": ["api", "sdk", "tech_stack", "chains_supported", "documentation", "sandbox", "webhook"],
            "products": ["product", "feature", "pricing", "asset_class", "standard", "integration"],
            "stability": ["documentation_quality", "sandbox", "playground", "languages_supported"],
            "deals": ["case_study", "deal", "client_name", "deal_size"],
        }

        _QUERY_TEMPLATES: dict[str, str] = {
            "funding": f"{company_name} funding round investors valuation amount raised",
            "compliance": f"{company_name} SOC2 ISO certification compliance audit report",
            "license": f"{company_name} SEC FINRA broker dealer license registration jurisdiction regulator",
            "partnership": f"{company_name} partnership integration strategic announcement collaboration",
            "sla": f"{company_name} SLA uptime reliability service level agreement availability",
            "exchange": f"{company_name} exchange listing trading secondary market ATS connectivity",
            "governance": f"{company_name} governance token DAO voting treasury runway",
            "aum_clients": f"{company_name} assets under management tokenized clients issuances AUM",
            "tech_api": f"{company_name} API documentation SDK chains supported webhook sandbox",
            "products": f"{company_name} products features pricing asset classes standards integrations",
            "stability": f"{company_name} API documentation quality sandbox playground developer",
            "deals": f"{company_name} case studies deals clients institutional tokenized",
        }

        matched_categories: set[str] = set()
        normalized_fields = [f.lower().strip() for f in missing_fields]

        for category, keywords in _CATEGORY_MAP.items():
            for field in normalized_fields:
                for keyword in keywords:
                    if keyword in field or field in keyword:
                        matched_categories.add(category)
                        break

        if not matched_categories:
            queries = [
                f"{company_name} detailed company information profile",
                f"{company_name} tokenization platform all features",
            ]
            return await self.parallel_search(queries, max_results=8)

        queries = [_QUERY_TEMPLATES[cat] for cat in sorted(matched_categories)]
        return await self.parallel_search(queries, max_results=8)
