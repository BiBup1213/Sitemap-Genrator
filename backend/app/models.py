from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class CrawlStartRequest(BaseModel):
    site: str = Field(..., examples=["zollsoft.de"])
    max_pages: int = Field(default=300, ge=1, le=5000)
    respect_robots: bool = True
    include_query_params: bool = False


class CrawlStartResponse(BaseModel):
    job_id: UUID


class CrawlProgress(BaseModel):
    collected: int = 0
    queued: int = 0
    current_url: str | None = None


class UrlResult(BaseModel):
    url: str
    priority: float
    lastmod: str
    changefreq: Literal["weekly"] = "weekly"

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: float) -> float:
        return round(min(1.0, max(0.1, value)), 1)


class CrawlStatusResponse(BaseModel):
    job_id: UUID
    state: Literal["queued", "running", "done", "error"]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    progress: CrawlProgress = Field(default_factory=CrawlProgress)
    results: list[UrlResult] = Field(default_factory=list)
    error: str | None = None


class CrawlJob(BaseModel):
    id: UUID
    state: Literal["queued", "running", "done", "error"] = "queued"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    progress: CrawlProgress = Field(default_factory=CrawlProgress)
    results: list[UrlResult] = Field(default_factory=list)
    error: str | None = None
    sitemap_xml: bytes | None = None
