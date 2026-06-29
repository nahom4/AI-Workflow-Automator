"""We Work Remotely adapter — public RSS feed, no auth.

Feed URLs:
  All jobs:        https://weworkremotely.com/remote-jobs.rss
  Programming:     https://weworkremotely.com/categories/remote-programming-jobs.rss
  Design:          https://weworkremotely.com/categories/remote-design-jobs.rss
  DevOps:          https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss
  Data Science:    https://weworkremotely.com/categories/remote-data-science-jobs.rss
  Product:         https://weworkremotely.com/categories/remote-product-jobs.rss
"""

from __future__ import annotations

import hashlib
import re
from xml.etree import ElementTree as ET

import httpx

DOMAIN = "weworkremotely.com"
VERTICAL = "jobs"

_FEED_BASE = "https://weworkremotely.com"
_DEFAULT_FEED = f"{_FEED_BASE}/remote-jobs.rss"

_CATEGORY_FEEDS = {
    "programming": f"{_FEED_BASE}/categories/remote-programming-jobs.rss",
    "design": f"{_FEED_BASE}/categories/remote-design-jobs.rss",
    "devops": f"{_FEED_BASE}/categories/remote-devops-sysadmin-jobs.rss",
    "data": f"{_FEED_BASE}/categories/remote-data-science-jobs.rss",
    "product": f"{_FEED_BASE}/categories/remote-product-jobs.rss",
    "marketing": f"{_FEED_BASE}/categories/remote-marketing-jobs.rss",
}

SPEC = {"tier": "api", "endpoint": _DEFAULT_FEED, "fields": {
    "id": "id", "title": "title", "url": "url",
    "company": "company", "category": "category", "date": "date",
}}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AutomatorBot/1.0)",
    "Accept": "application/rss+xml, application/xml, text/xml",
}


async def fetch_items(*, category: str = "", max_results: int = 100) -> list[dict]:
    feed_url = _CATEGORY_FEEDS.get(category.lower(), _DEFAULT_FEED)
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(feed_url, headers=_HEADERS, follow_redirects=True)
        resp.raise_for_status()

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        return []

    items = []
    for item in root.findall(".//item")[:max_results]:
        norm = _normalize(item)
        if norm:
            items.append(norm)
    return items


def _normalize(item: ET.Element) -> dict | None:
    title_raw = _t(item, "title") or ""
    link = _t(item, "link") or ""
    guid = _t(item, "guid") or link
    if not title_raw:
        return None

    # WWR title format: "CompanyName: Job Title at Location"
    company, _, rest = title_raw.partition(": ")
    title = rest.strip() if rest else title_raw.strip()

    description = _strip_html(_t(item, "description") or "")
    category = _t(item, "region") or _t(item, "category") or ""
    date = _t(item, "pubDate") or ""

    return {
        "id": hashlib.md5(guid.encode()).hexdigest()[:16],
        "title": title,
        "url": link,
        "company": company.strip(),
        "description": description[:600],
        "category": category,
        "date": date,
        "location": "Remote",
    }


def _t(el: ET.Element, tag: str) -> str:
    child = el.find(tag)
    return (child.text or "").strip() if child is not None else ""


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html).strip()
