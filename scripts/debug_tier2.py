"""Debug Tier-2 CSS scout and check what requestWillBeSent types we capture."""
import asyncio, sys, json
sys.path.insert(0, ".")

from worker.browser import make_chrome, navigate, settle

URL = sys.argv[1] if len(sys.argv) > 1 else "https://jobicy.com"


async def main():
    browser = make_chrome()
    tab = await browser.start()
    try:
        await tab.enable_network_events()
        await navigate(tab, URL)
        await settle(tab, 5)

        logs = await tab.get_network_logs()

        # Show resource types from requestWillBeSent
        from collections import Counter
        types = Counter(
            e.get("params", {}).get("type", "?")
            for e in logs if e.get("method") == "Network.requestWillBeSent"
        )
        print("requestWillBeSent types:", dict(types))

        # Try fetching bodies for ALL requests (not just XHR/Fetch)
        print("\nTrying get_network_response_body on first 5 requests:")
        sent = [e for e in logs if e.get("method") == "Network.requestWillBeSent"]
        for e in sent[:5]:
            p = e.get("params", {})
            rid = p.get("requestId", "")
            url = p.get("request", {}).get("url", "?")
            rtype = p.get("type", "?")
            try:
                body = await tab.get_network_response_body(rid)
                print(f"  [{rtype}] {url[:60]} -> body len={len(body)}")
            except Exception as exc:
                print(f"  [{rtype}] {url[:60]} -> ERROR: {exc}")

        # Run Tier-2 scout manually
        print("\n--- Tier-2 CSS scout ---")
        from worker.scout.pydantic_scout import scout as tier2_scout
        # Navigate fresh for Tier-2
        await navigate(tab, URL)
        await settle(tab, 3)
        result = await tier2_scout(tab, url=URL, vertical="jobs")
        print("Tier-2 result:", result)

    finally:
        try:
            await browser.stop()
        except Exception:
            pass


asyncio.run(main())
