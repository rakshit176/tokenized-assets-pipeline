"""
ARQ worker functions for background pipeline processing.
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, Any

from arq import create_pool
from arq.connections import RedisSettings

from ..orchestrator import run_pipeline
from ..database.saver import DatabaseSaver


logger = logging.getLogger(__name__)


# =============================================================================
# ARQ Worker Functions
# =============================================================================

async def process_company(ctx: Dict[str, Any], company_name: str, domain: str, timeout: int = 180) -> Dict[str, Any]:
    """
    Process a single company through the pipeline.

    Args:
        ctx: ARQ context
        company_name: Name of the company
        domain: Company domain
        timeout: Pipeline timeout in seconds

    Returns:
        Result dictionary with status and data
    """
    import asyncpg

    job_id = ctx['job_id']
    logger.info(f"Starting pipeline job {job_id} for {company_name} ({domain})")

    # Get database connection
    db_url = (
        f"postgresql://{os.getenv('DB_USER', 'postgres')}:"
        f"{os.getenv('DB_PASSWORD', 'postgres')}@"
        f"{os.getenv('DB_HOST', 'localhost')}:"
        f"{os.getenv('DB_PORT', '5432')}/"
        f"{os.getenv('DB_NAME', 'fiftyone_insights')}"
    )

    conn = None
    run_id = None

    try:
        conn = await asyncpg.connect(db_url)

        # Create pipeline run record
        run_row = await conn.fetchrow(
            """
            INSERT INTO pipeline_runs (company_name, domain, llm_provider, llm_model, status)
            VALUES ($1, $2, $3, $4, 'running')
            RETURNING run_id
            """,
            company_name,
            domain,
            os.getenv("LLM_PROVIDER", "openai"),
            os.getenv("LLM_MODEL", "gpt-4o"),
        )
        run_id = run_row['run_id']
        logger.info(f"Created pipeline run {run_id} for job {job_id}")

        # Run the pipeline
        result = await run_pipeline(
            company_name=company_name,
            domain=domain,
            timeout=timeout,
            output_dir="output",
        )

        # Calculate duration
        duration_secs = sum(result.timing.values()) if result.timing else 0

        # Save company data to database
        saver = DatabaseSaver()
        company_id = await saver.save(
            company_name=company_name,
            domain=domain,
            data=result.company_data,
            llm_provider=os.getenv("LLM_PROVIDER", "openai"),
            llm_model=os.getenv("LLM_MODEL", "gpt-4o"),
            fill_rate=result.fill_rate if result.fill_rate else 0.0,
            pages_scraped=result.scraped_page_count if hasattr(result, 'scraped_page_count') else 0,
            duration_secs=duration_secs,
        )
        logger.info(f"Saved company data for {company_name} with company_id={company_id}")

        # Get cost from llm_call_logs
        cost_row = await conn.fetchrow(
            """
            SELECT COALESCE(SUM(cost_usd), 0) as total_cost
            FROM llm_call_logs
            WHERE run_id = $1
            """,
            run_id,
        )
        cost_usd = float(cost_row['total_cost']) if cost_row else 0

        # Update pipeline run with success
        await conn.execute(
            """
            UPDATE pipeline_runs
            SET status = 'completed',
                completed_at = NOW(),
                fill_rate = $1,
                duration_secs = $2,
                cost_usd = $3,
                pages_scraped = $4,
                search_results = $5,
                total_fields = $6,
                filled_fields = $7,
                company_id = $8
            WHERE run_id = $9
            """,
            result.fill_rate if result.fill_rate else None,  # Already a decimal (0.0-1.0)
            duration_secs,
            cost_usd,
            len(result.sources) if hasattr(result, 'sources') else 0,
            0,  # search_results - to be calculated
            303,  # total_fields
            int(303 * (result.fill_rate / 100)) if result.fill_rate else 0,  # filled_fields
            company_id,
            run_id,
        )

        logger.info(f"Completed pipeline job {job_id} for {company_name}")

        return {
            'job_id': job_id,
            'run_id': run_id,
            'company_name': company_name,
            'domain': domain,
            'status': 'completed',
            'fill_rate': result.fill_rate,
            'duration_secs': duration_secs,
            'cost_usd': cost_usd,
            'errors': result.errors,
        }

    except Exception as e:
        logger.error(f"Pipeline job {job_id} failed: {e}")

        # Update pipeline run with error
        if conn and run_id:
            try:
                await conn.execute(
                    """
                    UPDATE pipeline_runs
                    SET status = 'failed',
                        completed_at = NOW(),
                        error_message = $1
                    WHERE run_id = $2
                    """,
                    str(e),
                    run_id,
                )
            except Exception:
                pass

        return {
            'job_id': job_id,
            'run_id': run_id,
            'company_name': company_name,
            'domain': domain,
            'status': 'failed',
            'errors': str(e),
        }

    finally:
        if conn:
            await conn.close()


# =============================================================================
# Worker settings
# =============================================================================

async def startup(ctx: Dict[str, Any]):
    """Initialize worker on startup."""
    logger.info("ARQ worker starting up")


async def shutdown(ctx: Dict[str, Any]):
    """Clean up worker on shutdown."""
    logger.info("ARQ worker shutting down")


class WorkerSettings:
    """ARQ worker configuration."""

    redis_settings = RedisSettings(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        database=int(os.getenv("REDIS_DB", "0")),
    )

    on_startup = startup
    on_shutdown = shutdown

    functions = [process_company]

    # Job settings
    job_timeout = 300  # 5 minutes
    max_jobs = 10
    queue_read_limit = 10

    # Retry settings
    max_tries = 1
    retry_jobs = False
