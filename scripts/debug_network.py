"""Debug: show what pydoll captures on a page load."""
import asyncio, sys, json
sys.path.insert(0, ".")

from worker.browser import make_chrome, navigate, settle

URL = sys.argv[1] if len(sys.argv) > 1 else "https://jobicy.com"


async def main():
    print(f"Opening {URL} ...")
    browser = make_chrome()
    tab = await browser.start()
    try:
        # Check what network-related methods exist on the tab
        methods = [m for m in dir(tab) if "network" in m.lower() or "log" in m.lower() or "request" in m.lower()]
        print("Tab network methods:", methods)

        await tab.enable_network_events()
        await navigate(tab, URL)
        await settle(tab, 4)

        logs = await tab.get_network_logs()
        print(f"\nget_network_logs() returned {len(logs)} entries")
        for log in logs[:3]:
            print(" ", json.dumps(log)[:200])
    finally:
        try:
            await browser.stop()
        except Exception:
            pass


asyncio.run(main())
