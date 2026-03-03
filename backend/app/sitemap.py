from __future__ import annotations

from lxml import etree

from app.models import UrlResult

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def build_sitemap_xml(urls: list[UrlResult]) -> bytes:
    nsmap = {None: SITEMAP_NS}
    root = etree.Element("urlset", nsmap=nsmap)

    for item in urls:
        url_el = etree.SubElement(root, "url")
        etree.SubElement(url_el, "loc").text = item.url
        etree.SubElement(url_el, "lastmod").text = item.lastmod
        etree.SubElement(url_el, "changefreq").text = item.changefreq
        etree.SubElement(url_el, "priority").text = f"{item.priority:.1f}"

    return etree.tostring(
        root,
        pretty_print=True,
        xml_declaration=True,
        encoding="UTF-8",
    )
