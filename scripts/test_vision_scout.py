"""End-to-end test of the new vision_scout path.

  python scripts/test_vision_scout.py <url> [vertical]

Spins up a real pydoll browser, runs vision_scout.scout(), and if a spec comes
back, runs the existing _extract_pydantic_at_url against it to confirm the
selector returns real cards. Prints the spec JSON + first 5 extracted items.
"""
import asyncio
import json
import os
import pathlib
import sys

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)

# Load .env.local
_envfile = pathlib.Path(".env.local")
if _envfile.exists():
    for line in _envfile.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

from worker.browser import start_browser
from worker.scout import vision_scout
from worker.runner import _extract_pydantic_at_url


async def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://scholarshipdb.net/scholarships-in-United-States"
    vertical = sys.argv[2] if len(sys.argv) > 2 else "scholarships"

    print(f"vision_scout test\n  url:      {url}\n  vertical: {vertical}\n")

    browser, tab = await start_browser(retries=2)
    try:
        spec = await vision_scout.scout(tab, url=url, vertical=vertical)
        print("=== spec ===")
        print(json.dumps(spec, indent=2) if spec else "(none)")
        if not spec:
            print("\nVision scout returned no spec — page has no listings, vision unavailable, "
                  "or DOM mapping couldn't lock onto a selector. This is the correct outcome "
                  "for marketing pages and search forms.")
            return

        print("\n=== extraction sample ===")
        items = await _extract_pydantic_at_url(tab, url, spec)
        print(f"got {len(items)} items, first 5:\n")
        for i, it in enumerate(items[:5], 1):
            print(f"  [{i}] title: {(it.get('title') or '')[:80]}")
            print(f"      url:   {it.get('url') or ''}")
    finally:
        try:
            await browser.stop()
        except Exception:
            pass


asyncio.run(main())
