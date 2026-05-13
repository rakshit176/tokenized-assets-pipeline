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

import logging
import os
from typing import Optional

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .arq_worker import process_company
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
    redis_status = "disconnected"
    db_status = "connected"

    try:
        redis = await create_pool(RedisSettings(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
        ))
        redis_status = "connected"
        await redis.close()
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        redis_status = "disconnected"

    return HealthResponse(
        status="healthy",
        version="2.0.0",
        redis=redis_status,
        database=db_status,
    )


@app.post("/run", response_model=RunResponse)
async def run_single(req: RunRequest, background_tasks: BackgroundTasks):
    """
    Run pipeline for a single company.

    The job is processed asynchronously by ARQ workers.
    Returns immediately with a job_id for polling.
    """
    try:
        redis = await create_pool(RedisSettings(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
        ))

        job = await redis.enqueue_job(
            'process_company',
            company_name=req.company_name,
            domain=req.domain,
            timeout=req.timeout,
        )

        await redis.close()

        return RunResponse(
            job_id=job.job_id,
            company_name=req.company_name,
            domain=req.domain,
            status="queued",
        )

    except Exception as e:
        logger.error(f"Failed to enqueue job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/batch", response_model=BatchResponse)
async def run_batch(req: BatchRequest, background_tasks: BackgroundTasks):
    """
    Run pipeline for multiple companies.

    Jobs are processed asynchronously by ARQ workers.
    Returns immediately with job_ids for polling.
    """
    try:
        redis = await create_pool(RedisSettings(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
        ))

        jobs = []
        for company in req.companies:
            job = await redis.enqueue_job(
                'process_company',
                company_name=company.company_name,
                domain=company.domain,
                timeout=company.timeout,
            )
            jobs.append(RunResponse(
                job_id=job.job_id,
                company_name=company.company_name,
                domain=company.domain,
                status="queued",
            ))

        await redis.close()

        return BatchResponse(jobs=jobs)

    except Exception as e:
        logger.error(f"Failed to enqueue batch jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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


@app.get("/result/{job_id}", response_model=ResultResponse)
async def get_result(job_id: str):
    """
    Get the status and result of a pipeline job by job_id.

    Poll this endpoint to check job progress.
    Returns status: queued, running, completed, or failed.
    """
    try:
        redis = await create_pool(RedisSettings(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
        ))

        # Check job status by looking at ARQ Redis keys
        result_key = f"arq:result:{job_id}"
        in_progress_key = f"arq:in-progress:{job_id}"
        retry_key = f"arq:retry:{job_id}"

        # Check all keys before closing connection
        in_progress = await redis.exists(in_progress_key)
        result_data = await redis.get(result_key)
        has_retry = await redis.exists(retry_key)

        await redis.close()

        if in_progress:
            return ResultResponse(
                job_id=job_id,
                status="running",
            )

        if result_data:
            import pickle
            result = pickle.loads(result_data)
            # ARQ stores function results directly
            status = result.get('status', 'unknown')
            raw_errors = result.get('errors', [])

            # Normalize errors to list
            if isinstance(raw_errors, str):
                errors = [raw_errors] if raw_errors else []
            else:
                errors = raw_errors if isinstance(raw_errors, list) else []

            # Simple logic: completed + no errors = success, everything else = failed
            if status == 'completed' and not errors:
                return ResultResponse(
                    job_id=job_id,
                    status="completed",
                    fill_rate=result.get('fill_rate'),
                    total_cost_usd=result.get('cost_usd'),
                    errors=[],
                    data=result,
                )
            else:
                return ResultResponse(
                    job_id=job_id,
                    status="failed",
                    fill_rate=result.get('fill_rate'),
                    total_cost_usd=result.get('cost_usd'),
                    errors=errors if errors else ['Unknown error'],
                    data=result,
                )

        # Job might be queued or not exist
        if has_retry:
            return ResultResponse(
                job_id=job_id,
                status="queued",
            )

        raise HTTPException(status_code=404, detail="Job not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job result {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
