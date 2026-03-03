from __future__ import annotations

import asyncio
from uuid import UUID

from app.models import CrawlJob


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[UUID, CrawlJob] = {}
        self._lock = asyncio.Lock()

    async def create(self, job: CrawlJob) -> None:
        async with self._lock:
            self._jobs[job.id] = job

    async def get(self, job_id: UUID) -> CrawlJob | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def update(self, job: CrawlJob) -> None:
        async with self._lock:
            self._jobs[job.id] = job


job_store = JobStore()
