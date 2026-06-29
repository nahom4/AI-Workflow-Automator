"""GitHub Trending adapter — GitHub Search API, 60 req/hr unauthenticated.

Fetches repositories created in the last N days sorted by stars, which
approximates the official trending page without requiring scraping.

Set GITHUB_TOKEN env var for 5000 req/hr if needed.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import httpx

DOMAIN = "github.com"
VERTICAL = "products"
API_URL = "https://api.github.com/search/repositories"

SPEC = {"tier": "api", "endpoint": API_URL, "fields": {
    "id": "id", "title": "full_name", "url": "html_url",
    "description": "description", "stars": "stargazers_count",
    "language": "language", "topics": "topics",
}}

_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "ai-workflow-automator/1.0",
}


async def fetch_items(*, language: str = "", days: int = 7, max_results: int = 50) -> list[dict]:
    cap = int(os.getenv("GITHUB_TRENDING_LIMIT", "0")) or max_results
    since = (date.today() - timedelta(days=days)).isoformat()

    query = f"created:>{since}"
    if language:
        query += f" language:{language}"

    params = {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": min(cap, 100),
    }

    headers = dict(_HEADERS)
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(API_URL, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    items = data.get("items", []) if isinstance(data, dict) else []
    return [_normalize(r) for r in items if isinstance(r, dict) and r.get("id")]


def _normalize(repo: dict) -> dict:
    owner = repo.get("owner", {})
    return {
        "id": str(repo["id"]),
        "title": repo.get("full_name", ""),
        "url": repo.get("html_url", ""),
        "description": repo.get("description") or "",
        "stars": repo.get("stargazers_count", 0),
        "forks": repo.get("forks_count", 0),
        "language": repo.get("language") or "",
        "topics": repo.get("topics", []),
        "author": owner.get("login", "") if isinstance(owner, dict) else "",
        "date": (repo.get("created_at") or "")[:10],
        "license": (repo.get("license") or {}).get("spdx_id", ""),
    }
