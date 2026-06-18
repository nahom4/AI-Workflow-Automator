"""Vision scout v2: screenshot + DOM snippets → Gemini → CSS spec.

The v1 vision scout (`vision_scout.py`) used a JS heuristic (`findCardAncestor`,
common-parent + class-intersection) to convert Gemini bboxes into a CSS selector.
That heuristic overshoots to layout containers (e.g. `<body> > div`) when bbox
centroids land on deeply-nested tile elements whose immediate parents differ.

v2 replaces the heuristic with a second Gemini call. For each bbox, we extract
the actual DOM element at the centroid plus its parent class chain. We send the
screenshot AND those snippets back to Gemini and ask it to return a clean CSS
spec ({card_selector, title_selector, url_selector}). Gemini sees both signals
at once — visual (what's a card) and structural (which class names anchor them).
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Optional

from worker.ai import gemini_client
from worker.browser import navigate, wait_for_content


async def scout(tab, *, url: str, vertical: str) -> Optional[dict]:
    """Same return contract as `vision_scout.scout`: dict spec or None."""
    try:
        await asyncio.wait_for(navigate(tab, url), timeout=60.0)
        await asyncio.wait_for(wait_for_content(tab, max_wait=20.0), timeout=25.0)
    except asyncio.TimeoutError:
        return None
    await asyncio.sleep(2.0)

    png_bytes, page_w, page_h = await _full_page_screenshot(tab)
    if not png_bytes:
        return None

    try:
        boxes = gemini_client.detect_listing_bboxes(png_bytes)
    except gemini_client.GeminiUnavailable:
        return None
    if not boxes or not gemini_client.labels_look_like_listings(boxes):
        return None

    snippets = await _gather_card_snippets(tab, boxes, page_w, page_h)
    if not snippets:
        return None

    ai_spec = gemini_client.pick_listing_selectors(png_bytes, snippets)
    if not ai_spec or ai_spec.get("reject"):
        return None

    card_sel = ai_spec.get("card_selector")
    if not card_sel:
        return None

    title_sel = ai_spec.get("title_selector") or ""
    title_attr = ai_spec.get("title_attr")
    # Preserve explicit empty string from the AI — "" means "the card element
    # itself" (used when the URL/title lives on an attribute of the card, e.g.,
    # `<poster-tile media-url="/m/x">`). Only default to "a" when the AI omitted
    # the field entirely.
    url_sel = ai_spec.get("url_selector")
    if url_sel is None:
        url_sel = "a"
    url_attr = ai_spec.get("url_attr") or "href"

    return {
        "tier": "vision_v2",
        "card_selector": card_sel,
        "entry_url": url,
        "entry_urls": [url],
        "fields": {
            "title": {"selector": title_sel, "attr": title_attr},
            "url": {"selector": url_sel, "attr": url_attr},
        },
        "vision_meta": {
            "n_boxes": len(boxes),
            "labels_sample": [b.get("label") for b in boxes[:3]],
            "ai_spec_raw": ai_spec,
        },
    }


# ---------------------------------------------------------------------------


async def _full_page_screenshot(tab) -> tuple[bytes, int, int]:
    """Capture beyond viewport (same as v1)."""
    try:
        metrics = await asyncio.wait_for(
            tab.execute_script(
                "return {h: document.body.scrollHeight, w: document.body.scrollWidth}",
                return_by_value=True,
            ),
            timeout=5.0,
        )
        v = metrics.get("result", {}).get("result", {}).get("value", {}) or {}
        page_w = int(v.get("w") or 1280)
        page_h = min(int(v.get("h") or 1600), 6000)
    except Exception:
        page_w, page_h = 1280, 1600
    try:
        r = await asyncio.wait_for(
            tab._connection_handler.execute_command({
                "method": "Page.captureScreenshot",
                "params": {
                    "format": "png",
                    "captureBeyondViewport": True,
                    "clip": {"x": 0, "y": 0, "width": page_w, "height": page_h, "scale": 1},
                },
            }),
            timeout=30.0,
        )
    except Exception:
        return b"", page_w, page_h
    data = (r or {}).get("result", {}).get("data") if isinstance(r, dict) else None
    if not data:
        return b"", page_w, page_h
    return base64.b64decode(data), page_w, page_h


async def _gather_card_snippets(
    tab, boxes: list[dict], page_w: int, page_h: int
) -> list[dict]:
    """For each Gemini bbox centroid, find the smallest reasonable DOM ancestor
    (≥80x60 px so we don't capture a tiny inner span) and return a compact
    snippet: parent class chain + outerHTML (truncated) + nearest <a href>.

    Caps to 12 snippets to keep the prompt small.
    """
    centroids = []
    for b in boxes[:12]:
        ymin, xmin, ymax, xmax = b["box_2d"]
        cx = (xmin + xmax) / 2 / 1000.0 * page_w
        cy = (ymin + ymax) / 2 / 1000.0 * page_h
        centroids.append([cx, cy, b.get("label", "")])

    js = """
    const targets = %s;
    // Snapshot every element ONCE (5-50k on big pages) and iterate absolute
    // coords to find the smallest containing element. No scrolling — works on
    // virtualized SPAs (Metacritic, RT) where scrolling destroys+recreates
    // tiles. Trade-off: items below the rendered DOM aren't reachable, but
    // we only need a handful of snippets to derive a selector.
    const allEls = document.querySelectorAll('*');
    function elementAtAbsPoint(px, py) {
      let best = null;
      let bestArea = Infinity;
      for (const el of allEls) {
        const r = el.getBoundingClientRect();
        if (r.width <= 0 || r.height <= 0) continue;
        const top = r.top + window.scrollY;
        const left = r.left + window.scrollX;
        if (px < left || px > left + r.width) continue;
        if (py < top || py > top + r.height) continue;
        const area = r.width * r.height;
        if (area < bestArea && area > 100) {
          best = el;
          bestArea = area;
        }
      }
      return best;
    }
    function chain(el, n) {
      const out = [];
      let cur = el;
      for (let i = 0; i < n && cur; i++) {
        const tag = cur.tagName ? cur.tagName.toLowerCase() : '';
        if (!tag) break;
        const cls = Array.from(cur.classList || [])
          .filter(Boolean).slice(0, 4).join('.');
        out.push(cls ? tag + '.' + cls : tag);
        cur = cur.parentElement;
      }
      return out;
    }
    const out = [];
    for (const [px, py, label] of targets) {
      let el = elementAtAbsPoint(px, py);
      if (!el) continue;
      // Walk up until the element has card-sized bbox (>= 80x60). Skips
      // tiny inner spans/icons we landed on by accident.
      while (el && el.parentElement) {
        const r = el.getBoundingClientRect();
        if (r.width >= 80 && r.height >= 60) break;
        el = el.parentElement;
      }
      if (!el) continue;
      const a = el.querySelector('a[href]');
      const text = (el.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 200);
      out.push({
        label: label || '',
        chain: chain(el, 4),
        outer_html: (el.outerHTML || '').slice(0, 600),
        href: a ? a.getAttribute('href') : null,
        text: text,
      });
    }
    return JSON.stringify(out);
    """ % json.dumps(centroids)

    try:
        raw = await asyncio.wait_for(
            tab.execute_script(js, return_by_value=True), timeout=15.0
        )
    except asyncio.TimeoutError:
        return []
    try:
        value = raw["result"]["result"]["value"]
    except (KeyError, TypeError):
        return []
    if not value:
        return []
    try:
        snippets = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(snippets, list):
        return []
    return snippets
