"""Papers with Code adapter — free public REST API, no auth.

Returns ML papers that have associated code/implementations.
Endpoint: https://paperswithcode.com/api/v1/papers/

Fields include: title, abstract, url, arxiv_id, github_url, stars, date.
"""

from __future__ import annotations

import os
import httpx

DOMAIN = "paperswithcode.com"
VERTICAL = "research"
API_URL = "https://paperswithcode.com/api/v1/papers/"

SPEC = {"tier": "api", "endpoint": API_URL, "fields": {
    "id": "id", "title": "title", "url": "url",
    "description": "abstract", "date": "published",
    "arxiv_id": "arxiv_id",
}}

_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "ai-workflow-automator/1.0",
}


async def fetch_items(*, max_results: int = 50) -> list[dict]:
    cap = int(os.getenv("PWC_LIMIT", "0")) or max_results
    params = {"ordering": "-published", "page_size": min(cap, 100)}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(API_URL, params=params, headers=_HEADERS)
        resp.raise_for_status()
        data = resp.json()

    results = data.get("results", []) if isinstance(data, dict) else []
    return [_normalize(p) for p in results if isinstance(p, dict) and p.get("id")]


def _normalize(paper: dict) -> dict:
    arxiv_id = paper.get("arxiv_id") or ""
    url = (
        paper.get("url_abs")
        or (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "")
        or f"https://paperswithcode.com/paper/{paper.get('id', '')}"
    )
    return {
        "id": str(paper["id"]),
        "title": paper.get("title", ""),
        "url": url,
        "description": paper.get("abstract", ""),
        "date": (paper.get("published") or "")[:10],
        "arxiv_id": arxiv_id,
        "github_url": paper.get("url_pdf", ""),
        "authors": paper.get("authors", []),
    }
