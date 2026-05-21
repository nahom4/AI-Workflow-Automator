"""Debug: show actual resource types and which entries have JSON bodies."""
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
        await settle(tab, 4)

        logs = await tab.get_network_logs()
        print(f"Total log entries: {len(logs)}")

        # Count by method
        from collections import Counter
        methods = Counter(e.get("method") for e in logs)
        print("Methods:", dict(methods))

        # Show resource types from responseReceived events
        types = Counter(
            e.get("params", {}).get("type", "?")
            for e in logs if e.get("method") == "Network.responseReceived"
        )
        print("Resource types (responseReceived):", dict(types))

        # Show a few XHR/Fetch entries
        xhr_entries = [
            e for e in logs
            if e.get("method") == "Network.responseReceived"
            and e.get("params", {}).get("type") in ("XHR", "Fetch")
        ]
        print(f"\nXHR/Fetch responses: {len(xhr_entries)}")
        for e in xhr_entries[:5]:
            p = e.get("params", {})
            url = p.get("response", {}).get("url", p.get("request", {}).get("url", "?"))
            rid = p.get("requestId", "?")
            print(f"  [{p.get('type')}] {url[:80]} (id={rid})")
            try:
                body = await tab.get_network_response_body(rid)
                print(f"    body size={len(body)}, is_json={body.strip().startswith(('{','['))}")
            except Exception as exc:
                print(f"    body error: {exc}")

    finally:
        try:
            await browser.stop()
        except Exception:
            pass


asyncio.run(main())
