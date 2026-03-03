from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import ParseResult, urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from app.models import CrawlJob, CrawlStartRequest, UrlResult
from app.robots import build_robots_checker, resolve_www_aliases, same_site_host
from app.sitemap import build_sitemap_xml
from app.store import job_store

logger = logging.getLogger(__name__)

NON_HTML_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".pdf",
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
    ".css",
    ".js",
    ".mjs",
    ".ico",
    ".mp4",
    ".mp3",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".xml",
    ".json",
}

DISALLOWED_NETS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
]


class CrawlError(Exception):
    pass


def normalize_site_input(site: str) -> str:
    raw = site.strip()
    if not raw:
        raise CrawlError("Site is required.")
    if "//" not in raw:
        raw = f"https://{raw}"

    parsed = urlparse(raw)
    host = parsed.hostname
    if not host:
        raise CrawlError("Invalid domain or URL.")
    if host.lower() == "localhost":
        raise CrawlError("Localhost is not allowed.")

    return host.lower()


def check_target_is_public(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise CrawlError(f"Could not resolve target host: {host}") from exc

    for info in infos:
        ip_text = info[4][0]
        ip = ipaddress.ip_address(ip_text)
        if any(ip in net for net in DISALLOWED_NETS) or ip.is_loopback:
            raise CrawlError("Private or local network targets are not allowed.")


def normalize_url(url: str, include_query_params: bool) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"

    # Keep root path as "/" and remove trailing slash for others.
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    query = parsed.query if include_query_params else ""
    normalized = ParseResult(
        scheme=scheme,
        netloc=netloc,
        path=path,
        params="",
        query=query,
        fragment="",
    )
    return urlunparse(normalized)


def should_skip_non_html(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    return any(path.endswith(ext) for ext in NON_HTML_EXTENSIONS)


def compute_priority(url: str) -> float:
    path = urlparse(url).path
    if path in ("", "/"):
        return 1.0
    segments = [segment for segment in path.split("/") if segment]
    depth = len(segments)
    return round(max(0.1, 1.0 - depth * 0.1), 1)


def extract_links(html: str) -> Iterable[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("a", href=True):
        href = tag.get("href")
        if href:
            yield href


async def canonical_base_url(host: str) -> str:
    async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
        for scheme in ("https", "http"):
            candidate = f"{scheme}://{host}/"
            try:
                response = await client.get(candidate)
                if response.status_code < 500:
                    return normalize_url(str(response.url), include_query_params=False)
            except httpx.HTTPError:
                continue

    raise CrawlError(f"Target is not reachable over HTTP/HTTPS: {host}")


async def _fetch_with_retry(client: httpx.AsyncClient, url: str, retries: int = 2) -> httpx.Response | None:
    for attempt in range(retries + 1):
        try:
            return await client.get(url)
        except httpx.HTTPError as exc:
            if attempt == retries:
                logger.warning("Request failed for %s: %s", url, exc)
                return None
            await asyncio.sleep(0.2 * (attempt + 1))
    return None


async def run_crawl_job(job: CrawlJob, payload: CrawlStartRequest, concurrency: int = 10) -> None:
    job.state = "running"
    job.started_at = datetime.now(tz=UTC)
    await job_store.update(job)

    try:
        host = normalize_site_input(payload.site)
        check_target_is_public(host)
        base_url = await canonical_base_url(host)
        base_host = urlparse(base_url).hostname or host

        allowed_hosts = {h for h in resolve_www_aliases(base_host) if _host_resolves(h)}
        if base_host not in allowed_hosts:
            allowed_hosts.add(base_host)

        queue: asyncio.Queue[str] = asyncio.Queue()
        seen: set[str] = set()
        results: dict[str, UrlResult] = {}
        lock = asyncio.Lock()

        start_url = normalize_url(base_url, payload.include_query_params)
        seen.add(start_url)
        await queue.put(start_url)

        timeout = httpx.Timeout(10.0)
        headers = {"User-Agent": "SitemapWranglerBot/1.0"}

        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout, headers=headers) as client:
            robots_checker = await build_robots_checker(client, base_url) if payload.respect_robots else None

            async def worker() -> None:
                while True:
                    url = await queue.get()
                    try:
                        async with lock:
                            job.progress.current_url = url
                            job.progress.queued = queue.qsize()
                            await job_store.update(job)

                        async with lock:
                            if len(results) >= payload.max_pages:
                                continue

                        response = await _fetch_with_retry(client, url)
                        if response is None:
                            continue

                        final_url = normalize_url(str(response.url), payload.include_query_params)
                        if not same_site_host(final_url, allowed_hosts):
                            continue
                        if should_skip_non_html(final_url):
                            continue

                        content_type = response.headers.get("content-type", "").lower()
                        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                            logger.warning("Skipping non-HTML content type %s at %s", content_type, final_url)
                            continue

                        async with lock:
                            if final_url not in results and len(results) < payload.max_pages:
                                results[final_url] = UrlResult(
                                    url=final_url,
                                    priority=compute_priority(final_url),
                                    lastmod=date.today().isoformat(),
                                    changefreq="weekly",
                                )
                                job.progress.collected = len(results)
                                await job_store.update(job)

                        for href in extract_links(response.text):
                            next_url = urljoin(final_url, href)
                            parsed_next = urlparse(next_url)
                            if parsed_next.scheme not in {"http", "https"}:
                                continue

                            normalized_next = normalize_url(next_url, payload.include_query_params)
                            if should_skip_non_html(normalized_next):
                                continue
                            if not same_site_host(normalized_next, allowed_hosts):
                                continue
                            if robots_checker and not robots_checker.allowed(normalized_next):
                                logger.info("Blocked by robots.txt: %s", normalized_next)
                                continue

                            async with lock:
                                if len(results) >= payload.max_pages:
                                    break
                                if normalized_next in seen:
                                    continue
                                seen.add(normalized_next)
                                await queue.put(normalized_next)
                                job.progress.queued = queue.qsize()
                                await job_store.update(job)
                    finally:
                        queue.task_done()

            workers = [asyncio.create_task(worker()) for _ in range(max(1, concurrency))]
            await queue.join()
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

        job.results = sorted(results.values(), key=lambda r: r.url)
        job.sitemap_xml = build_sitemap_xml(job.results)
        job.state = "done"
        job.finished_at = datetime.now(tz=UTC)
        job.progress.current_url = None
        job.progress.queued = 0
        await job_store.update(job)
        logger.info("Crawl finished for job %s with %s URLs", job.id, len(job.results))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Crawl failed for job %s", job.id)
        job.state = "error"
        job.error = str(exc)
        job.finished_at = datetime.now(tz=UTC)
        job.progress.current_url = None
        await job_store.update(job)


def _host_resolves(hostname: str) -> bool:
    try:
        socket.getaddrinfo(hostname, None)
        return True
    except socket.gaierror:
        return False
