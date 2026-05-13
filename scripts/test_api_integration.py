#!/usr/bin/env python
"""
Manual test script for API integration.

Run with: python scripts/test_api_integration.py
"""

import asyncio
import os
import sys
from datetime import datetime

import aiohttp


BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


async def test_health():
    """Test health endpoint."""
    print("Testing health endpoint...")
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/health") as resp:
            data = await resp.json()
            print(f"✓ Health: {data}")
            assert data["status"] == "healthy"


async def test_run_single():
    """Test running single company."""
    print("Testing single company run...")
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{BASE_URL}/run",
            json={
                "company_name": "test_integration",
                "domain": "example.com",
                "timeout": 30,
            }
        ) as resp:
            data = await resp.json()
            print(f"✓ Job queued: {data}")
            assert "job_id" in data
            return data["job_id"]


async def test_get_companies():
    """Test getting companies."""
    print("Testing get companies...")
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/companies") as resp:
            data = await resp.json()
            print(f"✓ Retrieved {len(data)} companies")
            return data


async def test_get_company(domain: str = "securitize.io"):
    """Test getting company details."""
    print(f"Testing get company {domain}...")
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/company/{domain}") as resp:
            if resp.status == 200:
                data = await resp.json()
                print(f"✓ Found company: {data.get('company_name')}")
                return data
            else:
                print(f"  Company not found (expected for test)")
                return None


async def test_batch():
    """Test batch processing."""
    print("Testing batch processing...")
    async with aiohttp.ClientSession() as session:
        companies = [
            {"company_name": "Batch Test 1", "domain": "batch1.test"},
            {"company_name": "Batch Test 2", "domain": "batch2.test"},
        ]
        async with session.post(
            f"{BASE_URL}/batch",
            json={"companies": companies, "max_concurrent": 2}
        ) as resp:
            data = await resp.json()
            print(f"✓ Batch queued: {len(data['jobs'])} jobs")
            return data["jobs"]


async def poll_job_result(job_id: str, max_wait: int = 30):
    """Poll job result until completion."""
    print(f"Polling job {job_id}...")
    async with aiohttp.ClientSession() as session:
        for i in range(max_wait):
            async with session.get(f"{BASE_URL}/result/{job_id}") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"  Status: {data['status']}")

                    if data["status"] in ["completed", "failed"]:
                        return data
                elif resp.status != 404:
                    print(f"  Error: {resp.status}")
                    return None

            await asyncio.sleep(1)

        print("  Timeout waiting for job completion")
        return None


async def main():
    """Run all tests."""
    print(f"Testing API at {BASE_URL}")
    print("=" * 50)

    try:
        await test_health()
        await test_get_companies()
        await test_get_company()

        job_id = await test_run_single()
        await test_batch()

        # Poll for result (optional, may timeout)
        # await poll_job_result(job_id, max_wait=5)

        print("=" * 50)
        print("✓ All basic tests passed")

    except Exception as e:
        print(f"✗ Test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
