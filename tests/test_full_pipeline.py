"""
Full end-to-end pipeline test with real LLM extraction.

Tests the complete 30-second pipeline:
1. Scrape company pages (real HTTP)
2. LLM extraction via z-ai CLI (real API)
3. Structured output

Run: PYTHONPATH=. .venv/bin/python3 tests/test_full_pipeline.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    from src.orchestrator import PipelineRunner
    from src.scrape.scraper import AsyncScraper
    from src.extractor.llm import LLMExtractor

    print("🚀 Full Pipeline Test — Real Scrape + Real LLM")
    print("=" * 60)

    # --- Test company ---
    company_name = "Chainlink"
    domain = "chain.link"

    # Phase 1: Scrape real pages
    print(f"\n📡 Phase 1: Scraping {domain}...")
    t1 = time.perf_counter()
    scraper = AsyncScraper(timeout=10, max_concurrent=5)
    scraped_pages = await scraper.get_company_pages(domain)
    scrape_time = time.perf_counter() - t1
    print(f"  Scraped {len(scraped_pages)} pages in {scrape_time:.2f}s")
    for url, page in scraped_pages.items():
        print(f"    {url}: {len(page.text)} chars | title: {page.title[:50] if page.title else 'N/A'}")

    # Combine scraped text for context
    scraped_text = ""
    for url, page in scraped_pages.items():
        scraped_text += f"\n--- {page.title} ({url}) ---\n{page.text}\n"
    print(f"  Total context: {len(scraped_text)} chars")

    # Phase 2: LLM extraction via z-ai
    print(f"\n🤖 Phase 2: LLM extraction for {company_name}...")
    t2 = time.perf_counter()
    extractor = LLMExtractor()

    # Check LLM access
    if extractor._zai_cli:
        print(f"  Using z-ai CLI: {extractor._zai_cli}")
    elif extractor.api_key:
        print(f"  Using direct API with key")
    else:
        print("  ❌ No LLM access available!")
        return

    extraction = await extractor.extract_all(
        company_name=company_name,
        domain=domain,
        search_results={},
        scraped_pages=scraped_pages,
    )
    llm_time = time.perf_counter() - t2
    print(f"  LLM extraction completed in {llm_time:.2f}s")
    print(f"  Extraction keys: {list(extraction.keys())}")

    # Show extracted data
    for table_name, data in extraction.items():
        if isinstance(data, dict):
            filled = sum(1 for v in data.values() if isinstance(v, dict) and v.get("value") is not None)
            total = sum(1 for v in data.values() if isinstance(v, dict))
            print(f"    {table_name}: {filled}/{total} fields filled")
            # Show a few sample values
            for k, v in list(data.items())[:3]:
                if isinstance(v, dict) and v.get("value") is not None:
                    print(f"      {k}: {v['value']} (conf: {v.get('confidence', 'N/A')})")

    # Phase 3: Structure output
    print(f"\n📊 Phase 3: Structuring output...")
    t3 = time.perf_counter()
    from src.orchestrator import PipelineRunner
    company_data = PipelineRunner._structure_output(extraction, company_name, domain)
    structure_time = time.perf_counter() - t3

    fill_rate = company_data.confidence_score()
    print(f"  Structured in {structure_time:.2f}s")
    print(f"  Fill rate: {fill_rate:.2%}")

    # Show profile highlights
    profile = company_data.profile
    print(f"\n📋 Company Profile Highlights:")
    for field_name in profile.model_fields:
        val = getattr(profile, field_name)
        if val.value is not None:
            print(f"  {field_name}: {val.value} (confidence: {val.confidence:.0%}, source: {val.source_url or 'N/A'})")

    print(f"\n📦 Sub-tables:")
    print(f"  Products: {len(company_data.products)}")
    print(f"  Funding rounds: {len(company_data.funding_rounds)}")
    print(f"  Tech stack: {len(company_data.tech_stack)}")
    print(f"  API capabilities: {len(company_data.api_capabilities)}")
    print(f"  Partnerships: {len(company_data.partnerships)}")
    print(f"  Compliance certs: {len(company_data.compliance_certifications)}")
    print(f"  Regulatory licenses: {len(company_data.regulatory_licenses)}")
    print(f"  Exchange listings: {len(company_data.exchange_listings)}")
    print(f"  Platform metrics: {len(company_data.platform_metrics)}")
    print(f"  Stability entries: {len(company_data.stability_entries)}")
    print(f"  Deal case studies: {len(company_data.deal_case_studies)}")
    print(f"  SLA commitments: {len(company_data.sla_commitments)}")
    print(f"  Governance models: {len(company_data.governance_models)}")

    # Total timing
    total_time = scrape_time + llm_time + structure_time
    print(f"\n⏱ Total Pipeline Time: {total_time:.2f}s")
    print(f"  Phase 1 (Scrape): {scrape_time:.2f}s")
    print(f"  Phase 2 (LLM):    {llm_time:.2f}s")
    print(f"  Phase 3 (Structure): {structure_time:.2f}s")

    # Save output
    output_dir = "/home/z/my-project/tokenized_assets_pipeline/output"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{domain.replace('.', '_')}.json")

    result_data = {
        "company_name": company_name,
        "domain": domain,
        "timing": {
            "phase1_scrape": round(scrape_time, 2),
            "phase2_llm": round(llm_time, 2),
            "phase3_structure": round(structure_time, 2),
            "total": round(total_time, 2),
        },
        "fill_rate": fill_rate,
        "data": company_data.model_dump(),
    }

    with open(output_path, "w") as f:
        json.dump(result_data, f, indent=2, default=str)

    print(f"\n💾 Output saved to: {output_path}")
    print(f"\n{'='*60}")
    print(f"✅ Pipeline test complete!")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
