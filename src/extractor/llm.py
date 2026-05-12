"""
LLM Extractor — 6 focused extraction batches with per-batch context.

Supports multiple LLM providers: z.ai (free), OpenAI, Anthropic, OpenRouter.
Select provider via LLM_PROVIDER env var (default: zai).
"""

from __future__ import annotations

import json
import re
import asyncio
import logging
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from ..providers.factory import get_provider
from ..providers.base import BaseLLMProvider, LLMCallResult
from ..cache import get_cache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Batch field specifications
# ---------------------------------------------------------------------------

BATCH_A = {"companies": [
    "company_name", "legal_name", "hq_country", "hq_city", "founded_year",
    "website", "description", "company_type", "operational_status",
    "employee_count_range", "logo_url", "is_active", "platform", "url",
    "total_employees", "founder_still_active", "handle", "follower_count",
]}

BATCH_B = {
    "products": [
        "product_name", "product_type", "description", "launch_date", "status",
        "pricing_model", "pricing_notes", "target_segment",
    ],
    "asset_classes": [
        "asset_class", "is_primary", "maturity_level", "notes",
    ],
    "features": [
        "feature_category", "feature_name", "feature_tier", "description",
    ],
    "standards": [
        "standard_name", "is_native_support", "compliance_built_in",
    ],
    "integrations": [
        "partner_name", "integration_type", "integration_depth", "status", "description",
    ],
}

BATCH_C = {
    "funding_round": [
        "round_type", "amount_usd", "date", "lead_investor",
        "other_investors", "valuation_usd", "source_url", "notes",
    ],
    "governance_model": [
        "governance_type", "has_token", "token_symbol",
        "token_distribution_notes", "treasury_runway_months",
        "total_funding_usd", "revenue_status", "last_assessed_at",
    ],
}

BATCH_D = {
    "compliance_certifications": [
        "certification_type", "status", "issued_date", "expiry_date", "auditor", "certificate_url",
    ],
    "sla_commitments": [
        "metric", "committed_value", "actual_value_last_12m",
        "measurement_period", "has_penalty_clause", "notes",
    ],
    "stability_table": [
        "documentation_quality", "has_sandbox_environment",
        "has_api_playground", "languages_supported",
    ],
}

BATCH_E = {
    "tech_stack": [
        "component", "technology", "version", "notes", "chains_supported", "mainnet_live",
    ],
    "api_capabilities": [
        "api_type", "documentation_url", "has_sandbox", "rate_limit_tier",
        "authentication_method", "sdk_languages", "webhook_support", "api_versioning",
    ],
}

BATCH_F = {
    "partnerships": [
        "partner_name", "partner_type", "partnership_tier",
        "announced_date", "description", "source_url",
    ],
    "exchange_listings": [
        "exchange_name", "exchange_type", "connectivity_type",
        "status", "asset_classes_tradeable",
    ],
    "regulatory_licenses": [
        "jurisdiction", "license_type", "status", "issued_date",
        "license_number", "regulator_name", "coverage_type",
        "investor_types_allowed", "asset_classes_allowed", "regulatory_basis",
    ],
    "platform_metrics": [
        "total_aum_tokenized_usd", "number_of_issuances",
        "number_of_active_tokens", "number_of_clients", "notable_clients",
    ],
    "deal_case_studies": [
        "title", "asset_class", "deal_size_usd", "client_name",
        "jurisdiction", "completion_date", "description", "public_url",
    ],
}

ALL_BATCHES = [
    ("BatchA_Company", BATCH_A),
    ("BatchB_Products", BATCH_B),
    ("BatchC_Funding_Governance", BATCH_C),
    ("BatchD_Compliance_SLA_Stability", BATCH_D),
    ("BatchE_Tech_API", BATCH_E),
    ("BatchF_Partners_Licenses_Metrics_Deals", BATCH_F),
]

# Map each batch to the search query keywords that are relevant to it
BATCH_CONTEXT_KEYWORDS = {
    "BatchA_Company": [
        "overview", "founded", "headquarters", "ceo", "founder", "employees",
        "linkedin", "crunchbase", "company", "about", "team", "headcount",
    ],
    "BatchB_Products": [
        "products", "services", "pricing", "features", "capabilities",
        "asset classes", "standards", "integrations", "tokenization", "platform",
    ],
    "BatchC_Funding_Governance": [
        "funding", "investors", "valuation", "series", "governance",
        "token", "dao", "treasury", "raised", "round",
    ],
    "BatchD_Compliance_SLA_Stability": [
        "compliance", "soc2", "iso", "certification", "audit", "sla",
        "uptime", "reliability", "sandbox", "documentation", "regulatory",
        "security",
    ],
    "BatchE_Tech_API": [
        "technology", "blockchain", "api", "sdk", "chains", "documentation",
        "developer", "sandbox", "webhook", "smart contracts", "infrastructure",
    ],
    "BatchF_Partners_Licenses_Metrics_Deals": [
        "partnership", "exchange", "listing", "license", "sec", "finra",
        "regulatory", "aum", "clients", "deals", "case studies", "trading",
        "broker", "dealer",
    ],
}


def _build_fields_desc(fields_spec: dict[str, list[str]]) -> str:
    lines = []
    for table, fields in fields_spec.items():
        lines.append(f"Table: {table}")
        for f in fields:
            lines.append(f"  - {f}")
        lines.append("")
    return "\n".join(lines)


SYSTEM_PROMPT = """You are an expert data extraction system for tokenized assets companies. Extract structured data from the provided context.

CRITICAL RULES:
1. For EVERY field, extract: {"value": <value_or_null>, "source_url": "<url_or_null>", "confidence": <0.0-1.0>}
2. If a field CANNOT be found, set value=null, source_url=null, confidence=0.0 — DO NOT SKIP any field.
3. Confidence: 0.9=company website, 0.7=reputable third-party (Wikipedia, Crunchbase, news), 0.5=inferred from context, 0.4=guessed
4. For repeating tables (products, funding_round, tech_stack, etc.), use {"rows": [...]} with array of objects.
5. For single-row tables (companies, governance_model, stability_table, platform_metrics), use flat object.
6. Return ONLY valid JSON — no markdown, no code fences, no commentary.
7. EVERY field listed must appear in the output, even if value is null.
8. Extract AS MANY repeating rows as you can find in the context.
9. Look carefully at ALL context provided — search results AND scraped pages.
10. If the company name is mentioned in context, use that exact name.
11. For boolean fields (is_active, has_token, mainnet_live, etc.), use true/false not "yes"/"no".
12. For numeric fields (founded_year, amount_usd, etc.), use numbers not strings.
13. For chain/blockchain info, list all chains mentioned (e.g., "Ethereum, Solana, Polygon").

JSON structure:
{
  "table_name": {
    "field_name": {"value": ..., "source_url": ..., "confidence": ...},
    ...
  },
  "repeating_table": {
    "rows": [
      {"field_name": {"value": ..., "source_url": ..., "confidence": ...}, ...},
      ...
    ]
  }
}"""


def _truncate(text: str, max_chars: int = 15000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[... truncated ...]"


def _parse_json(raw: str) -> dict[str, Any]:
    cleaned = re.sub(r"```(?:json)?\s*", "", raw)
    cleaned = re.sub(r"\s*```", "", cleaned).strip()
    start = cleaned.find("{")
    if start == -1:
        return {}
    end = cleaned.rfind("}") + 1
    if end == 0:
        return {}
    try:
        return json.loads(cleaned[start:end])
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM JSON (first 200 chars): %s", cleaned[start:start+200])
        return {}


class LLMExtractor:
    """Extract structured data using 6 focused LLM batches.

    Provider selected via LLM_PROVIDER env var (default: zai).
    Supports: zai, openai, anthropic, openrouter.
    """

    def __init__(self, provider_name: str | None = None) -> None:
        self.provider: BaseLLMProvider = get_provider(provider_name)
        self._semaphore = asyncio.Semaphore(self.provider.config.max_concurrent)
        self.call_logs: list[dict] = []
        logger.info(
            "LLMExtractor using provider: %s (model=%s)",
            type(self.provider).__name__, self.provider.config.model,
        )

    async def _call_llm(self, system: str, user: str, batch_name: str = "", _retries: int = 0) -> str:
        """Call LLM provider with retry logic, caching, and cost logging."""
        import hashlib
        import os

        sys_hash = hashlib.sha256(system.encode()).hexdigest()
        user_chars = len(user)

        # Check cache first (disabled for gap/knowledge queries)
        use_cache = os.getenv("ENABLE_CACHE", "true").lower() == "true"
        is_cacheable = batch_name not in ("gap_extraction", "knowledge_gap")

        if use_cache and is_cacheable and _retries == 0:
            cache = get_cache()
            cached = cache.get(user, self.provider.config.model, system)
            if cached:
                logger.info("Cache HIT for batch %s", batch_name)
                # Log as cached call
                self.call_logs.append({
                    "batch_name": batch_name,
                    "provider": type(self.provider).__name__.replace("Provider", "").lower(),
                    "model": self.provider.config.model,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "latency_ms": 1,
                    "system_prompt_hash": sys_hash,
                    "user_prompt_chars": user_chars,
                    "response_chars": len(str(cached)),
                    "success": True,
                    "error_message": None,
                    "cached": True,
                })
                return cached
            logger.info("Cache MISS for batch %s", batch_name)

        try:
            result: LLMCallResult = await self.provider.complete_with_usage(system, user)

            # Log the call
            log_entry = {
                "batch_name": batch_name,
                "provider": type(self.provider).__name__.replace("Provider", "").lower(),
                "model": self.provider.config.model,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "total_tokens": result.total_tokens,
                "latency_ms": result.latency_ms,
                "system_prompt_hash": sys_hash,
                "user_prompt_chars": user_chars,
                "response_chars": len(result.content),
                "success": result.success,
                "error_message": result.error,
                "cached": False,
            }
            self.call_logs.append(log_entry)

            if not result.success:
                raise RuntimeError(result.error or "Unknown error")

            # Cache successful responses
            if use_cache and is_cacheable and result.success:
                cache = get_cache()
                cache.set(user, self.provider.config.model, result.content, system)

            return result.content

        except Exception as e:
            # Log failed call if not already logged
            if not self.call_logs or self.call_logs[-1].get("batch_name") != batch_name or self.call_logs[-1].get("success"):
                self.call_logs.append({
                    "batch_name": batch_name,
                    "provider": type(self.provider).__name__.replace("Provider", "").lower(),
                    "model": self.provider.config.model,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "latency_ms": 0,
                    "system_prompt_hash": sys_hash,
                    "user_prompt_chars": user_chars,
                    "response_chars": 0,
                    "success": False,
                    "error_message": str(e)[:500],
                    "cached": False,
                })

            # Rate limit retry
            status = getattr(e, "status_code", None)
            is_rate_limit = status == 429 or "429" in str(e) or "rate" in str(e).lower()
            if is_rate_limit and _retries < 4:
                wait_time = 3 * (_retries + 1)
                logger.warning("Rate limited, waiting %ds (retry %d/4)", wait_time, _retries + 1)
                await asyncio.sleep(wait_time)
                return await self._call_llm(system, user, batch_name, _retries=_retries + 1)

            logger.error("LLM API error: %s: %s", type(e).__name__, str(e)[:200])
            return "{}"

    async def _extract_batch(self, name: str, spec: dict, context: str) -> dict:
        async with self._semaphore:
            fields_desc = _build_fields_desc(spec)
            user_prompt = (
                f"Extract data for the company below.\n\n"
                f"=== FIELDS TO EXTRACT (ALL must appear in output) ===\n{fields_desc}\n"
                f"=== CONTEXT ===\n{_truncate(context)}\n\n"
                f"Return valid JSON with ALL fields listed above. Every field must have value, source_url, confidence."
            )
            raw = await self._call_llm(SYSTEM_PROMPT, user_prompt, batch_name=name)
            parsed = _parse_json(raw)
            if not parsed:
                logger.warning("Batch %s returned empty", name)
            return parsed

    def _filter_context_for_batch(
        self,
        batch_name: str,
        search_results: dict,
        scraped_pages: dict,
    ) -> str:
        """Build filtered context relevant to each batch's data domain."""
        keywords = BATCH_CONTEXT_KEYWORDS.get(batch_name, [])
        keyword_lower = [k.lower() for k in keywords]

        parts: list[str] = []

        # Filter search results by keyword match - include FULL snippets
        parts.append("=== SEARCH RESULTS ===")
        for query, results in search_results.items():
            query_lower = query.lower()
            if any(kw in query_lower for kw in keyword_lower):
                parts.append(f"\nQuery: {query}")
                for r in results[:10]:
                    name = r.get("name", "") if isinstance(r, dict) else getattr(r, "title", "")
                    url = r.get("url", "") if isinstance(r, dict) else getattr(r, "url", "")
                    snippet = r.get("snippet", "") if isinstance(r, dict) else getattr(r, "snippet", "")
                    if snippet:
                        parts.append(f"  [{name}]({url}): {snippet}")

        # ALWAYS include all scraped pages
        parts.append("\n=== SCRAPED PAGES ===")
        for url, page in scraped_pages.items():
            text = getattr(page, "text", "") if not isinstance(page, dict) else page.get("text", "")
            title = getattr(page, "title", "") if not isinstance(page, dict) else page.get("title", "")
            if text:
                parts.append(f"\n--- {title} ({url}) ---")
                parts.append(text[:4000])

        return "\n".join(parts)

    async def extract_all(self, company_name: str, domain: str,
                          search_results: dict, scraped_pages: dict) -> dict:
        """Run all 6 extraction batches with per-batch filtered context."""
        tasks = []
        for name, spec in ALL_BATCHES:
            context = self._filter_context_for_batch(name, search_results, scraped_pages)
            context = f"Company: {company_name}\nDomain: {domain}\n\n{context}"
            tasks.append(self._extract_batch(name, spec, context))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        merged = {}
        for i, r in enumerate(results):
            name = ALL_BATCHES[i][0]
            if isinstance(r, Exception):
                logger.error("%s failed: %s", name, str(r)[:200])
            elif isinstance(r, dict):
                merged.update(r)
        return merged

    async def extract_gaps(
        self,
        company_name: str,
        domain: str,
        missing_fields: list[str],
        search_results: dict,
        scraped_pages: dict,
    ) -> dict:
        """Targeted extraction for specific missing fields from context + LLM knowledge."""
        spec: dict[str, list[str]] = {}
        for path in missing_fields:
            parts = path.split(".")
            if len(parts) >= 2:
                table = parts[0].split("[")[0]
                field = parts[-1]
                if table not in spec:
                    spec[table] = []
                if field not in spec[table]:
                    spec[table].append(field)

        if not spec:
            return {}

        context_parts: list[str] = [
            f"Company: {company_name}\nDomain: {domain}",
            f"\nThese fields are MISSING and need to be filled:",
            json.dumps(spec, indent=2),
        ]

        context_parts.append("\n=== ALL SEARCH RESULTS ===")
        for query, results in search_results.items():
            context_parts.append(f"\nQuery: {query}")
            for r in results[:10]:
                name = r.get("name", "") if isinstance(r, dict) else getattr(r, "title", "")
                url = r.get("url", "") if isinstance(r, dict) else getattr(r, "url", "")
                snippet = r.get("snippet", "") if isinstance(r, dict) else getattr(r, "snippet", "")
                if snippet:
                    context_parts.append(f"  [{name}]({url}): {snippet}")

        context_parts.append("\n=== ALL SCRAPED PAGES ===")
        for url, page in scraped_pages.items():
            text = getattr(page, "text", "") if not isinstance(page, dict) else page.get("text", "")
            title = getattr(page, "title", "") if not isinstance(page, dict) else page.get("title", "")
            if text:
                context_parts.append(f"\n--- {title} ({url}) ---")
                context_parts.append(text[:4000])

        context = "\n".join(context_parts)

        fields_desc = _build_fields_desc(spec)

        # Use a gap-specific prompt that also leverages LLM knowledge
        gap_system = SYSTEM_PROMPT + (
            "\n14. If a field cannot be found in the provided context but you KNOW the answer "
            "from your training data about this company, provide it with confidence 0.5 and "
            "source_url=null. This is better than leaving it null."
        )
        user_prompt = (
            f"The following fields are MISSING from our data extraction for {company_name}.\n"
            f"Please extract these missing fields from the context. If not in context, use your "
            f"knowledge about {company_name} with confidence 0.5.\n\n"
            f"=== MISSING FIELDS (ALL must appear in output) ===\n{fields_desc}\n"
            f"=== CONTEXT ===\n{_truncate(context, max_chars=20000)}\n\n"
            f"Return valid JSON with ALL missing fields. Every field must have value, source_url, confidence."
        )

        async with self._semaphore:
            raw = await self._call_llm(gap_system, user_prompt, batch_name="gap_extraction")
            parsed = _parse_json(raw)
            if not parsed:
                logger.warning("Gap extraction returned empty")
            return parsed

    async def extract_knowledge_gaps(
        self,
        company_name: str,
        domain: str,
        missing_fields: list[str],
    ) -> dict:
        """Fast LLM-only extraction for missing fields — no search or scraping needed.

        Uses the LLM's training knowledge to fill gaps. Much faster than
        extract_gaps since it doesn't need additional search/scrape cycles.
        Uses confidence 0.5 for LLM-sourced data (higher than defaults at 0.1-0.3).
        """
        spec: dict[str, list[str]] = {}
        for path in missing_fields:
            parts = path.split(".")
            if len(parts) >= 2:
                table = parts[0].split("[")[0]
                field = parts[-1]
                if table not in spec:
                    spec[table] = []
                if field not in spec[table]:
                    spec[table].append(field)

        if not spec:
            return {}

        fields_desc = _build_fields_desc(spec)

        knowledge_system = SYSTEM_PROMPT + (
            "\n14. You MUST use your training knowledge about this company to fill in fields. "
            "Do NOT return null for fields you know from your training data. "
            "For LLM-sourced data (not from provided context), set confidence=0.5 and source_url=null. "
            "This is critical — every field should have a value if you know it."
        )
        user_prompt = (
            f"Company: {company_name}\nDomain: {domain}\n\n"
            f"The following fields still have no data or only low-confidence defaults.\n"
            f"Use your KNOWLEDGE about {company_name} to fill these fields.\n"
            f"If you know the answer from your training data, provide it with confidence 0.5.\n"
            f"If you truly don't know, set value=null, confidence=0.0.\n\n"
            f"=== MISSING FIELDS (ALL must appear in output) ===\n{fields_desc}\n\n"
            f"Return valid JSON with ALL missing fields. Every field must have value, source_url, confidence."
        )

        async with self._semaphore:
            raw = await self._call_llm(knowledge_system, user_prompt, batch_name="knowledge_gap")
            parsed = _parse_json(raw)
            if not parsed:
                logger.warning("Knowledge gap extraction returned empty")
            return parsed
