from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Response

from app.crawler import CrawlError, check_target_is_public, normalize_site_input, run_crawl_job
from app.models import CrawlJob, CrawlStartRequest, CrawlStartResponse, CrawlStatusResponse
from app.store import job_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crawl", tags=["crawl"])


@router.post("/start", response_model=CrawlStartResponse)
async def start_crawl(payload: CrawlStartRequest) -> CrawlStartResponse:
    try:
        host = normalize_site_input(payload.site)
        check_target_is_public(host)
    except CrawlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = CrawlJob(id=uuid4(), state="queued", started_at=datetime.now(tz=UTC))
    await job_store.create(job)
    asyncio.create_task(run_crawl_job(job, payload, concurrency=10))
    logger.info("Queued crawl job %s for site %s", job.id, payload.site)
    return CrawlStartResponse(job_id=job.id)


@router.get("/status/{job_id}", response_model=CrawlStatusResponse)
async def crawl_status(job_id: UUID) -> CrawlStatusResponse:
    job = await job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return CrawlStatusResponse(
        job_id=job.id,
        state=job.state,
        started_at=job.started_at,
        finished_at=job.finished_at,
        progress=job.progress,
        results=job.results,
        error=job.error,
    )


@router.get("/download/{job_id}")
async def download_sitemap(job_id: UUID) -> Response:
    job = await job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.state != "done" or job.sitemap_xml is None:
        raise HTTPException(status_code=400, detail="Sitemap is not ready yet")

    headers = {"Content-Disposition": 'attachment; filename="sitemap.xml"'}
    return Response(content=job.sitemap_xml, media_type="application/xml", headers=headers)
