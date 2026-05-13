# 51 Insights Pipeline — Tokenized Asset Data Extraction

Automated multi-pass data extraction pipeline for 200+ tokenized asset companies. Takes a company name + domain, performs deep web search + scraping + multi-pass LLM extraction, and produces structured output with **303 fields across 17 tables** — each field cited with source URL and confidence score.

```
Input:  company_name + domain  (e.g. "Securitize", "securitize.io")
Output: JSON + Excel (.xlsx) + PostgreSQL   (3-tab workbook: Schema, LLM Cost, Evaluation)
```

---

## Table of Contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [Complete Pipeline Flow](#complete-pipeline-flow)
4. [Quick Start — Docker Compose](#quick-start--docker-compose)
5. [Environment Variables](#environment-variables)
6. [API Endpoints](#api-endpoints)
7. [Web UI](#web-ui)
8. [Model and Provider Selection](#model-and-provider-selection)
9. [Measured Results](#measured-results)
10. [Cost and Time Projections](#cost-and-time-projections)
11. [Data Schema (17 Tables, 303 Fields)](#data-schema-17-tables-303-fields)
12. [Project Structure](#project-structure)
13. [Known Limitations](#known-limitations)

---

## Features

### Core Pipeline
- **Multi-pass extraction**: 6 LLM batches + agentic gap search + knowledge gap fill
- **Deep web search**: 20+ targeted queries via self-hosted SearXNG
- **Smart scraping**: httpx + lazy Playwright fallback for SPAs; thin-content re-render
- **Agentic search loop**: LLM autonomously generates targeted queries and selects URLs to scrape for missing fields
- **303 fields across 17 tables**: Comprehensive tokenized asset data
- **CitedValue[T]**: Every field includes `{ value, source_url, confidence }`

### Production Features
- **Full Docker Compose stack**: PostgreSQL, Redis, SearXNG, API, worker, Next.js frontend — single command
- **FastAPI backend**: Async pipeline execution via `BackgroundTasks`; no ARQ/Celery required
- **Next.js frontend**: Single and batch processing UI with live progress tracking
- **Duplicate detection**: Popup dialog when a company already exists — choose Incremental Update or Start from Scratch
- **Incremental updates**: Re-extract only low-confidence fields — 79% faster, 87% cheaper
- **Download XLSX**: One-click Excel report download from the company detail page
- **Batch processing**: CSV upload or manual entry; parallel or sequential execution
- **Database persistence**: PostgreSQL with LLM cost tracking per field
- **Provider factory**: Plug-and-play LLM providers (OpenAI, Anthropic, z.ai, OpenRouter) — switch via env var
- **Caching layer**: File-based LLM response cache (87% cost savings on cache hits)
- **Rate limiting**: Provider-specific limits with exponential backoff
- **Per-field validation**: URLs, years, amounts, counts, status codes
- **Confidence calibration**: Source reliability scoring

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                     51 INSIGHTS PIPELINE v3                            │
│                                                                        │
│  INPUT: company_name + domain                                          │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  PHASE 1 — DEEP WEB SEARCH  (SearXNG, ~28s)                    │  │
│  │  20 targeted queries → ~160 URLs + snippets per company         │  │
│  │  Concurrency: 8 parallel with retry + exponential backoff       │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                              │                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  PHASE 2 — SMART SCRAPE  (httpx + Playwright fallback, ~17s)   │  │
│  │  A. Company domain crawl (45+ paths)                            │  │
│  │  B. Internal link discovery (up to 50 additional pages)        │  │
│  │  C. External search-result URLs (top 3 per query)              │  │
│  │  D. Thin-content fallback: <200 chars → Playwright re-render   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                              │                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  PHASE 3 — LLM EXTRACTION  (6 parallel batches, ~23s)          │  │
│  │  Batch A: Company Profile (20 fields)                           │  │
│  │  Batch B: Products + Assets + Features + Standards (35 fields)  │  │
│  │  Batch C: Funding + Governance (21 fields)                      │  │
│  │  Batch D: Compliance + SLA + Stability (18 fields)              │  │
│  │  Batch E: Tech Stack + API (16 fields)                          │  │
│  │  Batch F: Partners + Licenses + Metrics + Deals (29 fields)    │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                              │                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  PHASE 4 — AGENTIC GAP SEARCH  (~43s, 2 iterations max)        │  │
│  │  LLM identifies missing fields → generates targeted queries     │  │
│  │  Selects best URLs from snippets → scrapes → re-extracts        │  │
│  │  Uses provider factory (same LLM_PROVIDER env var)              │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                              │                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  PHASE 5 — KNOWLEDGE GAP FILL  (~32s)                          │  │
│  │  Fields still missing after agentic loop → LLM knowledge fill  │  │
│  │  Confidence 0.5 (LLM knowledge, no cited source)               │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                              │                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  PHASE 6 — VALIDATE + OUTPUT  (~1s)                            │  │
│  │  Pydantic CitedValue[T] mapping → confidence calibration        │  │
│  │  Per-field validation → multi-pass merge (highest conf wins)   │  │
│  │  Save: JSON + Excel (3 tabs) + PostgreSQL                       │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  OUTPUT: JSON + Excel (.xlsx) + PostgreSQL                             │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Complete Pipeline Flow

```
company_name + domain
  → SearXNG deep_search (20 queries, 8 concurrent)
  → httpx + Playwright scraping (45+ paths, 50 internal links)
  → 6-batch LLM extraction (parallel)
  → Agentic gap search loop (2 iterations, cheap LLM calls)
  → Knowledge gap fill (LLM knowledge for remaining fields)
  → Validation + calibration
  → JSON + Excel + PostgreSQL
```

**Key data model:**
- `CitedValue[T]` — `{ value, source_url, confidence }` on every field
- Confidence scale: `0.9` = company website, `0.7` = reputable third-party, `0.5` = LLM knowledge
- Three fill metrics: **Overall** (includes defaults), **Real** (conf ≥ 0.4), **High** (conf ≥ 0.7)

---

## Quick Start — Docker Compose

### Prerequisites

- Docker + Docker Compose v2
- An LLM API key (OpenAI, Anthropic, z.ai, or OpenRouter)

### 1. Clone and configure

```bash
git clone <repo>
cd fiftyone_insight
cp .env.example .env
# Edit .env — set at minimum LLM_PROVIDER + the matching API key
```

### 2. Start the full stack

```bash
docker compose up -d
```

This starts six services:

| Service | Port | Description |
|---------|------|-------------|
| `postgres` | 5432 | Primary data store |
| `redis` | 6379 | Cache and queue backend |
| `searxng` | 8888 | Self-hosted meta-search engine |
| `api` | 8000 | FastAPI backend |
| `worker` | — | Background pipeline workers (2 replicas) |
| `frontend` | 3000 | Next.js web UI |

### 3. Open the UI

```
http://localhost:3000
```

Use **Single Process** to run one company or **Batch Intelligence** to upload a CSV.

### 4. Run via CLI (optional)

```bash
# Single company
docker compose run --rm pipeline python step_run.py Securitize securitize.io

# Batch from CSV
docker compose run --rm pipeline python batch_run.py companies.csv
```

### 5. Useful commands

```bash
# View logs
docker compose logs -f api
docker compose logs -f worker

# Restart API after code changes
docker compose build api && docker compose up -d api

# Rebuild frontend after UI changes
docker compose build frontend && docker compose up -d frontend

# Stop everything
docker compose down

# Stop and remove volumes (wipes DB)
docker compose down -v
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in:

```bash
# LLM provider — one of: openai | anthropic | zai | openrouter
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini

# Provider API keys (only the selected provider is required)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
ZAI_API_KEY=...
OPENROUTER_API_KEY=sk-or-...

# Database (defaults match docker-compose.yml)
POSTGRES_DB=fiftyone_insight
POSTGRES_USER=fiftyone
POSTGRES_PASSWORD=fiftyone_secret

# SearXNG (auto-configured in Docker)
SEARXNG_URL=http://searxng:8080
SEARXNG_SECRET=change_me

# Redis (auto-configured in Docker)
REDIS_HOST=redis
REDIS_PORT=6379
```

---

## API Endpoints

The FastAPI backend runs on `http://localhost:8000`. Interactive docs at `/docs`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Service health check |
| `POST` | `/run` | Run pipeline for a single company (async) |
| `POST` | `/incremental` | Incremental update — re-extract low-confidence fields only |
| `POST` | `/batch` | Run pipeline for multiple companies (async, parallel) |
| `GET` | `/companies` | List all processed companies |
| `GET` | `/company/{domain}` | Get full company detail by domain |
| `GET` | `/download/{domain}` | Download Excel report (.xlsx) |
| `GET` | `/docs` | OpenAPI interactive documentation |

### Example: Run single company

```bash
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{"company_name": "Securitize", "domain": "securitize.io"}'
```

### Example: Batch run

```bash
curl -X POST http://localhost:8000/batch \
  -H "Content-Type: application/json" \
  -d '{
    "companies": [
      {"company_name": "Securitize", "domain": "securitize.io"},
      {"company_name": "Ondo Finance", "domain": "ondo.finance"}
    ],
    "max_concurrent": 3
  }'
```

Poll for completion with `GET /company/{domain}` — returns 404 while processing, 200 when done.

---

## Web UI

The Next.js frontend (`http://localhost:3000`) provides:

### Single Process
- Enter company name + domain → run the full pipeline
- Live step-by-step progress (Web Search → Scraping → Extraction → Validation → Save)
- If the company already exists in the database, a popup asks:
  - **Incremental Update** — only re-extracts low-confidence and missing fields (faster, cheaper)
  - **Start from Scratch** — full re-run, replaces all existing data

### Batch Intelligence
- Upload a CSV (`company_name, domain` columns) or add companies manually
- Duplicate detection: shows a dialog when any submitted company already exists
- Live per-company status tracking
- Summary stats on completion

### Company Dashboard
- Browse all processed companies with status and fill rates
- View full company detail (all 17 tables, cited sources)
- **Download XLSX** button for one-click Excel export

---

## Model and Provider Selection

The pipeline uses a **provider factory** — switch providers by changing `LLM_PROVIDER` in `.env`. No code changes needed.

| Provider | Model (default) | Cost/1M tokens | Fill Rate | Notes |
|----------|----------------|----------------|-----------|-------|
| `openai` | gpt-4o-mini | $0.15 in / $0.60 out | ~95% | Best accuracy/cost ratio — recommended |
| `zai` | glm-4-plus | Free | ~81% | Zero cost, lower quality |
| `anthropic` | claude-sonnet-4 | $3.00 in / $15.00 out | ~85% | Highest quality, 20× cost |
| `openrouter` | configurable | varies | varies | 200+ models via single API |

**Agentic loop** uses the same `LLM_PROVIDER` — cheap calls with small context windows to decide which URLs to scrape next.

---

## Measured Results

### Per-Company Performance (OpenAI gpt-4o-mini)

| Company | Real Fill | High Fill | Pages Scraped | Tokens | Cost | Time |
|---------|-----------|-----------|---------------|--------|------|------|
| Securitize | 94.8% | 42.9% | 10 | 32,208 | $0.0079 | 89s |
| Ondo Finance | 79.3% | 24.3% | 4 | 33,010 | $0.0079 | 90s |
| Centrifuge | 76.4% | 36.9% | 42 | 32,603 | $0.0078 | 120s |
| **Average** | **83.5%** | **34.7%** | 19 | 32,607 | $0.0079 | 100s |

### Mode Comparison

| Mode | Time | Cost | Savings vs baseline |
|------|------|------|---------------------|
| Full extraction | ~100s | $0.008 | baseline |
| With cache hit | <1s | $0.000 | 99% time, 100% cost |
| Incremental update | ~17s | $0.001 | 79% time, 87% cost |

---

## Cost and Time Projections

| Companies | Sequential | 3 Workers | 5 Workers | Total Cost |
|-----------|-----------|-----------|-----------|------------|
| 1 | 100s | 100s | 100s | $0.008 |
| 10 | 17 min | 7 min | 5 min | $0.08 |
| 50 | 83 min | 33 min | 22 min | $0.40 |
| **200** | **5.6 hr** | **2.2 hr** | **1.3 hr** | **$1.58** |

---

## Data Schema (17 Tables, 303 Fields)

| # | Table | Type | Fields | Purpose |
|---|-------|------|--------|---------|
| 1 | companies | Single row | 20 | Identity, location, status |
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

---

## Project Structure

```
fiftyone_insight/
├── src/
│   ├── orchestrator.py              # Pipeline runner — multi-pass extraction
│   ├── schema/
│   │   └── models.py                # 17 Pydantic tables with CitedValue[T]
│   ├── search/
│   │   ├── client.py                # SearXNG client — deep_search, gap_search
│   │   └── agentic.py               # Agentic search loop — LLM-driven gap search
│   ├── scrape/
│   │   └── scraper.py               # Async httpx + Playwright scraper
│   ├── extractor/
│   │   └── llm.py                   # 6-batch LLM extraction + gap fill
│   ├── providers/
│   │   ├── base.py                  # BaseLLMProvider + LLMCallResult
│   │   ├── factory.py               # Provider selection (get_provider())
│   │   ├── zai_provider.py          # z.ai (free GLM models)
│   │   ├── openai_provider.py       # OpenAI (GPT-4o-mini)
│   │   ├── anthropic_provider.py    # Anthropic (Claude Sonnet 4)
│   │   ├── openrouter_provider.py   # OpenRouter (200+ models)
│   │   └── structured_outputs.py   # JSON mode schemas
│   ├── database/
│   │   └── saver.py                 # PostgreSQL persistence + cost tracking
│   ├── api/
│   │   └── server.py                # FastAPI — /run, /batch, /incremental, /download
│   ├── incremental.py               # Targeted field re-extraction
│   ├── cache.py                     # File-based LLM response cache
│   ├── rate_limit.py                # Rate limiting + exponential backoff
│   ├── calibration.py               # Confidence calibration
│   └── validation.py                # Per-field validation
├── frontend/                        # Next.js 15 web UI
│   └── src/components/
│       ├── SingleProcess.tsx        # Single company pipeline UI
│       ├── BatchProcess.tsx         # Batch processing UI
│       ├── CompanyDetails.tsx       # Company detail + XLSX download
│       ├── CompanyList.tsx          # Companies dashboard
│       └── DuplicateDialog.tsx      # Incremental vs scratch popup
├── database/
│   └── schema.sql                   # PostgreSQL schema (19 tables)
├── config/
│   └── searxng/settings.yml         # SearXNG configuration
├── output/                          # Pipeline results (JSON + Excel)
├── tests/                           # pytest suite
├── step_run.py                      # CLI entrypoint — single company
├── batch_run.py                     # CLI entrypoint — batch from CSV
├── docker-compose.yml               # Full stack (6 services)
├── Dockerfile                       # Pipeline + API container
├── .env.example                     # Environment template
└── requirements.txt                 # Python dependencies
```

---

## Known Limitations

1. **Scraping blocks**: Some sites reject automated requests — fewer pages scraped, lower fill rate
2. **LLM non-determinism**: Same company may get ±1–2% variance across runs
3. **Agentic loop exits early**: If the LLM judges existing context sufficient, it won't issue more queries even when fields are missing
4. **No job-ID tracking**: Pipeline status is tracked by domain (`GET /company/{domain}`), not by job ID

---

## License

Proprietary — 51 Insights project.
