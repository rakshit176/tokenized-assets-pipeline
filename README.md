# 51 Insights Pipeline — Tokenized Asset Data Extraction

Automated multi-pass data extraction pipeline for 200+ tokenized asset companies. Takes a company name + domain, performs deep web search + scraping + multi-pass LLM extraction, and produces structured output with **303 fields across 17 tables** — each field cited with source URL and confidence score.

```
Input:  python step_run.py Securitize securitize.io
Output: securitize_io.json + securitize_io.xlsx (3 tabs: Schema, LLM Cost, Evaluation)
```

---

## Table of Contents

1. [Architecture and Approach](#architecture-and-approach)
2. [Complete Pipeline Flow](#complete-pipeline-flow)
3. [Model and Tool Selection Rationale](#model-and-tool-selection-rationale)
4. [Measured Results](#measured-results)
5. [Cost and Time Projections (200+ Companies)]#cost-and-time-projections-200-companies)
6. [Quick Start](#quick-start)
7. [Data Schema](#data-schema-17-tables-303-fields)
8. [Project Structure](#project-structure)
9. [Known Limitations and Improvements](#known-limitations-and-improvements)

---

## Architecture and Approach

### Design Philosophy

The pipeline follows a **multi-pass extraction** pattern inspired by academic RAG systems: gather broad context first, then extract in focused batches, then fill gaps with targeted follow-up passes. This trades latency for accuracy — each pass improves data quality.

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    51 INSIGHTS PIPELINE v3                              │
│                                                                         │
│  INPUT: company_name + domain (e.g. "Securitize", "securitize.io")     │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │  PHASE 1: DEEP WEB SEARCH (SearXNG, ~28s)                      │   │
│  │                                                                   │   │
│  │  20 targeted queries covering all 17 schema tables:              │   │
│  │  Company overview, products, funding, tech/API, compliance,      │   │
│  │  partnerships, exchanges, governance, SLA, metrics, employees    │   │
│  │  Concurrency: 4 parallel with retry + exponential backoff        │   │
│  │  Results: ~160 URLs + snippets per company                        │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │  PHASE 2: SMART SCRAPE (httpx + Playwright fallback, ~17s)      │   │
│  │                                                                   │   │
│  │  A. Company domain crawl (31 paths)                              │   │
│  │  B. Internal link discovery (up to 30 additional pages)         │   │
│  │  C. Search result pages (top external URLs)                      │   │
│  │  D. Subdomain/deep pages from search results                    │   │
│  │                                                                   │   │
│  │  Two-phase fetch: httpx (fast) → Playwright (lazy, SPAs only)   │   │
│  │  Content: trafilatura (clean) + selectolax (raw, Rust-backed)   │   │
│  │  robots.txt: advisory (logs but doesn't block)                   │   │
│  │  Result: ~10-42 pages with full text + metadata                  │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │  PHASE 3: LLM EXTRACTION — 6 PARALLEL BATCHES (~23s)           │   │
│  │                                                                   │   │
│  │  Batch A: Company Profile (20 fields)                            │   │
│  │  Batch B: Products + Assets + Features + Standards (35 fields)  │   │
│  │  Batch C: Funding + Governance (21 fields)                       │   │
│  │  Batch D: Compliance + SLA + Stability (18 fields)              │   │
│  │  Batch E: Tech Stack + API (16 fields)                           │   │
│  │  Batch F: Partners + Licenses + Metrics + Deals (29 fields)     │   │
│  │                                                                   │   │
│  │  Each batch: filtered context → LLM → JSON with citations        │   │
│  │  Runs concurrently (Semaphore(3) for OpenAI)                     │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │  PHASE 4: KNOWLEDGE GAP FILL (~32s)                             │   │
│  │                                                                   │   │
│  │  Identify fields with confidence < 0.4                           │   │
│  │  Run targeted extraction with focused prompt                     │   │
│  │  Merge results (higher confidence wins)                          │   │
│  │  Apply defaults for remaining empty fields                       │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │  PHASE 5: VALIDATE + OUTPUT (~1s)                               │   │
│  │                                                                   │   │
│  │  1. Map LLM JSON → Pydantic CitedValue[T] models                │   │
│  │  2. Merge multi-pass results (highest confidence wins)           │   │
│  │  3. Calculate fill metrics (overall, real, high)                 │   │
│  │  4. Save: JSON + Excel (3 tabs) + PostgreSQL                     │   │
│  │  5. Log LLM cost per call to database                            │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  OUTPUT: JSON + Excel + PostgreSQL                                      │
└─────────────────────────────────────────────────────────────────────────┘
```

### Handling Missing/Ambiguous Data

1. **CitedValue[T]** — every field has `{value, source_url, confidence}`. Missing data gets `value=None, confidence=0.0`
2. **Confidence scale** — 0.9 = company website, 0.7 = reputable third-party, 0.5 = LLM knowledge, 0.4 = inferred, 0.1-0.3 = default/placeholder
3. **Multi-pass merge** — higher confidence values overwrite lower ones
4. **Defaults** — empty tables get 1 row with placeholder values (confidence 0.1)
5. **Three fill metrics** — overall (includes defaults), real (conf >= 0.4), high (conf >= 0.7)

---

## Model and Tool Selection Rationale

### LLM Provider Selection

| Provider | Model | Cost/1K tokens | Speed | Fill Rate | Why |
|----------|-------|----------------|-------|-----------|-----|
| **OpenAI** (selected) | gpt-4o-mini | $0.15/$0.60 | Fast | 94.8% | Best accuracy/cost ratio |
| z.ai | glm-4-plus-0111 | Free | Slow | 80.7% | Zero cost but lower quality |
| Anthropic | Claude Sonnet 4 | $3.00/$15.00 | Medium | ~85%* | Highest quality but 20x cost |
| OpenRouter | 200+ models | Varies | Varies | — | Flexible but adds latency |

*Estimated based on limited testing (insufficient credits for full run)

**Why gpt-4o-mini**: At ~$0.008/company (32K tokens), it delivers 94.8% real fill at high speed (23s LLM time). The cost is negligible even at 200+ companies (~$1.60 total). Claude Sonnet 4 would cost ~$0.16/company (20x more) for marginal accuracy improvement. The free z.ai option is viable for cost-sensitive batch runs but sacrifices ~14% fill rate.

### Search: SearXNG vs Alternatives

| Option | Cost | Results | Why |
|--------|------|---------|-----|
| **SearXNG** (selected) | Free | 160/company | Self-hosted, 70+ engines, JSON output |
| Google Custom Search | $5/1K queries | Similar | Would cost ~$20 for 200 companies |
| Bing Web Search | $3/1K queries | Similar | Slightly cheaper but requires Azure |
| SerpAPI | $50/5K queries | Best | Most expensive, similar results |

**Why SearXNG**: Zero marginal cost, runs in Docker, aggregates 70+ search engines. The tradeoff is slightly slower queries (~28s for 20 queries) and occasional rate limiting from upstream engines.

### Scraping: httpx + Playwright (lazy) vs Alternatives

| Option | Speed | SPA Support | Why |
|--------|-------|-------------|-----|
| **httpx + Playwright lazy** (selected) | 5-35s | Yes | httpx for 90% of pages, Playwright only for SPA docs |
| Pure Playwright | 60-120s | Yes | 10x slower, unnecessary for most pages |
| Scrapy | 10-20s | No | Fast but can't handle JavaScript-heavy docs pages |
| Firecrawl/Jina Reader | 5-10s | Yes | Paid API, would add ~$0.01-0.05/company |

### HTML Parsing: selectolax vs Alternatives

| Option | Speed | Why |
|--------|-------|-----|
| **selectolax** (selected) | 10-50x faster | Rust-backed (Modest), handles malformed HTML |
| BeautifulSoup | Baseline | Python-only, significantly slower on large pages |
| lxml | Fast | Good but harder API for text extraction |

### What I'd Mix with More Time

- **Haiku for Batches A-D** (simple extraction) + **Sonnet for Batches E-F** (complex multi-row tables) — could cut cost by 50% with minimal accuracy loss
- **Crawl4AI** for deeper SPA scraping on specific company documentation portals
- **Embedding-based reranking** of search results to prioritize the most relevant pages per batch

---

## Measured Results

### Per-Company Performance (OpenAI gpt-4o-mini)

| Company | Real Fill | High Fill | Pages | Tokens | Cost (USD) | Time |
|---------|-----------|-----------|-------|--------|------------|------|
| **Securitize** | **94.8%** | 42.9% | 10 | 32,208 | $0.0079 | 89s |
| **Ondo Finance** | **79.3%** | 24.3% | 4 | 33,010 | $0.0079 | 90s |
| **Centrifuge** | **76.4%** | 36.9% | 42 | 32,603 | $0.0078 | 120s |
| **Average** | **83.5%** | 34.7% | 19 | 32,607 | $0.0079 | 100s |

### Phase Breakdown (Average)

| Phase | Time | % of Total |
|-------|------|------------|
| Search (20 queries) | 28s | 28% |
| Scrape (10-42 pages) | 17s | 17% |
| LLM (6 batches + gap fill) | 55s | 55% |
| Validate + Output | <1s | <1% |
| **Total** | **100s** | **100%** |

### LLM Call Detail (Securitize)

| Batch | Prompt Tokens | Completion Tokens | Cost | Latency |
|-------|---------------|-------------------|------|---------|
| BatchA: Company | 4,484 | 1,534 | $0.0017 | 8s |
| BatchB: Products | 5,191 | 1,408 | $0.0015 | 22s |
| BatchC: Funding | 4,673 | 1,119 | $0.0012 | 9s |
| BatchD: Compliance | 4,682 | 895 | $0.0010 | 6s |
| BatchE: Tech | 4,349 | 862 | $0.0009 | 6s |
| BatchF: Partners | 5,269 | 1,085 | $0.0012 | 10s |
| Knowledge Gap | 3,955 | 2,756 | $0.0021 | 34s |
| **Total** | **32,603** | **9,659** | **$0.0079** | **95s** |

### Why Fill Rates Vary

- **Securitize (94.8%)** — well-known company, extensive web presence, 10 pages scraped
- **Ondo Finance (79.3%)** — newer company, only 4 pages available (website blocks scraping), relies more on LLM knowledge
- **Centrifuge (76.4%)** — 42 pages scraped but much is developer documentation, not company info

---

## Cost and Time Projections (200+ Companies)

### Per-Company Cost Breakdown

| Component | Cost | Notes |
|-----------|------|-------|
| LLM (gpt-4o-mini, 32K tokens) | $0.008 | 7 API calls × ~4.6K tokens avg |
| Search (SearXNG) | $0.000 | Self-hosted, zero marginal cost |
| Scraping (httpx + Playwright) | $0.000 | Self-hosted, bandwidth only |
| **Total per company** | **$0.008** | |

### Scaling Projections

| Companies | Sequential | 3 Workers | 5 Workers | Cost (gpt-4o-mini) | Cost (z.ai) |
|-----------|-----------|-----------|-----------|---------------------|-------------|
| 1 | 100s | 100s | 100s | $0.008 | $0 |
| 10 | 17 min | 7 min | 5 min | $0.08 | $0 |
| 50 | 83 min | 33 min | 22 min | $0.40 | $0 |
| **200** | **5.6 hr** | **2.2 hr** | **1.3 hr** | **$1.58** | **$0** |
| 300 | 8.3 hr | 3.3 hr | 2.0 hr | $2.37 | $0 |

### Parallelization

The pipeline parallelizes at multiple levels:

1. **Company-level** — Run multiple companies in parallel workers (main bottleneck). Each is fully independent.
2. **Search queries** — 4 parallel SearXNG queries per company (Semaphore(4))
3. **Scraping** — 8 concurrent page fetches per company (Semaphore(8))
4. **LLM batches** — 3 concurrent API calls per company (Semaphore(3) for OpenAI)

With 5 workers on a single machine, 200 companies takes ~1.3 hours. With distributed workers (e.g. Kubernetes), it scales linearly — 20 workers would process 200 companies in ~20 minutes.

### Cost Comparison Across Providers

| Provider | Per Company | 200 Companies | Accuracy Tradeoff |
|----------|------------|---------------|-------------------|
| z.ai (free) | $0 | $0 | -14% fill rate vs OpenAI |
| gpt-4o-mini | $0.008 | $1.58 | Baseline |
| gpt-4o | $0.12 | $24 | +2-3% fill rate |
| Claude Sonnet 4 | $0.16 | $32 | +3-5% fill rate estimate |

---

## Quick Start

### 1. Start Infrastructure

```bash
docker compose up -d    # SearXNG + Redis + PostgreSQL
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env — set LLM_PROVIDER and corresponding API key
```

### 3. Install Dependencies

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 4. Run on Companies

```bash
# Single company
python step_run.py Securitize securitize.io

# Multiple companies
python step_run.py Securitize securitize.io "Ondo Finance" ondo.finance Centrifuge centrifuge.io

# Default (Securitize)
python step_run.py
```

### 5. Output

Each company produces:
- `output/{domain}.json` — full structured data with citations
- `output/{domain}.xlsx` — 3 tabs: Schema Data, LLM Cost, Evaluation
- `output/comparison.xlsx` — side-by-side comparison (when multiple companies)

### 6. Run Tests

```bash
python -m pytest tests/ -v
```

---

## Data Schema (17 Tables, 303 Fields)

Every field uses `CitedValue[T]` with `value`, `source_url`, and `confidence` (0.0–1.0).

| # | Table | Type | Fields | Purpose |
|---|-------|------|--------|---------|
| 1 | companies (profile) | Single row | 20 | Identity, location, status |
| 2 | products | Multi-row | 9 | Product catalog with pricing |
| 3 | asset_classes | Multi-row | 5 | Tokenized asset types |
| 4 | features | Multi-row | 5 | Platform feature breakdown |
| 5 | standards | Multi-row | 3 | Token standard compliance |
| 6 | integrations | Multi-row | 6 | Third-party integrations |
| 7 | funding_round | Multi-row | 12 | Investment history |
| 8 | governance_model | Single row | 9 | DAO/token governance |
| 9 | compliance_certifications | Multi-row | 7 | SOC2, ISO, audits |
| 10 | sla_commitments | Multi-row | 7 | Uptime, reliability |
| 11 | stability_table | Single row | 4 | Documentation, sandbox |
| 12 | tech_stack | Multi-row | 7 | Blockchain, chains |
| 13 | api_capabilities | Single row | 9 | API docs, SDK, rate limits |
| 14 | partnerships | Multi-row | 7 | Strategic partners |
| 15 | exchange_listings | Multi-row | 5 | Trading venues |
| 16 | regulatory_licenses | Multi-row | 11 | SEC, FINRA, jurisdiction |
| 17 | platform_metrics | Single row | 5 | AUM, clients, issuances |
| 18 | deal_case_studies | Multi-row | 8 | Notable tokenization deals |

All data is persisted to PostgreSQL with per-call LLM cost tracking.

---

## Project Structure

```
fiftyone_insight/
├── src/
│   ├── orchestrator.py              # Pipeline runner — multi-pass extraction
│   ├── schema/
│   │   └── models.py                # 17 Pydantic tables with CitedValue[T]
│   ├── search/
│   │   └── client.py                # SearXNG client — deep_search, gap_search
│   ├── scrape/
│   │   └── scraper.py               # Async httpx + Playwright scraper
│   ├── extractor/
│   │   └── llm.py                   # 6-batch LLM extraction + gap fill
│   ├── providers/
│   │   ├── base.py                  # BaseLLMProvider + LLMCallResult
│   │   ├── zai_provider.py          # z.ai (free GLM models)
│   │   ├── openai_provider.py       # OpenAI (GPT-4o-mini)
│   │   ├── anthropic_provider.py    # Anthropic (Claude Sonnet 4)
│   │   ├── openrouter_provider.py   # OpenRouter (200+ models)
│   │   └── factory.py              # Provider selection via LLM_PROVIDER env
│   ├── database/
│   │   └── saver.py                 # PostgreSQL persistence + LLM cost tracking
│   └── api/
│       ├── server.py                # FastAPI server
│       └── cli.py                   # Click CLI
├── database/
│   └── schema.sql                   # PostgreSQL schema (19 tables)
├── config/
│   └── searxng/settings.yml         # SearXNG configuration
├── output/                          # Pipeline results (JSON + Excel)
├── tests/
│   ├── test_pipeline.py             # Unit tests
│   └── test_full_pipeline.py        # Integration tests
├── step_run.py                      # Main runner — accepts any company
├── docker-compose.yml               # SearXNG + Redis + PostgreSQL
├── .env.example                     # Environment template
├── .gitignore
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## Known Limitations and Improvements

### Current Limitations

1. **Website scraping coverage** — Some sites (like Ondo Finance) block automated requests, yielding only 4 pages. This reduces fill rate from ~95% to ~79%. Could be improved with rotating proxies or headless browser fingerprint rotation.

2. **LLM non-determinism** — Same company may get slightly different results across runs (~1-2% fill rate variance). Structured outputs (OpenAI's `response_format`) help but don't eliminate this.

3. **Context window waste** — All scraped pages are sent to every batch, even when most aren't relevant. Embedding-based page ranking per batch would improve both accuracy and token efficiency.

4. **Single-model extraction** — All 6 batches use the same model. Smaller/cheaper models could handle simple batches (Company Profile) while larger models handle complex ones (Partnerships + Licenses).

5. **No validation against external sources** — Extracted funding amounts, employee counts, etc. are not cross-checked against structured databases (Crunchbase API, LinkedIn, etc.).

### What I'd Improve with More Time

1. **Multi-model routing** — Use GPT-4o-mini for simple batches, Claude Haiku for medium, GPT-4o for complex. Estimated 40% cost reduction with <1% accuracy loss.

2. **Caching layer** — Cache search results and scraped pages in Redis. Re-runs on the same company would skip straight to LLM extraction, saving ~45s.

3. **Incremental updates** — Only re-extract fields that changed since last run, using timestamps and diff detection.

4. **Confidence calibration** — Validate extracted values against known ground truth (e.g. funding amounts from Crunchbase) to calibrate confidence scores.

5. **Batch API mode** — Use OpenAI Batch API for 50% cost reduction on non-urgent runs (24-hour turnaround is fine for periodic company updates).

6. **Human-in-the-loop** — Flag fields with confidence 0.4-0.6 for manual review, rather than accepting or rejecting outright.

7. **Structured output enforcement** — Use OpenAI's Structured Outputs (JSON Schema) instead of `response_format: json_object` for guaranteed schema compliance.

---

## License

Proprietary — 51 Insights project.
