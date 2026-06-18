"""Run the Tier-2 scout's repeating-subtree detector against a URL and
print the top candidates with their counts and a short HTML sample. Lets
us see exactly what the detector finds (or doesn't) on a given page.

Usage:
    python scripts/diagnose_scout.py https://scholarshipdb.net/
    python scripts/diagnose_scout.py https://scholarshipdb.net/scholarships
"""
import asyncio
import json
import os
import pathlib
import sys

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

# Load .env.local so CHROME_BINARY etc. are picked up
_envfile = pathlib.Path(".env.local")
if _envfile.exists():
    for line in _envfile.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

from worker.browser import start_browser, navigate, wait_for_content
from worker.scout.pydantic_scout import _REPEATING_SUBTREE_JS, _sample_card_html


async def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "https://scholarshipdb.net/"
    print(f"Loading: {url}")

    browser, tab = await start_browser(retries=2)
    try:
        await navigate(tab, url)
        elements_after_settle = await wait_for_content(tab, max_wait=20.0)
        print(f"  DOM size after settle: {elements_after_settle} elements")

        # Total <a> count — sanity check that content actually loaded
        r = await tab.execute_script(
            "return document.querySelectorAll('a').length", return_by_value=True
        )
        anchor_count = r.get("result", {}).get("result", {}).get("value", "?")
        print(f"  <a> elements: {anchor_count}")

        title_r = await tab.execute_script(
            "return document.title", return_by_value=True
        )
        page_title = title_r.get("result", {}).get("result", {}).get("value", "")
        print(f"  document.title: {page_title!r}")

        # Run the same detector the scout uses
        raw = await tab.execute_script(_REPEATING_SUBTREE_JS, return_by_value=True)
        value = raw.get("result", {}).get("result", {}).get("value")
        if not value:
            print("\n  detector returned: <empty>")
            return
        try:
            cands = json.loads(value)
        except json.JSONDecodeError as e:
            print(f"\n  detector JSON parse error: {e}\n  raw: {value[:500]}")
            return

        if not cands:
            print("\n  detector found ZERO candidates — repeating-sibling threshold not met.")
            print("  (Detector requires class-fingerprint groups with ≥3 siblings, "
                  "or parent>tag patterns with ≥4.)")
        else:
            print(f"\n  detector found {len(cands)} candidate group(s):")
            for i, c in enumerate(cands[:8]):
                print(f"\n  [{i+1}] count={c['count']} kind={c.get('kind')} selector={c['selector']}")
                samples = await _sample_card_html(tab, c["selector"], n=1, max_len=500)
                if samples:
                    snippet = samples[0].replace("\n", " ").strip()[:480]
                    print(f"      sample: {snippet}…")
                else:
                    print("      sample: <none>")

        # Bonus: show a few semantic-looking links to manual-eyeball
        print("\n  --- top 20 anchor texts (for human inspection):")
        link_dump = await tab.execute_script(
            """
            const out = [];
            const seen = new Set();
            for (const a of document.querySelectorAll('a[href]')) {
              const text = (a.textContent || '').trim();
              if (!text || text.length < 3 || text.length > 80) continue;
              if (seen.has(text)) continue;
              seen.add(text);
              out.push({text, href: a.href.slice(0, 100)});
              if (out.length >= 20) break;
            }
            return JSON.stringify(out);
            """,
            return_by_value=True,
        )
        links_value = link_dump.get("result", {}).get("result", {}).get("value", "[]")
        try:
            links = json.loads(links_value)
        except json.JSONDecodeError:
            links = []
        for l in links:
            print(f"    - {l['text'][:70]:70} --&gt; {l['href']}")
    finally:
        try:
            await browser.stop()
        except Exception:
            pass


asyncio.run(main())
