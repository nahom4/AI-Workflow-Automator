"""dev.to adapter — free public API, no auth required.

Endpoints:
  Top articles:  GET /api/articles?top=7&per_page=N
  By tag:        GET /api/articles?tag=python&per_page=N
  Latest:        GET /api/articles?per_page=N
"""

from __future__ import annotations

import os
import httpx

DOMAIN = "dev.to"
VERTICAL = "content"
API_URL = "https://dev.to/api/articles"

SPEC = {"tier": "api", "endpoint": API_URL, "fields": {
    "id": "id", "title": "title", "url": "url",
    "description": "description", "tags": "tag_list",
    "reactions": "public_reactions_count", "author": "user",
}}

_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "ai-workflow-automator/1.0",
}


async def fetch_items(*, tag: str = "", top_days: int = 7, max_results: int = 60) -> list[dict]:
    cap = int(os.getenv("DEVTO_LIMIT", "0")) or max_results
    params: dict = {"per_page": min(cap, 100)}
    if tag:
        params["tag"] = tag
    else:
        params["top"] = top_days

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(API_URL, params=params, headers=_HEADERS)
        resp.raise_for_status()
        data = resp.json()

    if not isinstance(data, list):
        return []
    return [_normalize(a) for a in data if isinstance(a, dict) and a.get("id")]


def _normalize(item: dict) -> dict:
    user = item.get("user", {})
    return {
        "id": str(item["id"]),
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "description": item.get("description", ""),
        "tags": item.get("tag_list", []),
        "reactions": item.get("public_reactions_count", 0),
        "comments": item.get("comments_count", 0),
        "author": user.get("name", "") if isinstance(user, dict) else "",
        "date": (item.get("published_at") or "")[:10],
        "reading_time": item.get("reading_time_minutes", 0),
    }
