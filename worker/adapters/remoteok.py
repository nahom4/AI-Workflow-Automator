"""
RemoteOK adapter — pre-built Tier-1 spec.
RemoteOK exposes a public JSON API at /api with no auth or browser required.
"""

from __future__ import annotations

import os
import httpx

DOMAIN = "remoteok.com"
VERTICAL = "jobs"
API_URL = "https://remoteok.com/api"

# Pre-built Tier-1 spec stored in site_specs for future scouted-site reference
SPEC = {
    "tier": "api",
    "endpoint": API_URL,
    "fields": {
        "id": "id",
        "title": "position",
        "url": "url",
        "company": "company",
        "salary_min": "salary_min",
        "salary_max": "salary_max",
        "tags": "tags",
        "date": "date",
    },
}

_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; AutomatorBot/1.0)",
}


async def fetch_items() -> list[dict]:
    """
    Fetch all current jobs from the RemoteOK public JSON API.
    Returns a list of normalized item dicts ready for the ranker.
    No browser tab needed — this is a plain HTTPS request.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(API_URL, headers=_HEADERS)
        resp.raise_for_status()
        data = resp.json()

    if not isinstance(data, list):
        return []

    limit = int(os.getenv("REMOTEOK_LIMIT", "0")) or None
    jobs = []
    for item in data:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("id")
        if not raw_id:
            continue
        jobs.append(_normalize(item))
        if limit and len(jobs) >= limit:
            break

    return jobs


def _normalize(item: dict) -> dict:
    return {
        "id": str(item["id"]),
        "title": item.get("position", ""),
        "url": item.get("url", ""),
        "company": item.get("company", ""),
        "tags": item.get("tags", []),
        "salary_min": item.get("salary_min"),
        "salary_max": item.get("salary_max"),
        "date": item.get("date", ""),
        "description": item.get("description", ""),
        "location": item.get("location", "Worldwide"),
        # keep original for raw_json storage
        **{k: v for k, v in item.items() if k not in ("id", "position", "url", "company")},
    }
