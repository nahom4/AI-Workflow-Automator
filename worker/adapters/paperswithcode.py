"""Papers adapter — uses HuggingFace daily_papers API.

Papers with Code was acquired by Hugging Face and its public API now 302-
redirects to https://huggingface.co/papers/trending. We use HF's daily papers
endpoint instead — same shape (id, title, abstract, date, github_url).

Endpoint: https://huggingface.co/api/daily_papers
"""

from __future__ import annotations

import os
import httpx

DOMAIN = "paperswithcode.com"
VERTICAL = "research"
API_URL = "https://huggingface.co/api/daily_papers"

SPEC = {"tier": "api", "endpoint": API_URL, "fields": {
    "id": "paper.id", "title": "title", "summary": "summary",
    "date": "publishedAt",
}}

_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "ai-workflow-automator/1.0",
}


async def fetch_items(*, max_results: int = 50) -> list[dict]:
    cap = int(os.getenv("PWC_LIMIT", "0")) or max_results
    params = {"limit": min(cap, 100)}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(API_URL, params=params, headers=_HEADERS)
        resp.raise_for_status()
        data = resp.json()

    if not isinstance(data, list):
        return []
    return [_normalize(p) for p in data if isinstance(p, dict) and p.get("paper")]


def _normalize(entry: dict) -> dict:
    paper = entry.get("paper") or {}
    arxiv_id = str(paper.get("id") or "")
    title = entry.get("title") or paper.get("title") or ""
    summary = entry.get("summary") or paper.get("summary") or ""
    github_url = paper.get("githubRepo") or ""
    return {
        "id": arxiv_id or title,
        "title": title,
        "url": f"https://huggingface.co/papers/{arxiv_id}" if arxiv_id else "",
        "description": summary[:1500],
        "date": (entry.get("publishedAt") or "")[:10],
        "arxiv_id": arxiv_id,
        "github_url": github_url,
        "stars": paper.get("githubStars", 0),
        "upvotes": paper.get("upvotes", 0),
        "tags": paper.get("ai_keywords") or [],
    }
