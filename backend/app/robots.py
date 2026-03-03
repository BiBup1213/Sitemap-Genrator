from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

logger = logging.getLogger(__name__)


@dataclass
class RobotsChecker:
    parser: RobotFileParser | None

    def allowed(self, url: str, user_agent: str = "*") -> bool:
        if self.parser is None:
            return True
        return self.parser.can_fetch(user_agent, url)


async def build_robots_checker(client: httpx.AsyncClient, base_url: str) -> RobotsChecker:
    robots_url = urljoin(base_url, "/robots.txt")
    try:
        response = await client.get(robots_url)
        if response.status_code >= 400:
            logger.warning("robots.txt returned %s for %s", response.status_code, robots_url)
            return RobotsChecker(parser=None)

        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())
        return RobotsChecker(parser=parser)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to fetch robots.txt (%s): %s", robots_url, exc)
        return RobotsChecker(parser=None)


def resolve_www_aliases(hostname: str) -> set[str]:
    hostname = hostname.lower()
    aliases = {hostname}
    if hostname.startswith("www."):
        aliases.add(hostname[4:])
    else:
        aliases.add(f"www.{hostname}")
    return aliases


def same_site_host(url: str, allowed_hosts: set[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in allowed_hosts
