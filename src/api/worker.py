#!/usr/bin/env python
"""
ARQ worker startup script for the Tokenized Assets Pipeline.

Run with: python -m src.api.worker
"""

import os
import sys

from arq.connections import RedisSettings
from arq import Worker


# Import worker function
from .arq_worker import process_company


async def startup(ctx):
    """Worker startup callback."""
    print("ARQ worker starting up...")


async def shutdown(ctx):
    """Worker shutdown callback."""
    print("ARQ worker shutting down...")


if __name__ == '__main__':
    print("Starting ARQ worker...")

    # Create Redis settings
    redis_settings = RedisSettings(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", "6379")),
    )

    # Create and run worker
    worker = Worker(
        functions=[process_company],
        redis_settings=redis_settings,
        on_startup=startup,
        on_shutdown=shutdown,
        job_timeout=300,
        max_jobs=10,
    )

    try:
        worker.run()
    except KeyboardInterrupt:
        print("\nWorker stopped by user")
        sys.exit(0)
