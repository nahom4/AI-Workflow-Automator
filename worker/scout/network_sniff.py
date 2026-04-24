"""
Tier 1 scout: capture XHR/fetch responses during page load using pydoll's
get_network_logs() + get_network_response_body(), then ask Groq which
endpoint carries the listing data for a given vertical.

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

import json

from worker.ai.groq_client import chat
from worker.browser import navigate, settle

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
_MIN_BODY_BYTES = 2048

# Resource types we care about
_FETCH_TYPES = {"XHR", "Fetch"}


async def scout(tab, *, url: str, vertical: str) -> dict | None:
    """
    Navigate to `url` with network logging enabled, collect JSON responses,
    ask Groq which one contains the listing. Returns a Tier-1 spec or None.
    """
    await tab.enable_network_events()
    await navigate(tab, url)
    await settle(tab, 3)

    captured = await _collect_json_responses(tab)

    if not captured:
        return None

    prompt = (
        f"Vertical: {vertical}\n"
        f"Page URL: {url}\n\n"
        f"Captured XHR/fetch responses (up to 10 with JSON bodies ≥2 KB):\n"
        + json.dumps(captured[:10], ensure_ascii=False)
    )
    raw = await chat(prompt, system=_SYSTEM)
    try:
        result = json.loads(raw)
        if result.get("found") is False:
            return None
        # Validate minimum required fields
        if not result.get("endpoint") or not result.get("fields"):
            return None
        return result
    except Exception:
        return None


async def _collect_json_responses(tab) -> list[dict]:
    """
    Pull all logged requests via get_network_logs(), fetch their bodies,
    keep only those that parse as JSON and are large enough to be data.
    """
    try:
        logs = await tab.get_network_logs()
    except Exception:
        return []

    captured: list[dict] = []

    for log in logs:
        params = log.get("params", {})
        req_url: str = params.get("request", {}).get("url", "")
        request_id: str = params.get("requestId", "")
        resource_type: str = params.get("type", "")

        if not request_id or not req_url:
            continue
        # Skip non-data resource types
        if resource_type and resource_type not in _FETCH_TYPES:
            continue
        # Skip obviously non-API URLs
        if any(ext in req_url for ext in (".js", ".css", ".png", ".jpg", ".svg", ".woff")):
            continue

        try:
            body = await tab.get_network_response_body(request_id)
        except Exception:
            continue

        if not body or len(body) < _MIN_BODY_BYTES:
            continue

        try:
            parsed = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            continue

        captured.append({
            "url": req_url,
            "shape": _summarise(parsed),
        })

    return captured


def _summarise(obj, depth: int = 0) -> object:
    """Compact structural summary — first item of arrays, first 8 keys of dicts."""
    if depth > 4:
        return "..."
    if isinstance(obj, dict):
        return {k: _summarise(v, depth + 1) for k, v in list(obj.items())[:8]}
    if isinstance(obj, list):
        return [_summarise(obj[0], depth + 1)] if obj else []
    return type(obj).__name__
