"""Remotive adapter — free public JSON API, no auth required.

Endpoint: https://remotive.com/api/remote-jobs
Optional params: category, search, limit
Categories: software-dev, devops-sysadmin, design, marketing, etc.
"""

from __future__ import annotations

import os
import httpx

DOMAIN = "remotive.com"
VERTICAL = "jobs"
API_URL = "https://remotive.com/api/remote-jobs"

SPEC = {
    "tier": "api",
    "endpoint": API_URL,
    "fields": {
        "id": "id", "title": "title", "url": "url",
        "company": "company_name", "category": "category",
        "job_type": "job_type", "salary": "salary", "tags": "tags",
        "date": "publication_date",
    },
}

_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "ai-workflow-automator/1.0",
}


async def fetch_items(*, category: str = "", max_results: int = 100) -> list[dict]:
    cap = int(os.getenv("REMOTIVE_LIMIT", "0")) or max_results
    params: dict = {"limit": cap}
    if category:
        params["category"] = category
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(API_URL, params=params, headers=_HEADERS)
        resp.raise_for_status()
        data = resp.json()

    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    return [_normalize(j) for j in jobs if isinstance(j, dict) and j.get("id")]


def _normalize(item: dict) -> dict:
    return {
        "id": str(item["id"]),
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "company": item.get("company_name", ""),
        "description": _strip_html(item.get("description", "")),
        "category": item.get("category", ""),
        "job_type": item.get("job_type", ""),
        "salary": item.get("salary", ""),
        "tags": item.get("tags", []),
        "date": item.get("publication_date", ""),
        "location": item.get("candidate_required_location", "Worldwide"),
    }


def _strip_html(html: str) -> str:
    import re
    return re.sub(r"<[^>]+>", " ", html).strip()[:800]
