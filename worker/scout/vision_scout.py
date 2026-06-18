"""Vision-grounded scout: pydoll renders the page, Gemini identifies listing
bboxes from a full-page screenshot, then JS maps those bboxes back to DOM
elements and we derive a CSS selector for the listing container.

This replaces the heuristic Tier-2 scout (`pydantic_scout.py`) which kept
mistaking tag clouds and nav menus for listings. Vision is zero-shot, free
on Gemini 2.5 Flash, and correctly returns "no listings here" when the
URL doesn't have any — letting the URL-discovery ladder try a different page
instead of returning garbage.

The output spec is intentionally compatible with the existing
`_extract_pydantic_at_url` runner so we don't need a separate extractor.
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Optional

from worker.ai import gemini_client
from worker.browser import navigate, wait_for_content


async def scout(
    tab,
    *,
    url: str,
    vertical: str,
) -> Optional[dict]:
    """Render `url`, ask Gemini for listing bboxes, derive a CSS selector.

    Returns a spec dict (compatible with `_extract_pydantic_at_url`) or None
    if the page has no listings, vision was unavailable, or DOM mapping
    couldn't find a stable selector.
    """
    # 1. Navigate + settle
    try:
        await asyncio.wait_for(navigate(tab, url), timeout=60.0)
        await asyncio.wait_for(wait_for_content(tab, max_wait=20.0), timeout=25.0)
    except asyncio.TimeoutError:
        return None

    # Extra settle for dynamic SPAs
    await asyncio.sleep(2.0)

    # 2. Full-page screenshot via CDP captureBeyondViewport
    png_bytes, page_w, page_h = await _full_page_screenshot(tab)
    if not png_bytes:
        return None

    # 3. Gemini bboxes
    try:
        boxes = gemini_client.detect_listing_bboxes(png_bytes)
    except gemini_client.GeminiUnavailable:
        return None

    if not boxes:
        # Page genuinely has no listings — let caller try another URL.
        return None

    if not gemini_client.labels_look_like_listings(boxes):
        # Gemini found visually-card-shaped things (e.g. "Newsletter card",
        # "Membership card") but they aren't listings. Same signal as empty:
        # this URL is wrong, try another.
        return None

    # 4. Map bbox centroids to DOM elements
    centroids = []
    for b in boxes:
        bb = b["box_2d"]
        ymin, xmin, ymax, xmax = bb
        cx = (xmin + xmax) / 2 / 1000.0 * page_w
        cy = (ymin + ymax) / 2 / 1000.0 * page_h
        centroids.append([cx, cy])

    selector_info = await _derive_selector(tab, centroids)
    if not selector_info or not selector_info.get("card_selector"):
        return None

    # 5. Build a spec compatible with the existing extractor.
    spec = {
        "tier": "vision",
        "card_selector": selector_info["card_selector"],
        "entry_url": url,
        "entry_urls": [url],
        "fields": {
            # First <a> inside the card: text → title, href → url
            "title": {"selector": "a", "attr": None},
            "url": {"selector": "a", "attr": "href"},
        },
        "vision_meta": {
            "n_boxes": len(boxes),
            "matched_cards": selector_info.get("matched_count", 0),
            "labels_sample": [b.get("label") for b in boxes[:3]],
        },
    }
    return spec


# ---------------------------------------------------------------------------


async def _full_page_screenshot(tab) -> tuple[bytes, int, int]:
    """Return (png_bytes, page_width, page_height). Capture beyond viewport
    so listings below the fold are visible to Gemini.
    """
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
        page_h = min(int(v.get("h") or 1600), 6000)  # cap at 6000px to stay sane
    except Exception:
        page_w, page_h = 1280, 1600

    try:
        r = await asyncio.wait_for(
            tab._connection_handler.execute_command(
                {
                    "method": "Page.captureScreenshot",
                    "params": {
                        "format": "png",
                        "captureBeyondViewport": True,
                        "clip": {
                            "x": 0,
                            "y": 0,
                            "width": page_w,
                            "height": page_h,
                            "scale": 1,
                        },
                    },
                }
            ),
            timeout=30.0,
        )
    except Exception:
        return b"", page_w, page_h

    data_b64 = (r or {}).get("result", {}).get("data") if isinstance(r, dict) else None
    if not data_b64:
        return b"", page_w, page_h
    return base64.b64decode(data_b64), page_w, page_h


async def _derive_selector(tab, centroids: list[list[float]]) -> Optional[dict]:
    """Find the DOM element nearest each (page-x, page-y) centroid, then
    compute a stable selector for the listing container's children.

    Returns {card_selector, matched_count} or None.
    """
    js = r"""
    const centroids = %s;

    // For each centroid, find the deepest element whose absolute (page-coord)
    // bounding box contains the point.
    function elementAtPagePoint(px, py) {
      let best = null;
      let bestArea = Infinity;
      const all = document.querySelectorAll('*');
      for (const el of all) {
        const r = el.getBoundingClientRect();
        const top = r.top + window.scrollY;
        const left = r.left + window.scrollX;
        const w = r.width, h = r.height;
        if (w <= 0 || h <= 0) continue;
        if (px < left || px > left + w) continue;
        if (py < top || py > top + h) continue;
        const area = w * h;
        // Prefer the smallest containing element (deepest), but skip absurd
        // outliers like body/html that contain everything.
        if (area < bestArea && area > 100) {
          best = el;
          bestArea = area;
        }
      }
      return best;
    }

    function pathPart(el) {
      let part = el.tagName.toLowerCase();
      if (el.id) return part + '#' + el.id;
      const cls = (el.className && typeof el.className === 'string')
        ? el.className.trim().split(/\s+/).filter(Boolean).slice(0, 2).join('.')
        : '';
      if (cls) part += '.' + cls;
      return part;
    }

    const hits = [];
    for (const [px, py] of centroids) {
      const el = elementAtPagePoint(px, py);
      if (el) hits.push(el);
    }
    if (hits.length < 2) return JSON.stringify({error: 'fewer than 2 hits', n: hits.length});

    // Walk each hit upward to find a "card-shaped" ancestor: an element whose
    // siblings (under the same parent) are mostly the same tag. The card is
    // the level just below the listing container.
    function findCardAncestor(el) {
      let cur = el;
      while (cur && cur.parentElement && cur.parentElement.children.length > 1) {
        const sibs = Array.from(cur.parentElement.children);
        const sameTag = sibs.filter(s => s.tagName === cur.tagName).length;
        // If ≥3 siblings share the same tag, this is the card level.
        if (sameTag >= 3 && sibs.length >= 3) return cur;
        // Otherwise climb one level (parent might be the card if hit was deep
        // inside a single card).
        cur = cur.parentElement;
        // Don't climb past body
        if (!cur || cur === document.body) return null;
      }
      return null;
    }

    const cards = hits.map(findCardAncestor).filter(Boolean);
    if (cards.length < 2) return JSON.stringify({error: 'no card ancestor found'});

    // Group by parent and pick the parent that contains the most cards.
    const byParent = new Map();
    for (const c of cards) {
      const p = c.parentElement;
      if (!p) continue;
      if (!byParent.has(p)) byParent.set(p, []);
      byParent.get(p).push(c);
    }
    let bestParent = null;
    let bestCards = [];
    for (const [p, list] of byParent) {
      if (list.length > bestCards.length) {
        bestParent = p;
        bestCards = list;
      }
    }
    if (!bestParent) return JSON.stringify({error: 'no consensus parent'});

    // Find a class/tag fingerprint that ALL same-tag children of bestParent
    // share. Start with the most specific (full class set), fall back to tag.
    const sameTag = Array.from(bestParent.children)
      .filter(c => c.tagName === bestCards[0].tagName);

    function classListOf(el) {
      return Array.from(el.classList || []).filter(Boolean);
    }
    // Find the intersection of class lists across all sameTag children.
    let common = classListOf(sameTag[0]);
    for (let i = 1; i < sameTag.length; i++) {
      const cs = new Set(classListOf(sameTag[i]));
      common = common.filter(c => cs.has(c));
      if (!common.length) break;
    }

    const childPart = sameTag[0].tagName.toLowerCase()
      + (common.length ? '.' + common.slice(0, 2).join('.') : '');
    // Use ONLY the immediate parent's tag+classes — the existing
    // _extract_pydantic_at_url enforces strict class-set match on the
    // first selector segment, so deeper paths fail spuriously.
    const parentPart = pathPart(bestParent);
    const card_selector = parentPart + ' > ' + childPart;

    return JSON.stringify({
      card_selector,
      matched_count: sameTag.length,
      sample_text: sameTag.slice(0, 3).map(s => (s.innerText || '').slice(0, 80)),
    });
    """ % json.dumps(centroids)

    try:
        raw = await asyncio.wait_for(
            tab.execute_script(js, return_by_value=True), timeout=10.0
        )
    except asyncio.TimeoutError:
        return None

    try:
        value = raw["result"]["result"]["value"]
    except (KeyError, TypeError):
        return None
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    if parsed.get("error"):
        return None
    return parsed
