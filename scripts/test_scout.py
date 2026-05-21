"""Quick test: run the 3-tier scout against a real site.

Usage:
    python scripts/test_scout.py <url> [vertical]

Set SCOUT_DEBUG=1 to print HAR/candidate counts and the LLM raw response.
"""
import asyncio, sys, os, pathlib, json
sys.path.insert(0, ".")

# Auto-load .env.local so GROQ_API_KEY is available without manual exports.
_envfile = pathlib.Path(".env.local")
if _envfile.exists():
    for line in _envfile.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

from worker.browser import make_chrome, navigate, settle
from worker.scout import network_sniff, pydantic_scout

URL = sys.argv[1] if len(sys.argv) > 1 else "https://weworkremotely.com"
VERTICAL = sys.argv[2] if len(sys.argv) > 2 else "jobs"
DEBUG = os.getenv("SCOUT_DEBUG", "0") == "1"


async def main():
    print(f"Scouting {URL} (vertical={VERTICAL}) ...")
    browser = make_chrome()
    tab = await browser.start()
    try:
        if DEBUG:
            from pydoll.protocol.network.types import ResourceType
            async with tab.request.record(
                resource_types=[ResourceType.XHR, ResourceType.FETCH]
            ) as capture:
                await navigate(tab, URL)
                await settle(tab, 4)
            json_responses = network_sniff._extract_json_responses(capture.entries)
            print(f"[debug] HAR entries: {len(capture.entries)} | JSON-bodied: {len(json_responses)}")
            for r in json_responses[:5]:
                print(f"  {r['url'][:90]}")

        tier1 = await network_sniff.scout(tab, url=URL, vertical=VERTICAL)
        if tier1:
            print("Tier-1 (API) spec found:")
            print(json.dumps(tier1, indent=2))
            return

        print("No Tier-1 API found - trying Tier-2 CSS scout ...")
        if DEBUG:
            await navigate(tab, URL)
            await settle(tab, 3)
            cands = await pydantic_scout._find_repeating_subtrees(tab)
            print(f"[debug] Repeating candidates: {len(cands)}")
            for c in cands[:5]:
                print(f"  count={c['count']:3d} kind={c['kind']:5s} sel={c['selector']}")

        tier2 = await pydantic_scout.scout(tab, url=URL, vertical=VERTICAL)
        if tier2:
            print("Tier-2 spec found:")
            print(json.dumps(tier2, indent=2))
        else:
            print("No spec found by either tier.")
    finally:
        try:
            await browser.stop()
        except Exception:
            pass


asyncio.run(main())
