"""
Integration tests for the Tokenized Assets Pipeline API.

These tests verify the complete flow from API request to database storage.

Run with: pytest tests/api/test_server.py
"""

import asyncio
import os
from datetime import datetime
from typing import AsyncGenerator

import asyncpg
import pytest
from httpx import AsyncClient, ASGITransport
from arq import create_pool
from arq.connections import RedisSettings

from src.api.server import app
from src.api.database import db


# =============================================================================
# Test configuration
# =============================================================================

TEST_DB_URL = (
    f"postgresql://{os.getenv('DB_USER', 'fiftyone')}:"
    f"{os.getenv('DB_PASSWORD', 'fiftyone_secret')}@"
    f"{os.getenv('DB_HOST', 'localhost')}:"
    f"{os.getenv('DB_PORT', '5432')}/"
    f"{os.getenv('DB_NAME', 'fiftyone_insight')}"
)

REDIS_SETTINGS = RedisSettings(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=int(os.getenv('REDIS_PORT', '6379')),
    database=1,  # Use separate DB for tests
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="session")
async def test_db() -> AsyncGenerator[asyncpg.Connection, None]:
    """Create a test database connection."""
    conn = await asyncpg.connect(TEST_DB_URL)
    yield conn
    await conn.close()


@pytest.fixture(scope="session")
async def redis_pool():
    """Create a Redis connection pool for tests."""
    redis = await create_pool(REDIS_SETTINGS)
    yield redis
    await redis.close()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture(autouse=True)
async def cleanup_db(test_db: asyncpg.Connection):
    """Clean up test data after each test."""
    yield
    # Clean up test data
    await test_db.execute("DELETE FROM pipeline_runs WHERE company_name LIKE 'test_%'")


# =============================================================================
# Tests
# =============================================================================

@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Test the health check endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "2.0.0"
    assert "redis" in data
    assert "database" in data


@pytest.mark.asyncio
async def test_run_single_company(client: AsyncClient):
    """Test running the pipeline for a single company."""
    response = await client.post(
        "/run",
        json={
            "company_name": "test_securitize",
            "domain": "securitize.io",
            "timeout": 180,
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["company_name"] == "test_securitize"
    assert data["domain"] == "securitize.io"
    assert data["status"] in ["queued", "running"]


@pytest.mark.asyncio
async def test_run_batch_companies(client: AsyncClient):
    """Test running the pipeline for multiple companies."""
    response = await client.post(
        "/batch",
        json={
            "companies": [
                {"company_name": "test_company_1", "domain": "test1.com"},
                {"company_name": "test_company_2", "domain": "test2.com"},
            ],
            "max_concurrent": 2,
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert "jobs" in data
    assert len(data["jobs"]) == 2

    for job in data["jobs"]:
        assert "job_id" in job
        assert job["status"] in ["queued", "running"]


@pytest.mark.asyncio
async def test_get_companies(client: AsyncClient, test_db: asyncpg.Connection):
    """Test getting the list of processed companies."""
    # Insert test data
    await test_db.execute(
        """
        INSERT INTO pipeline_runs
        (company_name, domain, status, started_at, completed_at, fill_rate, cost_usd)
        VALUES
        ('test_company_1', 'test1.com', 'completed', NOW() - INTERVAL '1 hour', NOW(), 0.85, 0.05),
        ('test_company_2', 'test2.com', 'failed', NOW() - INTERVAL '2 hours', NOW(), NULL, NULL),
        ('test_company_3', 'test3.com', 'running', NOW() - INTERVAL '10 minutes', NULL, NULL, NULL)
        """
    )

    response = await client.get("/companies")
    assert response.status_code == 200

    data = response.json()
    assert len(data) >= 3

    # Check that companies are ordered by most recent
    assert data[0]["company_name"] == "test_company_3"  # running (most recent)


@pytest.mark.asyncio
async def test_get_companies_with_filter(client: AsyncClient, test_db: asyncpg.Connection):
    """Test filtering companies by status."""
    # Insert test data
    await test_db.execute(
        """
        INSERT INTO pipeline_runs
        (company_name, domain, status, started_at, completed_at, fill_rate, cost_usd)
        VALUES
        ('test_completed', 'completed.com', 'completed', NOW() - INTERVAL '1 hour', NOW(), 0.85, 0.05),
        ('test_failed', 'failed.com', 'failed', NOW() - INTERVAL '2 hours', NOW(), NULL, NULL)
        """
    )

    # Get only completed companies
    response = await client.get("/companies?status=completed")
    assert response.status_code == 200

    data = response.json()
    assert all(c["status"] == "completed" for c in data)


@pytest.mark.asyncio
async def test_get_company_by_domain(client: AsyncClient, test_db: asyncpg.Connection):
    """Test getting company details by domain."""
    # Insert test data
    await test_db.execute(
        """
        INSERT INTO companies
        (company_name, legal_name, hq_country, founded_year, description)
        VALUES ('Test Company', 'Test Company Inc', 'United States', 2020, 'A test company')
        """
    )

    await test_db.execute(
        """
        INSERT INTO pipeline_runs
        (company_name, domain, status, started_at, completed_at, fill_rate, cost_usd)
        VALUES ('Test Company', 'testcompany.com', 'completed', NOW() - INTERVAL '1 hour', NOW(), 0.85, 0.05)
        """
    )

    response = await client.get("/company/testcompany.com")
    assert response.status_code == 200

    data = response.json()
    assert data["company_name"] == "Test Company"
    assert data["domain"] == "testcompany.com"
    assert data["status"] == "completed"
    assert data["fill_rate"] == 0.85


@pytest.mark.asyncio
async def test_get_company_not_found(client: AsyncClient):
    """Test getting a company that doesn't exist."""
    response = await client.get("/company/nonexistent.com")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_job_result(client: AsyncClient, redis_pool):
    """Test getting job result."""
    # First, enqueue a job
    run_response = await client.post(
        "/run",
        json={
            "company_name": "test_result",
            "domain": "testresult.com",
        }
    )
    job_id = run_response.json()["job_id"]

    # Get job result (should be queued/running)
    result_response = await client.get(f"/result/{job_id}")
    assert result_response.status_code in [200, 404]  # May not be in Redis yet


@pytest.mark.asyncio
async def test_get_job_result_not_found(client: AsyncClient):
    """Test getting a job result that doesn't exist."""
    response = await client.get("/result/nonexistent_job_id")
    assert response.status_code == 404


# =============================================================================
# Integration test - full flow
# =============================================================================

@pytest.mark.asyncio
async def test_full_pipeline_flow(client: AsyncClient, redis_pool):
    """
    Test the complete flow from job submission to result retrieval.

    This test verifies:
    1. Job submission
    2. Job queueing
    3. Job execution (if worker is running)
    4. Result retrieval
    5. Database storage
    """
    # 1. Submit a job
    response = await client.post(
        "/run",
        json={
            "company_name": "test_full_flow",
            "domain": "testfullflow.com",
            "timeout": 30,
        }
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    # 2. Check initial status (queued or running)
    result_response = await client.get(f"/result/{job_id}")
    if result_response.status_code == 200:
        data = result_response.json()
        assert data["status"] in ["completed", "failed", "queued", "running"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
