"""
FastAPI server for the Tokenized Assets Pipeline.

Endpoints:
  POST /run          — Run pipeline for a single company
  POST /batch        — Run pipeline for multiple companies
  GET  /health       — Health check
  GET  /result/{id}  — Get stored result
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel as PydanticModel, Field

from ..orchestrator import PipelineRunner, PipelineResult, run_pipeline

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Tokenized Assets Pipeline",
    description="Data Gathering System for Tokenized Assets Companies — 30-second pipeline",
    version="1.0.0",
)

templates = Jinja2Templates(directory="src/api/templates")

# In-memory job store (use Redis in production)
_jobs: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class RunRequest(PydanticModel):
    company_name: str = Field(..., description="Company name, e.g. 'Chainlink'")
    domain: str = Field(..., description="Primary domain, e.g. 'chain.link'")
    timeout: int = Field(default=30, description="Pipeline timeout in seconds")


class BatchRequest(PydanticModel):
    companies: list[RunRequest] = Field(..., description="List of companies to process")
    max_concurrent: int = Field(default=3, description="Max concurrent pipeline runs")


class RunResponse(PydanticModel):
    job_id: str
    status: str
    message: str


class ResultResponse(PydanticModel):
    job_id: str
    status: str
    timing: dict = {}
    fill_rate: float = 0.0
    errors: list[str] = []
    data: dict = {}


class HealthResponse(PydanticModel):
    status: str
    searxng_url: str
    version: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="healthy",
        searxng_url=os.getenv("SEARXNG_URL", "http://searxng:8080"),
        version="1.0.0",
    )


@app.post("/run", response_model=RunResponse)
async def run_single(req: RunRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {"status": "running", "company": req.company_name}

    async def _run():
        try:
            searxng_url = os.getenv("SEARXNG_URL", "http://searxng:8080")
            result = await run_pipeline(
                company_name=req.company_name,
                domain=req.domain,
                searxng_url=searxng_url,
                timeout=req.timeout,
                output_dir="output",
            )
            _jobs[job_id] = {
                "status": "completed",
                "timing": result.timing,
                "fill_rate": result.fill_rate,
                "errors": result.errors,
                "data": result.company_data.model_dump(),
            }
        except Exception as e:
            _jobs[job_id] = {"status": "failed", "error": str(e)[:500]}

    background_tasks.add_task(_run)

    return RunResponse(
        job_id=job_id,
        status="started",
        message=f"Pipeline started for {req.company_name}",
    )


@app.post("/batch", response_model=list[RunResponse])
async def run_batch(req: BatchRequest, background_tasks: BackgroundTasks):
    responses = []
    for company in req.companies:
        resp = await run_single(company, background_tasks)
        responses.append(resp)
    return responses


@app.get("/result/{job_id}", response_model=ResultResponse)
async def get_result(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    return ResultResponse(
        job_id=job_id,
        status=job.get("status", "unknown"),
        timing=job.get("timing", {}),
        fill_rate=job.get("fill_rate", 0.0),
        errors=job.get("errors", []),
        data=job.get("data", {}),
    )
