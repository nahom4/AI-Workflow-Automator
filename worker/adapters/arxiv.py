"""arxiv adapter — Tier-1 spec via the public arXiv export API (Atom feed).

The HTML listing at arxiv.org/list/cs.AI/recent uses a `<dt>/<dd>` pair layout
that doesn't fit the vision_v2 card model (selector `+ dd .list-title` is not
something `querySelector` resolves from a `<dt>` element). The public export
API at https://export.arxiv.org/api/query returns Atom XML with rich
per-paper metadata, no auth, no rate-limit knock-out at modest volume.

Returned items include: title, url, summary (abstract), authors, published,
updated, primary_category, categories — the ranker gets real signal without
needing detail-page enrichment.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from xml.etree import ElementTree as ET

import httpx

DOMAIN = "arxiv.org"
VERTICAL = "research"
API_URL = "https://export.arxiv.org/api/query"

# Atom XML namespaces used by arXiv's feed
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

_HEADERS = {
    "Accept": "application/atom+xml",
    "User-Agent": "ai-workflow-automator/1.0 (https://github.com/example)",
}

# Pre-built Tier-1 spec stored in site_specs alongside remoteok's
SPEC = {
    "tier": "api",
    "endpoint": API_URL,
    "fields": {
        "id": "id",
        "title": "title",
        "url": "url",
        "summary": "summary",
        "authors": "authors",
        "published": "published",
        "primary_category": "primary_category",
        "categories": "categories",
    },
}


async def fetch_items(
    *, category: str = "cs.AI", max_results: int = 50
) -> list[dict]:
    """Fetch the most recent `max_results` papers from `category`.

    `category` is an arXiv subject classifier (cs.AI, cs.LG, cs.CL, stat.ML, etc.).
    No browser needed.
    """
    cap = int(os.getenv("ARXIV_LIMIT", "0")) or max_results
    params = {
        "search_query": f"cat:{category}",
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": str(cap),
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(API_URL, params=params, headers=_HEADERS)
        resp.raise_for_status()
        body = resp.text

    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []

    items: list[dict] = []
    for entry in root.findall("atom:entry", _NS):
        item = _parse_entry(entry)
        if item:
            items.append(item)
    return items


def _parse_entry(entry: ET.Element) -> dict | None:
    """Convert one <atom:entry> into a normalized dict."""
    raw_id = _text(entry, "atom:id")  # full URL like https://arxiv.org/abs/2605.12481v1
    if not raw_id:
        return None
    # Stable id without the version suffix
    paper_id = raw_id.rsplit("/", 1)[-1]
    paper_id = re.sub(r"v\d+$", "", paper_id)

    title = _text(entry, "atom:title")
    title = re.sub(r"\s+", " ", title or "").strip()

    summary = _text(entry, "atom:summary")
    summary = re.sub(r"\s+", " ", summary or "").strip()

    # Authors
    authors: list[str] = []
    for a in entry.findall("atom:author", _NS):
        name = _text(a, "atom:name")
        if name:
            authors.append(name.strip())

    # Categories
    categories: list[str] = []
    primary = None
    pc = entry.find("arxiv:primary_category", _NS)
    if pc is not None:
        primary = pc.get("term")
    for c in entry.findall("atom:category", _NS):
        term = c.get("term")
        if term and term not in categories:
            categories.append(term)

    # Link with rel="alternate" is the html abs page; others are pdf/etc.
    url = None
    for link in entry.findall("atom:link", _NS):
        if link.get("rel") in (None, "alternate") and link.get("type") in (None, "text/html"):
            url = link.get("href")
            break
    if not url:
        url = f"https://arxiv.org/abs/{paper_id}"

    published = _text(entry, "atom:published") or ""
    updated = _text(entry, "atom:updated") or ""

    return {
        "id": paper_id,
        "title": title,
        "url": url,
        "summary": summary,
        # alias so the ranker's generic "description" reads the abstract
        "description": summary,
        "authors": authors,
        "n_authors": len(authors),
        "primary_category": primary or "",
        "categories": categories,
        "published": _short_date(published),
        "updated": _short_date(updated),
    }


def _text(node: ET.Element, path: str) -> str:
    el = node.find(path, _NS)
    return (el.text or "") if el is not None else ""


def _short_date(iso: str) -> str:
    """Convert '2026-05-12T08:24:31Z' -> '2026-05-12'. Returns the input on failure."""
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).date().isoformat()
    except (TypeError, ValueError):
        return iso[:10] if len(iso) >= 10 else iso
