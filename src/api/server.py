"""
FastAPI server for the Tokenized Assets Pipeline with ARQ integration.

Endpoints:
  POST /run              — Run pipeline for a single company (async)
  POST /batch            — Run pipeline for multiple companies (async)
  GET  /companies        — Get all processed companies
  GET  /company/{domain}  — Get company details by domain
  GET  /result/{job_id}   — Get job status/result
  GET  /health            — Health check
"""

from __future__ import annotations

import asyncio
import logging
import os
import pathlib
import uuid
from typing import Optional

from dotenv import load_dotenv
load_dotenv(pathlib.Path(__file__).resolve().parents[2] / ".env")

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .database import db, CompanyBase, CompanyDetail


logger = logging.getLogger(__name__)


# =============================================================================
# FastAPI App
# =============================================================================

app = FastAPI(
    title="Tokenized Assets Pipeline API",
    description="Data Gathering System for Tokenized Assets Companies",
    version="2.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Request / Response schemas
# =============================================================================

class RunRequest(BaseModel):
    company_name: str = Field(..., description="Company name, e.g. 'Securitize'")
    domain: str = Field(..., description="Primary domain, e.g. 'securitize.io'")
    timeout: int = Field(default=180, description="Pipeline timeout in seconds")


class BatchRequest(BaseModel):
    companies: list[RunRequest] = Field(..., description="List of companies to process")
    max_concurrent: int = Field(default=3, description="Max concurrent pipeline runs")


class RunResponse(BaseModel):
    job_id: str
    company_name: str
    domain: str
    status: str


class BatchResponse(BaseModel):
    jobs: list[RunResponse]


class ResultResponse(BaseModel):
    job_id: str
    status: str
    fill_rate: Optional[float] = None
    total_cost_usd: Optional[float] = None
    errors: list[str] = []
    data: dict = {}


class HealthResponse(BaseModel):
    status: str
    version: str
    redis: str
    database: str


# =============================================================================
# Startup / Shutdown
# =============================================================================

@app.on_event("startup")
async def startup():
    """Initialize connections on startup."""
    await db.connect()
    logger.info("Database connected")


@app.on_event("shutdown")
async def shutdown():
    """Close connections on shutdown."""
    await db.close()
    logger.info("Database connection closed")


# =============================================================================
# Endpoints
# =============================================================================

@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    db_status = "connected" if db.pool else "disconnected"
    return HealthResponse(
        status="healthy",
        version="2.0.0",
        redis="n/a",
        database=db_status,
    )


async def _run_and_save(job_id: str, company_name: str, domain: str):
    """Run pipeline for one company and save result to DB. Used by both /run and /batch."""
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from step_run import run_company
    try:
        await run_company(company_name, domain)
    except Exception as e:
        logger.error("Pipeline failed for %s (%s): %s", company_name, domain, e)


@app.post("/run", response_model=RunResponse)
async def run_single(req: RunRequest, background_tasks: BackgroundTasks):
    """Run pipeline for a single company. Returns immediately; pipeline runs in background."""
    job_id = str(uuid.uuid4())
    background_tasks.add_task(_run_and_save, job_id, req.company_name, req.domain)
    return RunResponse(
        job_id=job_id,
        company_name=req.company_name,
        domain=req.domain,
        status="running",
    )


@app.post("/batch", response_model=BatchResponse)
async def run_batch(req: BatchRequest, background_tasks: BackgroundTasks):
    """Run pipeline for multiple companies.

    Uses max_concurrent workers (like batch_run.py):
    - max_concurrent=1 → sequential
    - max_concurrent>1 → parallel asyncio.gather in batches
    Returns immediately; all jobs run in background.
    """
    from step_run import run_company

    async def _run_batch_async():
        companies = [(c.company_name, c.domain) for c in req.companies]
        if req.max_concurrent <= 1:
            for name, domain in companies:
                try:
                    await run_company(name, domain)
                except Exception as e:
                    logger.error("Batch pipeline failed for %s: %s", name, e)
        else:
            # Process in parallel chunks of max_concurrent
            for i in range(0, len(companies), req.max_concurrent):
                chunk = companies[i:i + req.max_concurrent]
                await asyncio.gather(
                    *[run_company(name, domain) for name, domain in chunk],
                    return_exceptions=True,
                )

    jobs = []
    for company in req.companies:
        job_id = str(uuid.uuid4())
        jobs.append(RunResponse(
            job_id=job_id,
            company_name=company.company_name,
            domain=company.domain,
            status="running",
        ))

    background_tasks.add_task(_run_batch_async)
    return BatchResponse(jobs=jobs)


@app.get("/companies", response_model=list[CompanyBase])
async def get_companies(
    limit: int = 100,
    offset: int = 0,
    status: Optional[str] = None,
):
    """
    Get all processed companies from the database.

    Results are ordered by most recently processed.
    """
    try:
        companies = await db.get_companies(limit=limit, offset=offset, status=status)
        return companies

    except Exception as e:
        logger.error(f"Failed to get companies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/company/{domain}", response_model=CompanyDetail)
async def get_company(domain: str):
    """
    Get detailed information about a company by domain.

    Includes extracted fields, sources, and pipeline metadata.
    """
    try:
        company = await db.get_company_by_domain(domain)

        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        return company

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get company {domain}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/incremental", response_model=RunResponse)
async def run_incremental(req: RunRequest, background_tasks: BackgroundTasks):
    """Incremental update for an existing company — only re-extracts low-confidence fields."""
    job_id = str(uuid.uuid4())

    async def _run_incremental():
        import sys
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
        from src.incremental import targeted_update
        try:
            await targeted_update(req.company_name, req.domain)
        except Exception as e:
            logger.error("Incremental update failed for %s: %s", req.domain, e)

    background_tasks.add_task(_run_incremental)
    return RunResponse(job_id=job_id, company_name=req.company_name, domain=req.domain, status="running")


@app.get("/download/{domain}")
async def download_xlsx(domain: str):
    """Download the Excel report for a company by domain (e.g. ondo.finance)."""
    safe_name = domain.replace(".", "_")
    output_dir = pathlib.Path(__file__).resolve().parents[2] / "output"
    xlsx_path = output_dir / f"{safe_name}.xlsx"
    if not xlsx_path.exists():
        raise HTTPException(status_code=404, detail=f"Report not found for {domain}. Run the pipeline first.")
    return FileResponse(
        path=str(xlsx_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{safe_name}_report.xlsx",
    )


@app.get("/result/{job_id}", response_model=ResultResponse)
async def get_result(job_id: str):
    """Get pipeline result by looking up the company in DB by job_id is not tracked —
    use GET /companies or GET /company/{domain} to check results."""
    raise HTTPException(status_code=410, detail="Use GET /company/{domain} to check results")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
