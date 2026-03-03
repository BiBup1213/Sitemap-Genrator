from __future__ import annotations

from lxml import etree

from app.crawler import compute_priority, normalize_site_input, normalize_url
from app.robots import same_site_host
from app.sitemap import SITEMAP_NS, build_sitemap_xml
from app.models import UrlResult


def test_normalize_site_input_accepts_plain_domain() -> None:
    assert normalize_site_input("example.com") == "example.com"


def test_normalize_url_dedupes_fragment_and_trailing_slash() -> None:
    url = "https://Example.com/about/#team"
    assert normalize_url(url, include_query_params=False) == "https://example.com/about"


def test_normalize_url_keeps_or_removes_query_based_on_option() -> None:
    url = "https://example.com/search/?q=test#frag"
    assert normalize_url(url, include_query_params=False) == "https://example.com/search"
    assert normalize_url(url, include_query_params=True) == "https://example.com/search?q=test"


def test_compute_priority_depth_based() -> None:
    assert compute_priority("https://example.com/") == 1.0
    assert compute_priority("https://example.com/a/b") == 0.8
    assert compute_priority("https://example.com/a/b/c/d/e/f/g/h/i/j/k") == 0.1


def test_sitemap_output_is_well_formed_xml() -> None:
    xml_bytes = build_sitemap_xml(
        [
            UrlResult(
                url="https://example.com/",
                priority=1.0,
                lastmod="2026-03-03",
                changefreq="weekly",
            )
        ]
    )
    root = etree.fromstring(xml_bytes)
    assert root.tag == f"{{{SITEMAP_NS}}}urlset"
    loc = root.find(f"{{{SITEMAP_NS}}}url/{{{SITEMAP_NS}}}loc")
    assert loc is not None
    assert loc.text == "https://example.com/"


def test_same_site_host_allows_www_aliases_only_when_in_allowed_set() -> None:
    allowed = {"example.com", "www.example.com"}
    assert same_site_host("https://example.com/page", allowed)
    assert same_site_host("https://www.example.com/page", allowed)
    assert not same_site_host("https://blog.example.com/page", allowed)
