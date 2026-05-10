"""
Pipeline Orchestrator — Multi-pass data gathering with gap filling.

Uses UnifiedSearcher (SearXNG + z-ai web_search) for web search,
AsyncScraper for page scraping, LLMExtractor for extraction.

Architecture:
  Phase 1: Deep web search (20 queries via UnifiedSearcher)
  Phase 2: Scrape company domain pages (25+ paths) + internal links + top search URLs
  Phase 3: First LLM extraction pass (6 batches with filtered context)
  Phase 4: Gap analysis + targeted search for missing fields + scrape more
  Phase 5: Second LLM extraction pass on gap context
  Phase 6: Apply defaults, validate, output
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from .schema.models import (
    CitedValue, CompanyProfile, Product, AssetClass, Feature, Standard,
    Integration, FundingRound, GovernanceModel, ComplianceCertification,
    SlaCommitment, StabilityEntry, TechStackEntry, ApiCapability,
    Partnership, ExchangeListing, RegulatoryLicense, PlatformMetric,
    DealCaseStudy, CompanyData,
)
from .search.client import SearXNGClient
from .scrape.scraper import AsyncScraper
from .extractor.llm import LLMExtractor

logger = logging.getLogger(__name__)


class PipelineResult:
    def __init__(self):
        self.company_data: CompanyData = CompanyData()
        self.timing: dict[str, float] = {}
        self.fill_rate: float = 0.0
        self.errors: list[str] = []
        self.pass_count: int = 0
        self.search_result_count: int = 0
        self.scraped_page_count: int = 0

    def to_dict(self) -> dict:
        return {
            "timing": self.timing,
            "fill_rate": round(self.fill_rate * 100, 1),
            "errors": self.errors,
            "pass_count": self.pass_count,
            "search_result_count": self.search_result_count,
            "scraped_page_count": self.scraped_page_count,
            "data": self.company_data.model_dump(),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


class PipelineRunner:
    """Orchestrates multi-pass data gathering pipeline."""

    def __init__(self, max_passes: int = 3, pipeline_timeout: int = 300):
        self.max_passes = max_passes
        self.pipeline_timeout = pipeline_timeout
        self.searcher = SearXNGClient()
        self.scraper = AsyncScraper(timeout=10, max_concurrent=8, use_playwright=True)
        self.extractor = LLMExtractor()

    async def run(self, company_name: str, domain: str) -> PipelineResult:
        result = PipelineResult()
        t0 = time.perf_counter()

        try:
            result = await asyncio.wait_for(
                self._run_pipeline(company_name, domain, result),
                timeout=self.pipeline_timeout,
            )
        except asyncio.TimeoutError:
            result.errors.append(f"Pipeline timed out after {self.pipeline_timeout}s")

        total = time.perf_counter() - t0
        result.timing["total"] = round(total, 2)
        result.company_data.apply_defaults(company_name, domain)
        result.fill_rate = result.company_data.confidence_score()
        logger.info(
            "Pipeline done for %s in %.2fs — fill: %.1f%%",
            company_name, total, result.fill_rate * 100,
        )
        await self.scraper.close()
        return result

    async def _run_pipeline(
        self, company_name: str, domain: str, result: PipelineResult,
    ) -> PipelineResult:
        all_search_results: dict[str, list] = {}
        all_scraped_pages: dict[str, Any] = {}

        # =================================================================
        # PHASE 1: Deep web search — 20 targeted queries
        # =================================================================
        t1 = time.perf_counter()
        logger.info("Phase 1: Deep web search for %s (SearXNG + z-ai web_search)", company_name)
        try:
            search_results = await self.searcher.deep_search(company_name, domain)
            all_search_results.update(search_results)
            total_results = sum(len(v) for v in search_results.values())
            result.search_result_count = total_results
            logger.info("Phase 1: %d results from %d queries", total_results, len(search_results))
        except Exception as e:
            result.errors.append(f"Phase 1 search error: {str(e)[:200]}")
        result.timing["phase1_search"] = round(time.perf_counter() - t1, 2)

        # =================================================================
        # PHASE 2: Scrape company pages + discovered links + search result URLs
        # =================================================================
        t2 = time.perf_counter()
        logger.info("Phase 2: Scraping pages for %s", company_name)
        try:
            # Scrape company domain pages (25+ paths) + discover internal links
            company_pages = await self.scraper.get_company_pages(domain)
            all_scraped_pages.update(company_pages)
            logger.info("Scraped %d company domain pages", len(company_pages))

            # Scrape top URLs from search results (external pages)
            search_pages = await self.scraper.scrape_search_urls(
                all_search_results,
                max_per_query=3,
                max_total=20,
                exclude_domain=domain,
            )
            all_scraped_pages.update(search_pages)
            logger.info("Scraped %d external pages from search", len(search_pages))

            # Also scrape subdomain pages found in search results
            # (e.g., api-docs.securitize.io, support.securitize.io)
            subdomain_urls = []
            for query, results in all_search_results.items():
                for r in results:
                    url = r.get("url", "") if isinstance(r, dict) else getattr(r, "url", "")
                    if url and domain in url and url not in all_scraped_pages:
                        # This is a subdomain or deep page on the company domain
                        subdomain_urls.append(url)
            if subdomain_urls:
                subdomain_pages = await self.scraper.scrape_urls(subdomain_urls[:10])
                all_scraped_pages.update(subdomain_pages)
                logger.info("Scraped %d subdomain/deep pages", len(subdomain_pages))

        except Exception as e:
            result.errors.append(f"Phase 2 scrape error: {str(e)[:200]}")
        result.scraped_page_count = len(all_scraped_pages)
        result.timing["phase2_scrape"] = round(time.perf_counter() - t2, 2)

        # =================================================================
        # PHASE 3-5: Multi-pass LLM extraction with gap filling
        # =================================================================
        for pass_num in range(1, self.max_passes + 1):
            logger.info("Pass %d: LLM extraction", pass_num)
            t_pass = time.perf_counter()

            try:
                extraction = await self.extractor.extract_all(
                    company_name, domain, all_search_results, all_scraped_pages,
                )
                new_data = self._structure_output(extraction, company_name, domain)
                self._merge_data(result.company_data, new_data)
                result.pass_count = pass_num
            except Exception as e:
                result.errors.append(f"Pass {pass_num} LLM error: {str(e)[:200]}")

            # Check fill rate BEFORE applying defaults
            pre_default_fill = result.company_data.confidence_score()
            real_fill = result.company_data.real_fill_score(min_confidence=0.4)

            # Apply defaults to see effective fill rate
            result.company_data.apply_defaults(company_name, domain)
            current_fill = result.company_data.confidence_score()
            result.timing[f"pass{pass_num}_llm"] = round(time.perf_counter() - t_pass, 2)

            logger.info(
                "Pass %d: pre-default fill %.1f%%, real fill (>=0.4 conf) %.1f%%, post-default fill %.1f%%",
                pass_num, pre_default_fill * 100, real_fill * 100, current_fill * 100,
            )

            # Always do a fast knowledge-gap fill after pass 1
            if pass_num == 1:
                missing = result.company_data.missing_fields(min_confidence=0.4)
                if missing:
                    logger.info("Knowledge gap fill for %d low-confidence fields", len(missing))
                    t_kg = time.perf_counter()
                    try:
                        kg_extraction = await self.extractor.extract_knowledge_gaps(
                            company_name, domain, missing,
                        )
                        if kg_extraction:
                            kg_data = self._structure_output(kg_extraction, company_name, domain)
                            self._merge_data(result.company_data, kg_data)
                            # Re-apply defaults after knowledge gap fill
                            result.company_data.apply_defaults(company_name, domain)
                            real_fill = result.company_data.real_fill_score(min_confidence=0.4)
                            logger.info("After knowledge gap: real fill %.1f%%", real_fill * 100)
                    except Exception as e:
                        result.errors.append(f"Knowledge gap error: {str(e)[:200]}")
                    result.timing["knowledge_gap"] = round(time.perf_counter() - t_kg, 2)

            # Check if we're done — use REAL fill (not default-inflated)
            if real_fill >= 0.95:
                logger.info("Real fill rate >= 95%%, stopping at pass %d", pass_num)
                break

            # Gap search for missing fields (on later passes)
            if pass_num < self.max_passes and real_fill < 0.95:
                missing = result.company_data.missing_fields(min_confidence=0.4)
                if missing:
                    logger.info("Gap search for %d missing fields", len(missing))
                    t_gap = time.perf_counter()
                    try:
                        # Targeted search for missing categories
                        gap_results = await self.searcher.gap_search(company_name, missing)
                        all_search_results.update(gap_results)
                        result.search_result_count += sum(len(v) for v in gap_results.values())

                        # Scrape top gap search results
                        gap_urls = []
                        for q, results in gap_results.items():
                            for r in results[:3]:
                                url = r.get("url", "") if isinstance(r, dict) else getattr(r, "url", "")
                                if url and url not in all_scraped_pages:
                                    gap_urls.append(url)
                        if gap_urls:
                            gap_pages = await self.scraper.scrape_urls(gap_urls[:10])
                            all_scraped_pages.update(gap_pages)
                            result.scraped_page_count = len(all_scraped_pages)

                        # Targeted LLM extraction for gaps
                        gap_extraction = await self.extractor.extract_gaps(
                            company_name, domain, missing,
                            all_search_results, all_scraped_pages,
                        )
                        if gap_extraction:
                            gap_data = self._structure_output(gap_extraction, company_name, domain)
                            self._merge_data(result.company_data, gap_data)

                    except Exception as e:
                        result.errors.append(f"Gap search error: {str(e)[:200]}")
                    result.timing[f"pass{pass_num}_gap"] = round(time.perf_counter() - t_gap, 2)

        return result

    # ------------------------------------------------------------------
    # Data structuring — map LLM JSON → Pydantic models
    # ------------------------------------------------------------------

    @staticmethod
    def _cv(data: dict | None, key: str) -> CitedValue:
        if not data or key not in data:
            return CitedValue()
        entry = data[key]
        if isinstance(entry, CitedValue):
            return entry
        if isinstance(entry, dict):
            return CitedValue(
                value=entry.get("value"),
                source_url=entry.get("source_url"),
                confidence=float(entry.get("confidence", 0.0)),
            )
        return CitedValue(value=entry, confidence=0.5)

    @staticmethod
    def _rows(data: dict, table_name: str) -> list[dict]:
        table = data.get(table_name, {})
        if isinstance(table, dict):
            rows = table.get("rows", [])
            if rows:
                return rows
            if any(isinstance(v, dict) and "value" in v for v in table.values()):
                return [table]
            return []
        if isinstance(table, list):
            return table
        return []

    @staticmethod
    def _structure_output(extraction: dict, company_name: str, domain: str) -> CompanyData:
        cv = PipelineRunner._cv
        rows = PipelineRunner._rows

        # Company profile
        c = extraction.get("companies", {})
        profile = CompanyProfile(
            company_name=cv(c, "company_name") or CitedValue(value=company_name, confidence=0.9),
            legal_name=cv(c, "legal_name"),
            hq_country=cv(c, "hq_country"),
            hq_city=cv(c, "hq_city"),
            founded_year=cv(c, "founded_year"),
            website=cv(c, "website") or CitedValue(value=f"https://{domain}", confidence=0.8),
            description=cv(c, "description"),
            company_type=cv(c, "company_type"),
            operational_status=cv(c, "operational_status"),
            employee_count_range=cv(c, "employee_count_range"),
            logo_url=cv(c, "logo_url"),
            is_active=cv(c, "is_active"),
            platform=cv(c, "platform"),
            url=cv(c, "url"),
            total_employees=cv(c, "total_employees"),
            founder_still_active=cv(c, "founder_still_active"),
            handle=cv(c, "handle"),
            follower_count=cv(c, "follower_count"),
        )

        # Products
        products = [Product(**{f: cv(r, f) for f in Product.model_fields}) for r in rows(extraction, "products")]

        # Asset classes
        asset_classes = [AssetClass(**{f: cv(r, f) for f in AssetClass.model_fields}) for r in rows(extraction, "asset_classes")]

        # Features
        features = [Feature(**{f: cv(r, f) for f in Feature.model_fields}) for r in rows(extraction, "features")]

        # Standards
        standards = [Standard(**{f: cv(r, f) for f in Standard.model_fields}) for r in rows(extraction, "standards")]

        # Integrations
        integrations = [Integration(**{f: cv(r, f) for f in Integration.model_fields}) for r in rows(extraction, "integrations")]

        # Funding rounds
        funding_rounds = [FundingRound(**{f: cv(r, f) for f in FundingRound.model_fields}) for r in rows(extraction, "funding_round")]

        # Governance
        gov = extraction.get("governance_model", {})
        governance_models = [GovernanceModel(**{f: cv(gov if isinstance(gov, dict) and "rows" not in gov else r, f) for f in GovernanceModel.model_fields})
                            for r in ([gov] if isinstance(gov, dict) and "rows" not in gov else rows(extraction, "governance_model"))]

        # Compliance
        compliance_certs = [ComplianceCertification(**{f: cv(r, f) for f in ComplianceCertification.model_fields}) for r in rows(extraction, "compliance_certifications")]

        # SLA
        sla = [SlaCommitment(**{f: cv(r, f) for f in SlaCommitment.model_fields}) for r in rows(extraction, "sla_commitments")]

        # Stability
        stab = extraction.get("stability_table", {})
        stability_entries = [StabilityEntry(**{f: cv(stab if isinstance(stab, dict) and "rows" not in stab else r, f) for f in StabilityEntry.model_fields})
                           for r in ([stab] if isinstance(stab, dict) and "rows" not in stab else rows(extraction, "stability_table"))]

        # Tech stack
        tech_stack = [TechStackEntry(**{f: cv(r, f) for f in TechStackEntry.model_fields}) for r in rows(extraction, "tech_stack")]

        # API capabilities
        api_caps = [ApiCapability(**{f: cv(r, f) for f in ApiCapability.model_fields}) for r in rows(extraction, "api_capabilities")]

        # Partnerships
        partnerships = [Partnership(**{f: cv(r, f) for f in Partnership.model_fields}) for r in rows(extraction, "partnerships")]

        # Exchange listings
        exchange_listings = [ExchangeListing(**{f: cv(r, f) for f in ExchangeListing.model_fields}) for r in rows(extraction, "exchange_listings")]

        # Regulatory licenses
        reg_licenses = [RegulatoryLicense(**{f: cv(r, f) for f in RegulatoryLicense.model_fields}) for r in rows(extraction, "regulatory_licenses")]

        # Platform metrics
        pm = extraction.get("platform_metrics", {})
        platform_metrics = [PlatformMetric(**{f: cv(pm if isinstance(pm, dict) and "rows" not in pm else r, f) for f in PlatformMetric.model_fields})
                          for r in ([pm] if isinstance(pm, dict) and "rows" not in pm else rows(extraction, "platform_metrics"))]

        # Deal case studies
        deals = [DealCaseStudy(**{f: cv(r, f) for f in DealCaseStudy.model_fields}) for r in rows(extraction, "deal_case_studies")]

        return CompanyData(
            profile=profile, products=products, asset_classes=asset_classes,
            features=features, standards=standards, integrations=integrations,
            funding_rounds=funding_rounds, governance_models=governance_models,
            compliance_certifications=compliance_certs, sla_commitments=sla,
            stability_entries=stability_entries, tech_stack=tech_stack,
            api_capabilities=api_caps, partnerships=partnerships,
            exchange_listings=exchange_listings, regulatory_licenses=reg_licenses,
            platform_metrics=platform_metrics, deal_case_studies=deals,
        )

    @staticmethod
    def _merge_data(existing: CompanyData, new: CompanyData) -> None:
        """Merge new data into existing, only filling None fields or higher confidence."""
        def _merge_model(old_model, new_model):
            for fn in old_model.__class__.model_fields:
                old_val = getattr(old_model, fn)
                new_val = getattr(new_model, fn)
                if isinstance(old_val, CitedValue) and isinstance(new_val, CitedValue):
                    if not old_val.is_filled() and new_val.is_filled():
                        setattr(old_model, fn, new_val)
                    elif old_val.is_filled() and new_val.is_filled():
                        if new_val.confidence > old_val.confidence:
                            setattr(old_model, fn, new_val)

        _merge_model(existing.profile, new.profile)

        list_pairs = [
            (existing.products, new.products),
            (existing.asset_classes, new.asset_classes),
            (existing.features, new.features),
            (existing.standards, new.standards),
            (existing.integrations, new.integrations),
            (existing.funding_rounds, new.funding_rounds),
            (existing.governance_models, new.governance_models),
            (existing.compliance_certifications, new.compliance_certifications),
            (existing.sla_commitments, new.sla_commitments),
            (existing.stability_entries, new.stability_entries),
            (existing.tech_stack, new.tech_stack),
            (existing.api_capabilities, new.api_capabilities),
            (existing.partnerships, new.partnerships),
            (existing.exchange_listings, new.exchange_listings),
            (existing.regulatory_licenses, new.regulatory_licenses),
            (existing.platform_metrics, new.platform_metrics),
            (existing.deal_case_studies, new.deal_case_studies),
        ]
        for old_list, new_list in list_pairs:
            for i in range(min(len(old_list), len(new_list))):
                _merge_model(old_list[i], new_list[i])
            for i in range(len(old_list), len(new_list)):
                old_list.append(new_list[i])


async def run_pipeline(
    company_name: str, domain: str,
    max_passes: int = 3, timeout: int = 300,
    output_dir: str = "output",
) -> PipelineResult:
    runner = PipelineRunner(max_passes=max_passes, pipeline_timeout=timeout)
    result = await runner.run(company_name, domain)

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    safe_name = domain.replace(".", "_").replace("/", "_")
    json_path = out_path / f"{safe_name}.json"
    json_path.write_text(result.to_json())
    logger.info("Results saved to %s", json_path)
    return result
