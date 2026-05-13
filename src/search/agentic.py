"""Agentic search loop — AI decides what to search for and which URLs to scrape.

Two cheap LLM calls per iteration (uses the configured provider via get_provider()):
  1. Query generation  (~200 tokens in, ~150 out) — "what should I search for?"
  2. URL selection     (~400 tokens in, ~100 out) — "which of these snippets are worth scraping?"

Provider and model are selected by get_provider() — same as the rest of the pipeline.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

logger = logging.getLogger(__name__)

# Lazy-cached provider instance (reuses the pipeline's configured provider)
_provider = None


def _get_provider():
    global _provider
    if _provider is None:
        from ..providers.factory import get_provider
        _provider = get_provider()
    return _provider


async def _cheap_call(prompt: str) -> dict:
    """Single LLM call for agentic decisions using the configured provider.

    Returns parsed JSON dict. Falls back to {} on any error.
    """
    provider = _get_provider()
    system = "You are a research assistant. Always respond with valid JSON only."
    try:
        raw = await provider.complete(system, prompt)
        # Strip markdown fences if present
        cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(cleaned)
    except Exception as e:
        logger.warning("Agentic decision call failed: %s", e)
        return {}


async def generate_targeted_queries(
    company_name: str,
    domain: str,
    missing_fields: list[str],
    already_searched: list[str],
) -> list[str]:
    """Ask cheap LLM to generate 3-5 targeted search queries for missing fields.

    Returns list of query strings.
    """
    # Summarize missing fields by table (avoid sending huge list)
    by_table: dict[str, list[str]] = {}
    for path in missing_fields[:40]:
        table = path.split("[")[0].split(".")[0] if "[" in path else path.split(".")[0]
        field = path.split(".")[-1]
        by_table.setdefault(table, []).append(field)

    missing_summary = "; ".join(
        f"{table}: {', '.join(fields[:5])}"
        for table, fields in list(by_table.items())[:8]
    )

    already = "; ".join(already_searched[-8:]) if already_searched else "none"

    prompt = f"""You are a research assistant for a data extraction pipeline.

Company: {company_name} (domain: {domain})

These data fields are still MISSING:
{missing_summary}

Queries already tried (do NOT repeat these):
{already}

Generate 3-5 precise web search queries to find the missing data.
Prefer site-specific queries (e.g. site:crunchbase.com) and news sources.
Return JSON: {{"queries": ["query1", "query2", ...]}}"""

    result = await _cheap_call(prompt)
    queries = result.get("queries", [])
    if not isinstance(queries, list):
        return []
    return [str(q) for q in queries[:5] if q]


async def select_urls_to_scrape(
    company_name: str,
    missing_fields: list[str],
    search_results: dict[str, list[dict]],
    already_scraped: set[str],
    max_urls: int = 5,
) -> list[str]:
    """Ask cheap LLM to pick the most relevant URLs from search snippets.

    Reads only snippets (no scraping yet) — very cheap.
    Returns list of URLs worth actually scraping.
    """
    # Build a compact snippet list
    candidates = []
    seen = set()
    for _query, results in search_results.items():
        for r in results:
            url = r.get("url", "")
            snippet = r.get("snippet", "") or r.get("content", "")
            title = r.get("name", "") or r.get("title", "")
            if not url or url in seen or url in already_scraped:
                continue
            seen.add(url)
            candidates.append({
                "url": url,
                "title": title[:80],
                "snippet": snippet[:200],
            })
            if len(candidates) >= 20:
                break
        if len(candidates) >= 20:
            break

    if not candidates:
        return []

    # Summarize what's missing
    fields_preview = ", ".join(f.split(".")[-1] for f in missing_fields[:15])

    prompt = f"""You are selecting URLs to scrape for a data pipeline.

Company: {company_name}
Missing data: {fields_preview}

Below are search result candidates. Pick the {max_urls} URLs most likely to contain the missing data.
Prefer: official company pages, Crunchbase, LinkedIn, news articles about funding/compliance/partnerships.
Avoid: generic directories, irrelevant pages, social media feeds.

Candidates:
{json.dumps(candidates, indent=2)}

Return JSON: {{"selected_urls": ["url1", "url2", ...]}}"""

    result = await _cheap_call(prompt)
    selected = result.get("selected_urls", [])
    if not isinstance(selected, list):
        return []
    # Only return URLs that were in the candidates list
    valid = {c["url"] for c in candidates}
    return [u for u in selected if u in valid][:max_urls]


async def agentic_search_loop(
    company_name: str,
    domain: str,
    missing_fields: list[str],
    searcher,        # SearXNGClient
    scraper,         # AsyncScraper
    max_iterations: int = 3,
    target_fields_remaining: int = 5,
) -> dict[str, Any]:
    """Autonomous search-and-scrape loop driven by LLM decisions.

    Each iteration:
      1. Cheap LLM generates targeted queries for still-missing fields
      2. Run those queries through SearXNG
      3. Cheap LLM reads snippets and picks best URLs to scrape
      4. Scrape only selected URLs
      5. Return all new pages for extraction

    Stops when: max_iterations reached OR few enough fields remain.
    Cost: ~2 cheap calls × N iterations = pennies.
    """
    all_new_pages: dict[str, Any] = {}
    already_searched: list[str] = []
    already_scraped: set[str] = scraper._scraped_urls.copy()

    for iteration in range(1, max_iterations + 1):
        if len(missing_fields) <= target_fields_remaining:
            logger.info("Agentic loop: only %d fields missing, stopping", len(missing_fields))
            break

        logger.info("Agentic iteration %d: %d fields missing", iteration, len(missing_fields))

        # Step 1: Generate targeted queries
        queries = await generate_targeted_queries(
            company_name, domain, missing_fields, already_searched,
        )
        if not queries:
            logger.warning("Agentic loop: no queries generated, stopping")
            break

        logger.info("Agentic queries: %s", queries)
        already_searched.extend(queries)

        # Step 2: Search
        search_results = await searcher.parallel_search(queries, max_results=8)

        # Step 3: AI selects best URLs to scrape
        urls_to_scrape = await select_urls_to_scrape(
            company_name, missing_fields, search_results, already_scraped,
        )
        if not urls_to_scrape:
            logger.info("Agentic loop: no URLs selected for scraping in iteration %d", iteration)
            continue

        logger.info("Agentic scraping %d URLs: %s", len(urls_to_scrape), urls_to_scrape)

        # Step 4: Scrape selected URLs only
        new_pages = await scraper.scrape_urls(urls_to_scrape)
        all_new_pages.update(new_pages)
        already_scraped.update(new_pages.keys())

        logger.info("Agentic iteration %d: scraped %d new pages", iteration, len(new_pages))

    return all_new_pages
