"""Capture network traffic for a URL and print all XHR/Fetch responses
that contain JSON. This is what Tier-1 sniff sees — we want to confirm
whether scholarshipdb has a backing API at all.
"""
import asyncio, json, os, pathlib, sys

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
from pydoll.protocol.network.types import ResourceType


async def main():
    url = sys.argv[1]
    print(f"Capturing traffic for: {url}")
    browser, tab = await start_browser(retries=2)
    try:
        async with tab.request.record(
            resource_types=[ResourceType.XHR, ResourceType.FETCH]
        ) as capture:
            await navigate(tab, url)
            await wait_for_content(tab, max_wait=20.0)
            # Scroll to trigger any deferred fetches
            await tab.execute_script(
                "window.scrollTo(0, document.body.scrollHeight)", return_by_value=True
            )
            await asyncio.sleep(3)

        entries = capture.entries
        print(f"\ncaptured {len(entries)} XHR/Fetch entries")
        for e in entries:
            req = e.get("request", {})
            resp = e.get("response", {})
            url2 = req.get("url", "")
            method = req.get("method", "")
            status = resp.get("status", 0)
            ct = ""
            for h in resp.get("headers", []):
                if (h.get("name") or "").lower() == "content-type":
                    ct = h.get("value", "")
                    break
            size = (resp.get("content") or {}).get("size", 0)
            body = (resp.get("content") or {}).get("text", "") or ""
            print(f"  {method} {status} {ct[:30]:30} {size:7}  {url2[:120]}")
            if "json" in ct.lower() and body:
                try:
                    j = json.loads(body)
                    print(f"    keys: {list(j)[:10] if isinstance(j, dict) else f'list of {len(j)}'}")
                    if isinstance(j, dict):
                        for k, v in list(j.items())[:5]:
                            if isinstance(v, list) and v:
                                print(f"    {k}: list[{len(v)}], item0 keys = {list(v[0])[:8] if isinstance(v[0], dict) else type(v[0])}")
                except Exception:
                    pass
    finally:
        try:
            await browser.stop()
        except Exception:
            pass


asyncio.run(main())
