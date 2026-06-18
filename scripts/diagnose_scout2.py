"""Variant of diagnose_scout that scrolls + waits longer + looks for any
anchor whose href pattern repeats (likely detail-page links of cards).
"""
import asyncio, json, os, pathlib, sys, re

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

_envfile = pathlib.Path(".env.local")
if _envfile.exists():
    for line in _envfile.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

from worker.browser import start_browser, navigate, wait_for_content
from worker.scout.pydantic_scout import _REPEATING_SUBTREE_JS


async def main():
    url = sys.argv[1]
    print(f"Loading: {url}")
    browser, tab = await start_browser(retries=2)
    try:
        await navigate(tab, url)
        n = await wait_for_content(tab, max_wait=20.0)
        print(f"  after settle: {n} elements")

        # Scroll to trigger lazy-load
        await tab.execute_script("window.scrollTo(0, document.body.scrollHeight)", return_by_value=True)
        await asyncio.sleep(2)
        await tab.execute_script("window.scrollTo(0, document.body.scrollHeight)", return_by_value=True)
        await asyncio.sleep(3)

        r = await tab.execute_script("return document.querySelectorAll('*').length", return_by_value=True)
        n2 = r["result"]["result"]["value"]
        print(f"  after scroll x2 + 5s: {n2} elements (delta {n2 - n})")

        # Anchor href pattern analysis — group anchors by URL "shape"
        js_patterns = """
        const groups = {};
        for (const a of document.querySelectorAll('a[href]')) {
          const href = a.href;
          // Take just the path, strip trailing IDs / numbers / slugs
          const path = href.replace(/^https?:\\/\\/[^/]+/, '');
          // Replace alphanum tokens >=4 chars between slashes with *
          const shape = path
            .replace(/\\?.*$/, '')
            .replace(/\\/[A-Za-z0-9_-]{4,}/g, '/*')
            .replace(/^\\/[A-Za-z0-9_-]{4,}$/, '/*');
          (groups[shape] = groups[shape] || []).push(href);
        }
        const summary = Object.entries(groups)
          .filter(([_, v]) => v.length >= 3)
          .sort((a,b) => b[1].length - a[1].length)
          .slice(0, 15)
          .map(([k, v]) => ({shape: k, count: v.length, sample: v.slice(0, 3)}));
        return JSON.stringify(summary);
        """
        rr = await tab.execute_script(js_patterns, return_by_value=True)
        patterns = json.loads(rr["result"]["result"]["value"] or "[]")
        print("\n--- anchor-shape groups (count >= 3):")
        for p in patterns:
            print(f"  count={p['count']} shape={p['shape']}")
            for s in p["sample"]:
                print(f"    e.g. {s[:120]}")

        # Re-run repeating-subtree detector now that the page is fully scrolled
        raw = await tab.execute_script(_REPEATING_SUBTREE_JS, return_by_value=True)
        cands = json.loads(raw["result"]["result"]["value"] or "[]")
        print(f"\n--- detector after scroll: {len(cands)} candidate(s)")
        for c in cands[:8]:
            print(f"  count={c['count']} kind={c.get('kind')} sel={c['selector'][:100]}")
    finally:
        try:
            await browser.stop()
        except Exception:
            pass


asyncio.run(main())
