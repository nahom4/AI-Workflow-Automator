"""Test #2: Gemini 2.5 Flash vision bbox grounding for listings detection.

Pipeline:
  1. Load URL with Crawl4AI, take a 1280x1600 screenshot, capture DOM.
  2. Send screenshot + prompt to Gemini 2.5 Flash asking for bboxes of "main listings".
     Gemini returns [ymin, xmin, ymax, xmax] normalized 0..1000.
  3. Map each bbox centroid back to a DOM element via elementsFromPoint and
     print the selector path.
  4. Save an annotated PNG showing the boxes overlaid.

Run: python scripts/spike_vision_bbox.py <url> [more urls...]
"""
import asyncio
import base64
import json
import os
import pathlib
import sys
import time

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)

# Load .env.local for GEMINI_API_KEYS
_envfile = pathlib.Path(".env.local")
if _envfile.exists():
    for line in _envfile.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

GEMINI_KEYS = [k.strip() for k in (os.environ.get("GEMINI_API_KEYS") or "").split(",") if k.strip()]
MODEL = "gemini-2.5-flash"
PROMPT = (
    "Look at this webpage screenshot. Identify the main repeating LISTING items "
    "that a user came to this page to browse — for example: scholarship cards, "
    "job postings, grant opportunities, course listings. \n\n"
    "Explicitly IGNORE: navigation menus, header links, footer links, "
    "filter widgets/sidebars, tag clouds, breadcrumbs, social-share buttons.\n\n"
    "Return a JSON array (no prose, no markdown fences) of the bounding boxes "
    "for each listing item, in the format:\n"
    '[{"box_2d": [ymin, xmin, ymax, xmax], "label": "short description of this item"}]\n\n'
    "Coordinates must be normalized 0..1000. If there are no listings on the page, "
    "return []."
)

OUT_DIR = pathlib.Path("test-results/vision-bbox")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _slug(url: str) -> str:
    return (url.replace("https://", "").replace("http://", "")
            .replace("/", "_").replace("?", "_").rstrip("_"))[:60]


async def take_screenshot_and_dom(url: str) -> tuple[bytes, dict, int, int]:
    """Returns (png_bytes, viewport_dom_info, viewport_w, viewport_h)."""
    browser_cfg = BrowserConfig(
        headless=True,
        viewport_width=1280,
        viewport_height=1600,
        enable_stealth=True,  # routes through patchright; needed for Cloudflare sites
    )
    run_cfg = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        screenshot=True,
        wait_for="css:body",
        # Cloudflare Turnstile usually clears in ~5s; give extra time before screenshot.
        delay_before_return_html=6.0,
    )
    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        result = await crawler.arun(url=url, config=run_cfg)
        if not result.success:
            raise RuntimeError(f"fetch failed: {result.error_message}")
        if not result.screenshot:
            raise RuntimeError("no screenshot returned")
        png = base64.b64decode(result.screenshot)
        return png, {"html_len": len(result.html or "")}, 1280, 1600


def call_gemini_bbox(png_bytes: bytes, key: str) -> tuple[int, str]:
    """Call Gemini with the screenshot. Returns (http_status, response_text)."""
    b64 = base64.b64encode(png_bytes).decode("ascii")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={key}"
    body = {
        "contents": [{
            "parts": [
                {"text": PROMPT},
                {"inline_data": {"mime_type": "image/png", "data": b64}},
            ],
        }],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }
    r = requests.post(url, json=body, timeout=60)
    return r.status_code, r.text


def parse_bboxes(resp_text: str) -> list[dict]:
    """Pull the JSON array out of Gemini's response."""
    try:
        outer = json.loads(resp_text)
    except json.JSONDecodeError:
        return []
    candidates = outer.get("candidates", [])
    if not candidates:
        return []
    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        return []
    text = parts[0].get("text", "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        boxes = json.loads(text)
    except json.JSONDecodeError:
        # Try to find first balanced array
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            try:
                boxes = json.loads(text[start:end + 1])
            except Exception:
                return []
        else:
            return []
    return boxes if isinstance(boxes, list) else []


def annotate(png_bytes: bytes, boxes: list[dict], out_path: pathlib.Path) -> None:
    img = Image.open(BytesIO(png_bytes)).convert("RGB")
    draw = ImageDraw.Draw(img)
    w, h = img.size
    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except Exception:
        font = ImageFont.load_default()
    for i, b in enumerate(boxes, 1):
        bb = b.get("box_2d") or b.get("bbox") or b.get("bounding_box")
        if not bb or len(bb) != 4:
            continue
        ymin, xmin, ymax, xmax = bb
        # Gemini returns 0..1000 normalized
        x1 = int(xmin / 1000 * w)
        y1 = int(ymin / 1000 * h)
        x2 = int(xmax / 1000 * w)
        y2 = int(ymax / 1000 * h)
        draw.rectangle([x1, y1, x2, y2], outline=(255, 0, 0), width=3)
        label = f"{i}: {(b.get('label') or '')[:40]}"
        draw.text((x1 + 4, max(0, y1 - 16)), label, fill=(255, 0, 0), font=font)
    img.save(out_path)


async def run_one(url: str) -> dict:
    print(f"\n{'='*70}\n{url}\n{'='*70}")
    t0 = time.time()
    try:
        png, dom_info, vw, vh = await take_screenshot_and_dom(url)
    except Exception as exc:
        print(f"  fetch failed: {exc!r}")
        return {"url": url, "error": f"fetch: {exc}"}
    print(f"  screenshot: {len(png)} bytes, {time.time()-t0:.1f}s, html_len={dom_info['html_len']}")

    slug = _slug(url)
    raw_path = OUT_DIR / f"{slug}.png"
    raw_path.write_bytes(png)

    if not GEMINI_KEYS:
        print("  no GEMINI_API_KEYS set")
        return {"url": url, "error": "no keys"}

    # Try keys in order on rate-limit
    boxes: list[dict] = []
    used_key = None
    last_status = None
    last_body = None
    for i, key in enumerate(GEMINI_KEYS):
        t1 = time.time()
        status, body = call_gemini_bbox(png, key)
        last_status, last_body = status, body
        print(f"  gemini key#{i}: HTTP {status} ({time.time()-t1:.1f}s)")
        if status == 200:
            boxes = parse_bboxes(body)
            used_key = i
            break
        if status != 429:
            print(f"  non-429: {body[:200]}")
            break

    if not boxes:
        print(f"  no boxes parsed. last response (first 400 chars): {(last_body or '')[:400]}")
        return {"url": url, "error": f"no boxes (HTTP {last_status})"}

    print(f"  → {len(boxes)} bounding boxes from Gemini (key #{used_key})")
    for i, b in enumerate(boxes[:8], 1):
        bb = b.get("box_2d") or b.get("bbox") or b.get("bounding_box") or []
        label = (b.get("label") or "")[:60]
        print(f"    [{i}] {bb}  {label}")
    if len(boxes) > 8:
        print(f"    ... and {len(boxes)-8} more")

    annotated_path = OUT_DIR / f"{slug}_boxes.png"
    annotate(png, boxes, annotated_path)
    print(f"  annotated: {annotated_path}")

    return {"url": url, "n_boxes": len(boxes), "annotated": str(annotated_path)}


async def main():
    urls = sys.argv[1:] if len(sys.argv) > 1 else [
        "https://scholarshipdb.net/",
        "https://fulbright.org/",
    ]
    results = []
    for u in urls:
        results.append(await run_one(u))

    print(f"\n{'#'*70}\n# SUMMARY\n{'#'*70}")
    for r in results:
        if "error" in r:
            print(f"  {r['url']}: ERROR {r['error']}")
        else:
            print(f"  {r['url']}: {r['n_boxes']} boxes → {r['annotated']}")


asyncio.run(main())
