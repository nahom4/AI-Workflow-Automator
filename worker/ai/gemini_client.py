"""Gemini client — vision bbox grounding + async text-only fallback ranker.

Sync paths (`detect_listing_bboxes`, `pick_listing_selectors`) use `requests`
because they're called from within `asyncio.to_thread` already.

Async path (`chat_text_metered`) uses `httpx.AsyncClient` so the metrics
recording can stay async-native. It's wrapped in tenacity and writes to the
`llm_calls` table via the observability shim.
"""

from __future__ import annotations

import base64
import json
import time

import httpx
import requests

from worker.config import GEMINI_API_KEYS, GEMINI_MODEL

_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
_RETRY_DELAYS = (1.5, 3.0, 6.0)  # 3 retries per key on 429/503; ~10s total

# Last error from pick_listing_selectors, so callers can log status codes
# without us threading an exception type through every call site.
LAST_SELECTOR_ERROR: str | None = None


def _is_hard_quota_429(body_text: str) -> bool:
    """A 429 with daily-quota messaging is not retryable on this key. We must
    rotate to the next key (or give up) without burning more retries."""
    b = (body_text or "").lower()
    return (
        "exceeded your current quota" in b
        or "resource_exhausted" in b
        or "quota metric" in b
    )


def _post_gemini(body: dict) -> tuple[dict | None, int | None, str | None]:
    """POST `body` to Gemini. Retries 503 (and transient rate-limit 429) with
    exponential backoff on the same key before rotating. Hard-quota 429s
    rotate to the next key immediately — retrying a key that's been
    daily-quota-blocked just wastes time.

    Returns (parsed_json_dict, last_status, last_body_trimmed).
    """
    last_status: int | None = None
    last_body: str | None = None
    for key in GEMINI_API_KEYS:
        url = f"{_API_BASE}/models/{GEMINI_MODEL}:generateContent?key={key}"
        for attempt in range(1 + len(_RETRY_DELAYS)):
            if attempt > 0:
                time.sleep(_RETRY_DELAYS[attempt - 1])
            try:
                r = requests.post(url, json=body, timeout=60)
            except requests.RequestException as exc:
                last_status, last_body = -1, repr(exc)
                break  # try next key
            last_status, last_body = r.status_code, (r.text or "")[:300]
            if r.status_code == 200:
                try:
                    return json.loads(r.text), 200, None
                except json.JSONDecodeError:
                    return None, 200, last_body
            if r.status_code == 429 and _is_hard_quota_429(r.text):
                break  # rotate immediately — this key is dead for the day
            if r.status_code in (429, 503):
                continue  # backoff and retry same key (transient)
            break  # 4xx auth / malformed — try next key
    return None, last_status, last_body

_BBOX_PROMPT = (
    "Look at this webpage screenshot. Identify the main repeating LISTING items "
    "that a user came to this page to browse — for example: scholarship cards, "
    "job postings, grant opportunities, course listings, search results.\n\n"
    "Explicitly IGNORE: navigation menus, header links, footer links, "
    "filter widgets/sidebars, tag clouds, breadcrumbs, social-share buttons, "
    "newsletter signup boxes, cookie banners, marketing/advertising cards, "
    "Cloudflare or other security challenges.\n\n"
    "Return a JSON array (no prose, no markdown fences) of the bounding boxes "
    "for each listing item, in the format:\n"
    '[{"box_2d": [ymin, xmin, ymax, xmax], "label": "short description"}]\n\n'
    "Coordinates must be normalized 0..1000 (Gemini's standard). "
    "If there are no listings on this page, return []."
)


class GeminiUnavailable(Exception):
    """All keys exhausted or no keys configured."""


def chat_text(prompt: str, *, system: str = "", json_mode: bool = True, temperature: float = 0.0) -> str:
    """Legacy sync wrapper kept for back-compat. Prefer `chat_text_metered`
    when calling from async code so cost/latency metrics are recorded.
    """
    if not GEMINI_API_KEYS:
        raise GeminiUnavailable("no GEMINI_API_KEYS configured")
    body = _build_chat_body(prompt, system=system, json_mode=json_mode, temperature=temperature)
    parsed, status, body_trimmed = _post_gemini(body)
    if status == 200 and parsed is not None:
        return _extract_model_text(parsed)
    raise GeminiUnavailable(
        f"chat_text exhausted (last status={status}): {(body_trimmed or '')[:200]}"
    )


def _build_chat_body(prompt: str, *, system: str, json_mode: bool, temperature: float) -> dict:
    user_text = prompt if not system else f"{system}\n\n{prompt}"
    body: dict = {
        "contents": [{"parts": [{"text": user_text}]}],
        "generationConfig": {
            "temperature": temperature,
            # Disable thinking — for a structured ranker prompt, thinking
            # adds 5-10s per call with no quality gain.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    return body


async def chat_text_metered(
    prompt: str,
    *,
    system: str = "",
    json_mode: bool = True,
    temperature: float = 0.0,
    purpose: str = "rank",
) -> str:
    """Async Gemini chat with key rotation, retry-on-503/429, and cost/latency
    tracking via the `llm_calls` observability shim.

    Raises GeminiUnavailable if every key is exhausted.
    """
    # Lazy imports to avoid circular dependency at module load
    from worker.obs.metrics import observe_llm_call

    if not GEMINI_API_KEYS:
        raise GeminiUnavailable("no GEMINI_API_KEYS configured")

    body = _build_chat_body(prompt, system=system, json_mode=json_mode, temperature=temperature)
    last_status: int | None = None
    last_body: str | None = None

    async with httpx.AsyncClient(timeout=60) as client:
        for key in GEMINI_API_KEYS:
            url = f"{_API_BASE}/models/{GEMINI_MODEL}:generateContent?key={key}"
            for attempt in range(1 + len(_RETRY_DELAYS)):
                if attempt > 0:
                    import asyncio as _asyncio
                    await _asyncio.sleep(_RETRY_DELAYS[attempt - 1])
                start = time.time()
                try:
                    r = await client.post(url, json=body)
                except httpx.RequestError as exc:
                    last_status, last_body = -1, repr(exc)
                    await observe_llm_call(
                        provider="gemini", model=GEMINI_MODEL, purpose=purpose,
                        latency_ms=int((time.time() - start) * 1000),
                        status="error", error=last_body[:300],
                    )
                    break  # next key
                latency_ms = int((time.time() - start) * 1000)
                last_status = r.status_code
                last_body = (r.text or "")[:300]
                if r.status_code == 200:
                    try:
                        parsed = r.json()
                    except ValueError:
                        await observe_llm_call(
                            provider="gemini", model=GEMINI_MODEL, purpose=purpose,
                            latency_ms=latency_ms, status="error",
                            error="invalid JSON in 200 response",
                        )
                        return ""
                    usage = parsed.get("usageMetadata") or {}
                    await observe_llm_call(
                        provider="gemini", model=GEMINI_MODEL, purpose=purpose,
                        tokens_in=int(usage.get("promptTokenCount") or 0),
                        tokens_out=int(usage.get("candidatesTokenCount") or 0),
                        latency_ms=latency_ms, status="success",
                    )
                    return _extract_model_text(parsed)
                if r.status_code == 429 and _is_hard_quota_429(r.text):
                    await observe_llm_call(
                        provider="gemini", model=GEMINI_MODEL, purpose=purpose,
                        latency_ms=latency_ms, status="error",
                        error=f"daily-quota 429: {last_body[:200]}",
                    )
                    break  # rotate immediately
                if r.status_code in (429, 503):
                    await observe_llm_call(
                        provider="gemini", model=GEMINI_MODEL, purpose=purpose,
                        latency_ms=latency_ms, status="retry",
                        error=f"transient {r.status_code}",
                    )
                    continue  # backoff + retry same key
                await observe_llm_call(
                    provider="gemini", model=GEMINI_MODEL, purpose=purpose,
                    latency_ms=latency_ms, status="error",
                    error=f"{r.status_code}: {last_body[:200]}",
                )
                break  # 4xx auth/malformed — try next key

    raise GeminiUnavailable(
        f"chat_text_metered exhausted (last status={last_status}): {(last_body or '')[:200]}"
    )


def detect_listing_bboxes(png_bytes: bytes) -> list[dict]:
    """Return a list of {box_2d: [ymin, xmin, ymax, xmax], label: str}.

    Empty list = page has no listings (Gemini's correct answer for marketing
    pages, search forms, etc.). Raises GeminiUnavailable if every key returns
    a non-success status (429 or 503 after retries).
    """
    if not GEMINI_API_KEYS:
        raise GeminiUnavailable("no GEMINI_API_KEYS configured")

    b64 = base64.b64encode(png_bytes).decode("ascii")
    body = {
        "contents": [{
            "parts": [
                {"text": _BBOX_PROMPT},
                {"inline_data": {"mime_type": "image/png", "data": b64}},
            ],
        }],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }
    parsed, status, body_trimmed = _post_gemini(body)
    if status == 200 and parsed is not None:
        return _parse_bboxes_response(parsed)
    raise GeminiUnavailable(
        f"all keys exhausted (last status={status}): {(body_trimmed or '')[:200]}"
    )


def _extract_model_text(outer: dict) -> str:
    """Walk a Gemini generateContent response down to the model's text payload."""
    parts = outer.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    if not parts:
        return ""
    text = (parts[0].get("text") or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    return text


def _parse_bboxes_response(outer: dict) -> list[dict]:
    text = _extract_model_text(outer)
    if not text:
        return []
    try:
        boxes = json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find("["), text.rfind("]")
        if s >= 0 and e > s:
            try:
                boxes = json.loads(text[s:e + 1])
            except Exception:
                return []
        else:
            return []
    if not isinstance(boxes, list):
        return []
    out: list[dict] = []
    for b in boxes:
        if not isinstance(b, dict):
            continue
        bb = b.get("box_2d") or b.get("bbox") or b.get("bounding_box")
        if not bb or not isinstance(bb, list) or len(bb) != 4:
            continue
        try:
            bb = [int(x) for x in bb]
        except (TypeError, ValueError):
            continue
        out.append({"box_2d": bb, "label": str(b.get("label") or "")})
    return out


# ---------------------------------------------------------------------------
# Label-based filtering: when Gemini correctly identifies non-listing regions
# (nav, footer, marketing) instead of listings, we want to detect that and
# treat the page as "no listings here, move on." Cheaper than re-prompting.

_NEGATIVE_LABEL_PATTERNS = (
    "nav", "menu", "category", "filter", "footer", "header",
    "social", "newsletter", "subscription", "cookie", "consent",
    "membership", "sign in", "sign up", "login", "search box",
    "breadcrumb", "tag", "advertisement",
)


_SELECTOR_PROMPT_TEMPLATE = (
    "You previously identified {n} listing items in this page screenshot.\n\n"
    "For each item, here is the actual DOM context at that listing's centroid. "
    "The 'chain' is the element's tag.class path walking up to the page root.\n\n"
    "DOM snippets:\n{snippets}\n\n"
    "Return a JSON object (no prose, no markdown) with these fields:\n"
    '  "card_selector":  CSS selector that matches every real listing card on the page\n'
    '                    (NOT navigation, NOT ads, NOT footer links).\n'
    '  "title_selector": CSS selector relative to a card to find the title element.\n'
    '                    Empty string "" if the card itself contains the title text.\n'
    '  "title_attr":     attribute name to read for title (e.g. "aria-label"), '
    'or null for textContent.\n'
    '  "url_selector":   CSS selector relative to a card for the listing\'s permalink.\n'
    '  "url_attr":       attribute name (typically "href").\n\n'
    "Guidelines:\n"
    "- COUNT RULE: you identified {n} listing bboxes in the screenshot. Your "
    "card_selector MUST match approximately {n} elements on the page (within "
    "~30% tolerance is fine — virtualized lists may show fewer in DOM). If "
    "your selector would match only 1-3 elements, you picked a wrapper "
    "(a sidebar, a results container, a 'filter-results' div). That is wrong "
    "even if the wrapper visually 'contains' the listings. Pick a deeper "
    "selector (the child elements inside the wrapper).\n"
    "- Prefer parent > child form (e.g., 'ul.list > li.card') when card classes "
    "vary or are too generic ('div', 'item').\n"
    "- Pick the most specific class shared by ALL listing cards. If the cards "
    "have NO shared class, fall back to the tag name itself (e.g., "
    "'media-info-tile' for a web component) or a parent > tag form.\n"
    "- For title_selector, prefer a child element with clean text (h2, h3, "
    "[class*='title'], [itemprop='name']) over reading the whole card text. "
    "If the title lives on an attribute (alt, aria-label, title), set "
    "title_attr accordingly. Verify the selector path you write actually "
    "appears in at least one snippet's outer_html — do not invent class "
    "chains that look plausible but aren't in the DOM.\n"
    "- URL ATTRIBUTE RULE: url_attr MUST be one of: 'href' (default for any "
    "<a> tag), or an attribute name that appears LITERALLY in at least one "
    "snippet's outer_html string. Do NOT fabricate names like 'media-url', "
    "'data-href', 'item-url' unless you can quote that exact attribute from "
    "the snippets. When in doubt, default to url_selector='a' url_attr='href' "
    "— even if no snippet has href (the snippet's <a> may be outside the "
    "truncated 600 chars), 'a' + 'href' is almost always correct for any "
    "clickable card.\n"
    "- If the snippets look like navigation, ads, or filter widgets rather "
    'than real listings, return {{"reject": true}}.\n'
)


def pick_listing_selectors(
    png_bytes: bytes, snippets: list[dict]
) -> dict | None:
    """Send the screenshot + DOM snippets at each Gemini-identified listing
    back to Gemini. Ask it to derive a CSS spec (card + title + url selectors)
    that captures every real listing on the page.

    Returns the parsed JSON spec, or None on failure / explicit reject. On
    failure, `LAST_SELECTOR_ERROR` is set to a short reason string callers
    can read for logging.
    """
    global LAST_SELECTOR_ERROR
    LAST_SELECTOR_ERROR = None

    if not GEMINI_API_KEYS:
        LAST_SELECTOR_ERROR = "no GEMINI_API_KEYS configured"
        return None
    if not snippets:
        LAST_SELECTOR_ERROR = "no snippets to send"
        return None

    prompt = _SELECTOR_PROMPT_TEMPLATE.format(
        n=len(snippets),
        snippets=json.dumps(snippets, indent=2)[:6000],
    )
    b64 = base64.b64encode(png_bytes).decode("ascii")
    body = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/png", "data": b64}},
            ],
        }],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json",
        },
    }

    parsed, status, body_trimmed = _post_gemini(body)
    if status == 200 and parsed is not None:
        spec = _parse_selector_response(parsed)
        if spec is None:
            LAST_SELECTOR_ERROR = f"could not parse response JSON: {(body_trimmed or '')[:120]}"
        return spec
    LAST_SELECTOR_ERROR = f"status={status} body={(body_trimmed or '')[:150]}"
    return None


def _parse_selector_response(outer: dict) -> dict | None:
    text = _extract_model_text(outer)
    if not text:
        return None
    try:
        spec = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(spec, dict):
        return None
    return spec


def labels_look_like_listings(boxes: list[dict]) -> bool:
    """Heuristic: do the bbox labels Gemini returned describe real listings,
    or did it find marketing/nav cards that happen to be visually card-shaped?
    """
    if not boxes:
        return False
    labels = [(b.get("label") or "").lower() for b in boxes]
    # If a majority of labels match "negative" patterns, reject.
    neg = sum(
        1 for l in labels
        if any(p in l for p in _NEGATIVE_LABEL_PATTERNS)
    )
    return neg < len(labels) / 2
