"""Incremental update mode - update existing company data efficiently.

This module provides utilities for updating only fields that need improvement.
For now, it provides a targeted gap-fill mode that can be extended.
"""
import asyncio
import logging
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from .schema.models import CompanyData

logger = logging.getLogger(__name__)


async def targeted_update(
    company_name: str,
    domain: str,
    target_fields: list[str] | None = None,
) -> dict[str, Any]:
    """Run targeted extraction for specific fields.

    Args:
        company_name: Company name
        domain: Company domain
        target_fields: Specific fields to extract (optional). If None, uses smart defaults.

    Returns:
        Dict with update results
    """
    from .search.client import SearXNGClient
    from .scrape.scraper import AsyncScraper
    from .extractor.llm import LLMExtractor
    from .orchestrator import PipelineRunner
    from .schema.models import CompanyData

    t0 = asyncio.get_event_loop().time()
    logger.info(f"Starting targeted update for {company_name} ({domain})")

    # Default target fields if none specified (high-value fields)
    if target_fields is None:
        target_fields = [
            "companies.total_funding_usd",
            "companies.revenue_status",
            "companies.employee_count_range",
            "platform_metrics.total_aum_tokenized_usd",
            "platform_metrics.number_of_clients",
        ]

    try:
        # Quick search
        s = SearXNGClient()
        sr = await s.deep_search(company_name, domain)

        # Quick scrape
        scraper = AsyncScraper(timeout=8, max_concurrent=4, use_playwright=False)
        cp = await scraper.get_company_pages(domain)
        await scraper.close()

        all_pages = {**cp}

        # Extract only target fields
        ext = LLMExtractor()
        gap_data = await ext.extract_gaps(
            company_name, domain, target_fields, sr, all_pages
        )

        # Also try knowledge gaps
        kg_data = await ext.extract_knowledge_gaps(company_name, domain, target_fields)

        # Structure the output properly
        gap_structured = PipelineRunner._structure_output(gap_data, company_name, domain)
        kg_structured = PipelineRunner._structure_output(kg_data, company_name, domain)

        # Merge into final CompanyData
        cd = CompanyData()
        PipelineRunner._merge_data(cd, gap_structured)
        PipelineRunner._merge_data(cd, kg_structured)
        cd.apply_defaults(company_name, domain)

        elapsed = asyncio.get_event_loop().time() - t0

        # Get call logs for cost
        call_logs = getattr(ext, "call_logs", [])
        from .database.saver import DatabaseSaver
        for log in call_logs:
            log["cost_usd"] = DatabaseSaver._calc_cost(
                log.get("model", ""), log.get("prompt_tokens", 0), log.get("completion_tokens", 0)
            )
        total_cost = sum(l.get("cost_usd", 0) for l in call_logs)

        # Count filled fields
        filled_count = 0
        for field_path in target_fields:
            parts = field_path.split(".")
            if len(parts) >= 2:
                table = parts[0].split("[")[0]
                field = parts[-1]
                if hasattr(cd, field):
                    val = getattr(cd, field)
                    if val and val.is_filled() and val.confidence >= 0.4:
                        filled_count += 1

        return {
            "company": company_name,
            "domain": domain,
            "status": "completed",
            "fields_requested": len(target_fields),
            "fields_filled": filled_count,
            "total_cost_usd": round(total_cost, 6),
            "duration_secs": round(elapsed, 1),
            "target_fields": target_fields,
        }

    except Exception as e:
        logger.error(f"Targeted update failed for {domain}: {e}")
        return {
            "company": company_name,
            "domain": domain,
            "status": "error",
            "error": str(e),
        }
