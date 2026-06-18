"""Test #3: DOM heuristic that ranks repeating subtrees by visual area, not raw count.

The kernel insight from the research: tag-clouds beat real-cards on naive count.
Better signal is **mean child bounding-box area × log(count)**, with count clamped
to [5, 50], plus a bonus for being in the visual center column.

This script enumerates repeating subtrees on the live page, scores them under both
the OLD heuristic (raw count) and the NEW heuristic (visual-area weighted), and
shows the top 5 of each so we can compare.

Run: python scripts/spike_dom_heuristic.py [url ...]
"""
import asyncio
import json
import os
import pathlib
import sys

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

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

# JS that walks the DOM, finds containers whose direct children share a tag/class
# fingerprint, and reports each candidate with visual metrics.
DETECTOR_JS = r"""
(() => {
  const VW = window.innerWidth;
  const results = [];

  // Tag-only fingerprint — children with slightly different class lists still
  // group together (e.g. tr.job vs tr.job.placeholder, or article vs article.featured).
  function fingerprint(el) {
    return el.tagName.toLowerCase();
  }

  function pathTo(el) {
    const parts = [];
    let cur = el;
    while (cur && cur.nodeType === 1 && parts.length < 6) {
      let part = cur.tagName.toLowerCase();
      if (cur.id) { part += '#' + cur.id; parts.unshift(part); break; }
      if (cur.className && typeof cur.className === 'string') {
        const c = cur.className.trim().split(/\s+/).filter(Boolean).slice(0, 2).join('.');
        if (c) part += '.' + c;
      }
      parts.unshift(part);
      cur = cur.parentElement;
    }
    return parts.join(' > ');
  }

  // Walk every element; for each, look at its direct children and group by
  // fingerprint. If any group has >= 3 children, treat as a repeating-subtree
  // candidate.
  const elems = document.querySelectorAll('*');
  for (const parent of elems) {
    if (!parent.children || parent.children.length < 3) continue;
    const groups = new Map();
    for (const c of parent.children) {
      const fp = fingerprint(c);
      if (!groups.has(fp)) groups.set(fp, []);
      groups.get(fp).push(c);
    }
    for (const [fp, kids] of groups) {
      if (kids.length < 3) continue;

      // Compute visual metrics for the children.
      let totalArea = 0;
      let textTotal = 0;
      let visibleCount = 0;
      let cxSum = 0;
      let widths = [];
      let heights = [];
      const kidBoxes = [];
      for (const k of kids) {
        const r = k.getBoundingClientRect();
        if (r.width <= 0 || r.height <= 0) continue;
        visibleCount++;
        const area = r.width * r.height;
        totalArea += area;
        cxSum += (r.left + r.width / 2);
        widths.push(r.width);
        heights.push(r.height);
        const txt = (k.innerText || '').trim();
        textTotal += txt.length;
        kidBoxes.push({ x: r.left, y: r.top, w: r.width, h: r.height, t: txt.slice(0, 80) });
      }
      // Require count >= 5 — excludes body-level layout containers.
      // Upper bound left to log-clamp in scoring (diminishing returns past ~50)
      // so legit big tables (200+ jobs) still survive as candidates.
      if (visibleCount < 5) continue;

      const meanArea = totalArea / visibleCount;
      const meanText = textTotal / visibleCount;
      const meanCx = cxSum / visibleCount;
      // Skip absurdly large items — body-level sections, hero banners.
      // 800k px² ≈ 1000×800. Real cards top out around 300×400 = 120k.
      if (meanArea > 800000) continue;

      // Width homogeneity: real listings have very similar widths;
      // body-level layouts have widely varying widths.
      const meanW = widths.reduce((a, b) => a + b, 0) / widths.length;
      const wVar = widths.reduce((a, b) => a + (b - meanW) ** 2, 0) / widths.length;
      const wCv = Math.sqrt(wVar) / Math.max(1, meanW);  // coeff of variation 0..1+
      // Reject candidates where children differ by >40% in width.
      if (wCv > 0.4) continue;

      // distance of column center from viewport center, normalized 0..1
      const centerOffset = Math.abs(meanCx - VW / 2) / (VW / 2);

      results.push({
        selector: pathTo(parent) + ' > ' + fp,
        parent_path: pathTo(parent),
        fingerprint: fp,
        count: visibleCount,
        mean_area: Math.round(meanArea),
        mean_text_len: Math.round(meanText),
        center_offset: Number(centerOffset.toFixed(3)),
        width_cv: Number(wCv.toFixed(3)),
        first_three_text: kidBoxes.slice(0, 3).map(b => b.t),
      });
    }
  }
  return results;
})();
"""


def score_old(c: dict) -> float:
    """Naive: raw count."""
    return float(c["count"])


def score_new(c: dict) -> float:
    """Visual area × log(count clamped 5..50) × center column bonus.

    - mean_area is the strongest signal: real cards are big, tag-clouds are tiny
    - count clamped: 100-item filter widgets shouldn't outrank 12 real cards
    - text length: filters/nav are short, real listings have descriptions
    - center bonus: real listings are in main column, sidebars are off-center
    """
    import math
    n = max(5, min(50, c["count"]))
    area = max(1, c["mean_area"])
    text = max(1, c["mean_text_len"])
    center_bonus = 1.0 + (1.0 - c["center_offset"]) * 0.5  # 1.0..1.5
    return math.log(n) * area * math.log(text + 1) * center_bonus


async def run_one(url: str) -> None:
    print(f"\n{'='*80}\n{url}\n{'='*80}")
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 1600})
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Wait longer + scroll to trigger lazy load
            await page.wait_for_timeout(3500)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
            await page.wait_for_timeout(1500)
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(500)
            candidates = await page.evaluate(DETECTOR_JS)
        finally:
            await browser.close()

    if not candidates:
        print("  detector returned no candidates")
        return

    print(f"  {len(candidates)} repeating-subtree candidates")

    old_top = sorted(candidates, key=score_old, reverse=True)[:5]
    new_top = sorted(candidates, key=score_new, reverse=True)[:5]

    def _fmt(c, score_fn):
        return (f"score={score_fn(c):>10.0f}  count={c['count']:>3}  "
                f"area={c['mean_area']:>7}  text={c['mean_text_len']:>4}  "
                f"cx_off={c['center_offset']:.2f}  wCv={c.get('width_cv',0):.2f}  "
                f"sel={c['selector'][:80]}")

    print("\n  --- OLD heuristic (raw count) top 5 ---")
    for c in old_top:
        print("   " + _fmt(c, score_old))
        for t in c["first_three_text"]:
            print(f"      · {t[:90]}")

    print("\n  --- NEW heuristic (area × log(count) × center) top 5 ---")
    for c in new_top:
        print("   " + _fmt(c, score_new))
        for t in c["first_three_text"]:
            print(f"      · {t[:90]}")


async def main():
    urls = sys.argv[1:] if len(sys.argv) > 1 else [
        "https://scholarshipdb.net/",
        "https://scholarshipdb.net/scholarships-in-United-States",
        "https://remoteok.com/",
    ]
    for u in urls:
        try:
            await run_one(u)
        except Exception as exc:
            print(f"  ERROR on {u}: {exc!r}")


asyncio.run(main())
