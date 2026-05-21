"""
Tier 1 scout: capture XHR/fetch responses during page load using pydoll's
HAR recorder (tab.request.record), then ask Groq which endpoint carries the
listing data for a given vertical.

Returns a spec dict:
{
  "endpoint": "https://remoteok.com/api",
  "item_path": "jobs",       # dot-path to the items array in the JSON
  "fields": {                # field name -> dot-path in each item
    "title": "position",
    "url": "url",
    "id": "id"
  }
}
"""

from __future__ import annotations

import base64
import json

from worker.ai.groq_client import chat, strip_code_fences
from worker.browser import navigate, settle, wait_for_content

_SYSTEM = """\
You are a web API analyst. Given a list of XHR/fetch response shapes observed
during a page load, identify which endpoint returns a listing of items for the
given vertical (jobs / products / scholarships / other).

Respond with valid JSON only:
{
  "endpoint": "<url of the data endpoint>",
  "item_path": "<dot-path to items array, e.g. 'data.jobs' or '' for root array>",
  "fields": {
    "title": "<dot-path>",
    "url":   "<dot-path>",
    "id":    "<dot-path>"
  }
}
If no suitable endpoint was found respond: {"found": false}
"""

# Minimum response body size to consider — filters out tiny status pings
_MIN_BODY_BYTES = 1024

# Maximum responses to send to the LLM (token budget)
_MAX_CANDIDATES = 10


async def scout(tab, *, url: str, vertical: str) -> dict | None:
    """
    Navigate to `url` while recording network traffic, collect JSON responses,
    ask Groq which one contains the listing. Returns a Tier-1 spec or None.
    """
    from pydoll.protocol.network.types import ResourceType

    async with tab.request.record(
        resource_types=[ResourceType.XHR, ResourceType.FETCH]
    ) as capture:
        await navigate(tab, url)
        # Wait for the page to actually finish hydrating, not a fixed timer.
        # Some sites (IMDb, Product Hunt, large SPAs) keep adding DOM for 10+s.
        await wait_for_content(tab, max_wait=20.0)

    captured = _extract_json_responses(capture.entries)
    if not captured:
        return None

    prompt = (
        f"Vertical: {vertical}\n"
        f"Page URL: {url}\n\n"
        f"Captured XHR/fetch responses (up to {_MAX_CANDIDATES} with JSON bodies):\n"
        + json.dumps(captured[:_MAX_CANDIDATES], ensure_ascii=False)
    )
    try:
        raw = await chat(prompt, system=_SYSTEM)
    except Exception:
        # LLM unreachable / rate-limited / auth — caller logs, runner skips.
        return None
    try:
        result = json.loads(strip_code_fences(raw))
    except (json.JSONDecodeError, TypeError):
        return None

    if result.get("found") is False:
        return None
    if not result.get("endpoint") or not result.get("fields"):
        return None
    return result


def _extract_json_responses(entries: list[dict]) -> list[dict]:
    """
    From HAR entries, keep only those with JSON-parseable bodies large enough
    to be data. Returns compact summaries suitable for LLM analysis.
    """
    out: list[dict] = []
    for entry in entries:
        try:
            response = entry.get("response") or {}
            request = entry.get("request") or {}
            content = response.get("content") or {}
            body: str = content.get("text") or ""
            if not body:
                continue

            # HAR may base64-encode binary bodies. Decode if so.
            if content.get("encoding") == "base64":
                try:
                    body = base64.b64decode(body).decode("utf-8", errors="replace")
                except Exception:
                    continue

            if len(body) < _MIN_BODY_BYTES:
                continue

            mime: str = content.get("mimeType", "")
            # Quick filter for likely JSON. Some APIs return text/plain.
            if mime and ("json" not in mime.lower() and not body.lstrip().startswith(("{", "["))):
                continue

            try:
                parsed = json.loads(body)
            except (json.JSONDecodeError, ValueError):
                continue

            req_url = request.get("url", "")
            if not req_url:
                continue

            out.append({
                "url": req_url,
                "shape": _summarise(parsed),
            })
        except Exception:
            continue
    return out


def _summarise(obj, depth: int = 0) -> object:
    """Compact structural summary — first item of arrays, first 8 keys of dicts."""
    if depth > 4:
        return "..."
    if isinstance(obj, dict):
        return {k: _summarise(v, depth + 1) for k, v in list(obj.items())[:8]}
    if isinstance(obj, list):
        return [_summarise(obj[0], depth + 1)] if obj else []
    return type(obj).__name__
