"""Hacker News adapter — Tier-1 spec via the public Firebase API.

Endpoints:
  - https://hacker-news.firebaseio.com/v0/showstories.json   (Show HN)
  - https://hacker-news.firebaseio.com/v0/topstories.json    (front page)
  - https://hacker-news.firebaseio.com/v0/newstories.json
  - https://hacker-news.firebaseio.com/v0/item/{id}.json     (per-item details)

The list endpoints return an array of IDs (ordered). We then fetch the top-N
items in parallel. No auth, no rate limit at modest volume.

Each item gives us: title, url, by (author), score, descendants (comment count),
time (unix ts). For "Show HN: <X> – <Y>" we strip the prefix and capture the
tagline. The ranker gets enough signal without detail-page enrichment.
"""

from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timezone

import httpx

DOMAIN = "news.ycombinator.com"
VERTICAL = "products"
_API_BASE = "https://hacker-news.firebaseio.com/v0"

_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "ai-workflow-automator/1.0",
}

# Pre-built Tier-1 spec stored in site_specs alongside remoteok's
SPEC = {
    "tier": "api",
    "endpoint": _API_BASE,
    "fields": {
        "id": "id",
        "title": "title",
        "url": "url",
        "tagline": "tagline",
        "author": "author",
        "score": "score",
        "n_comments": "n_comments",
        "posted_at": "posted_at",
        "host": "host",
    },
}


async def fetch_items(
    *, listing: str = "showstories", max_results: int = 30
) -> list[dict]:
    """Fetch the top `max_results` items from `listing`.

    `listing` is one of: showstories, topstories, newstories, beststories,
    askstories, jobstories.
    """
    cap = int(os.getenv("HN_LIMIT", "0")) or max_results
    async with httpx.AsyncClient(timeout=30) as client:
        ids_resp = await client.get(
            f"{_API_BASE}/{listing}.json", headers=_HEADERS
        )
        ids_resp.raise_for_status()
        ids = ids_resp.json()
        if not isinstance(ids, list):
            return []
        # Fetch first `cap` items concurrently
        tasks = [_fetch_item(client, item_id) for item_id in ids[:cap]]
        raw_items = await asyncio.gather(*tasks, return_exceptions=True)

    items: list[dict] = []
    for raw in raw_items:
        if isinstance(raw, Exception) or not isinstance(raw, dict):
            continue
        norm = _normalize(raw)
        if norm:
            items.append(norm)
    return items


async def _fetch_item(client: httpx.AsyncClient, item_id: int) -> dict | None:
    try:
        r = await client.get(f"{_API_BASE}/item/{item_id}.json", headers=_HEADERS)
        if r.status_code != 200:
            return None
        return r.json()
    except (httpx.RequestError, ValueError):
        return None


_SHOWHN_RE = re.compile(r"^show\s+hn[:\s]+", re.IGNORECASE)


def _normalize(raw: dict) -> dict | None:
    if not raw.get("title"):
        return None
    title = raw["title"].strip()
    # Show HN posts often look like "Show HN: ToolName – tagline". Split the
    # tagline off so the ranker sees both the product name AND what it does.
    tagline = ""
    stripped = _SHOWHN_RE.sub("", title).strip()
    for sep in (" – ", " — ", " - "):
        if sep in stripped:
            name, _, rest = stripped.partition(sep)
            stripped, tagline = name.strip(), rest.strip()
            break

    url = raw.get("url") or f"https://news.ycombinator.com/item?id={raw['id']}"

    # Derive a host for quick filtering ("github.com", "arxiv.org", etc.)
    host = ""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.replace("www.", "")
    except Exception:
        pass

    posted_at = ""
    if raw.get("time"):
        try:
            posted_at = datetime.fromtimestamp(int(raw["time"]), tz=timezone.utc).date().isoformat()
        except (TypeError, ValueError):
            posted_at = ""

    return {
        "id": str(raw["id"]),
        "title": stripped,
        "tagline": tagline,
        # Description from tagline only — left empty otherwise so the runner's
        # enrichment pass fetches the real og:description from the linked URL
        # (typically a github repo or product page). The previous
        # "description = tagline or title" form fooled the enrichment trigger
        # into thinking the item was already enriched.
        "description": tagline,
        "url": url,
        "author": raw.get("by", ""),
        "score": raw.get("score", 0),
        "n_comments": raw.get("descendants", 0),
        "posted_at": posted_at,
        "host": host,
        "type": raw.get("type", ""),
    }
