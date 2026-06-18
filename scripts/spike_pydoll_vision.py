"""Use our existing pydoll browser (Cloudflare-bypassing) to render and screenshot,
then send to Gemini for bbox. Prove the lean architecture: keep pydoll, add vision.
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

from worker.browser import start_browser, navigate, wait_for_content

GEMINI_KEYS = [k.strip() for k in (os.environ.get("GEMINI_API_KEYS") or "").split(",") if k.strip()]
MODEL = "gemini-2.5-flash"
PROMPT = (
    "Look at this webpage screenshot. Identify the main repeating LISTING items "
    "that a user came to this page to browse — for example: scholarship cards, "
    "job postings, grant opportunities, course listings. \n\n"
    "Explicitly IGNORE: navigation menus, header links, footer links, "
    "filter widgets/sidebars, tag clouds, breadcrumbs, social-share buttons, "
    "Cloudflare or other security challenges.\n\n"
    "Return a JSON array (no prose, no markdown fences) of the bounding boxes "
    "for each listing item, in the format:\n"
    '[{"box_2d": [ymin, xmin, ymax, xmax], "label": "short description of this item"}]\n\n'
    "Coordinates must be normalized 0..1000. If there are no listings on the page, "
    "return []."
)

OUT_DIR = pathlib.Path("test-results/pydoll-vision")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _slug(url: str) -> str:
    return (url.replace("https://", "").replace("http://", "")
            .replace("/", "_").replace("?", "_").rstrip("_"))[:60]


async def screenshot_via_pydoll(url: str) -> bytes:
    browser, tab = await start_browser(retries=2)
    try:
        await navigate(tab, url)
        # Cloudflare clears in ~5-8s; wait for DOM stability.
        try:
            await wait_for_content(tab, min_elements=200, max_wait=20.0)
        except Exception:
            pass  # not fatal; just proceed and screenshot whatever we have
        # Extra grace for any final layout settling.
        await asyncio.sleep(2.0)
        # Scroll down so listings (typically below the search form) are in view.
        try:
            await tab.execute_script("window.scrollTo(0, 800)")
            await asyncio.sleep(1.0)
        except Exception:
            pass
        # CDP Page.captureScreenshot — pydoll exposes this on tab.
        # API varies between pydoll versions; try the common names.
        png_bytes = None
        # pydoll's take_screenshot requires a file path; write to tmp then read.
        tmp = OUT_DIR / f"_tmp_{int(time.time()*1000)}.png"
        for method_name in ("take_screenshot", "screenshot", "capture_screenshot"):
            fn = getattr(tab, method_name, None)
            if fn:
                try:
                    await fn(str(tmp))
                    if tmp.exists():
                        png_bytes = tmp.read_bytes()
                        try:
                            tmp.unlink()
                        except Exception:
                            pass
                    break
                except Exception as exc:
                    print(f"  {method_name} failed: {exc!r}")
        # Always also try a full-page CDP capture so we see content past viewport.
        # Skip if the page is enormous (>15000px tall) to avoid huge PNGs.
        try:
            metrics = await tab.execute_script(
                "return {h: document.body.scrollHeight, w: document.body.scrollWidth}",
                return_by_value=True,
            )
            mres = metrics.get("result", {}).get("result", {}).get("value", {}) or {}
            page_h = min(int(mres.get("h", 1600) or 1600), 4800)
            page_w = int(mres.get("w", 1280) or 1280)
            r = await tab._connection_handler.execute_command(
                {"method": "Page.captureScreenshot",
                 "params": {
                    "format": "png",
                    "captureBeyondViewport": True,
                    "clip": {"x": 0, "y": 0, "width": page_w, "height": page_h, "scale": 1},
                 }}
            )
            data_b64 = r.get("result", {}).get("data") if isinstance(r, dict) else None
            if data_b64:
                png_bytes = base64.b64decode(data_b64)
                print(f"  full-page CDP capture: {page_w}x{page_h}")
        except Exception as exc:
            print(f"  full-page CDP capture failed: {exc!r}")
        if not png_bytes:
            raise RuntimeError("could not capture screenshot via any known pydoll method")
        return png_bytes
    finally:
        try:
            await browser.stop()
        except Exception:
            pass


def call_gemini_bbox(png_bytes: bytes, key: str) -> tuple[int, str]:
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
    try:
        outer = json.loads(resp_text)
    except json.JSONDecodeError:
        return []
    parts = outer.get("candidates", [{}])[0].get("content", {}).get("parts", [])
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
        s, e = text.find("["), text.rfind("]")
        if s >= 0 and e > s:
            try:
                boxes = json.loads(text[s:e + 1])
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
        x1 = int(xmin / 1000 * w); y1 = int(ymin / 1000 * h)
        x2 = int(xmax / 1000 * w); y2 = int(ymax / 1000 * h)
        draw.rectangle([x1, y1, x2, y2], outline=(255, 0, 0), width=3)
        label = f"{i}: {(b.get('label') or '')[:40]}"
        draw.text((x1 + 4, max(0, y1 - 16)), label, fill=(255, 0, 0), font=font)
    img.save(out_path)


async def run_one(url: str) -> None:
    print(f"\n{'='*70}\n{url}\n{'='*70}")
    t0 = time.time()
    try:
        png = await screenshot_via_pydoll(url)
    except Exception as exc:
        print(f"  pydoll fetch failed: {exc!r}")
        return
    print(f"  screenshot: {len(png)} bytes, {time.time()-t0:.1f}s")

    slug = _slug(url)
    (OUT_DIR / f"{slug}.png").write_bytes(png)

    boxes: list[dict] = []
    last_status, last_body = None, None
    for i, key in enumerate(GEMINI_KEYS):
        status, body = call_gemini_bbox(png, key)
        last_status, last_body = status, body
        print(f"  gemini key#{i}: HTTP {status}")
        if status == 200:
            boxes = parse_bboxes(body)
            break
        if status != 429:
            print(f"  non-429: {body[:200]}")
            break

    if not boxes:
        print(f"  no boxes (HTTP {last_status})")
        return
    print(f"  → {len(boxes)} bounding boxes")
    for i, b in enumerate(boxes[:5], 1):
        bb = b.get("box_2d") or []
        print(f"    [{i}] {bb}  {(b.get('label') or '')[:60]}")
    if len(boxes) > 5:
        print(f"    ... and {len(boxes)-5} more")
    annotated = OUT_DIR / f"{slug}_boxes.png"
    annotate(png, boxes, annotated)
    print(f"  annotated: {annotated}")


async def main():
    urls = sys.argv[1:] if len(sys.argv) > 1 else ["https://www.findaphd.com/phds/"]
    for u in urls:
        await run_one(u)


asyncio.run(main())
