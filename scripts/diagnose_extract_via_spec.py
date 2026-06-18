"""Re-run extraction with the saved spec and dump first 5 items so we can
see what kind of 'items' the worker is grabbing."""
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

from worker.browser import start_browser
from worker.runner import _extract_pydantic_at_url


async def main():
    domain = sys.argv[1]
    import sqlite3
    c = sqlite3.connect("data/automations.db")
    spec_row = c.execute("SELECT spec_json, tier FROM site_specs WHERE domain=?", [domain]).fetchone()
    if not spec_row:
        print(f"no saved spec for {domain}")
        return
    spec = json.loads(spec_row[0])
    print(f"spec card_selector: {spec.get('card_selector')}")
    print(f"entry_urls: {spec.get('entry_urls')}\n")

    browser, tab = await start_browser(retries=2)
    try:
        for url in spec.get("entry_urls") or [spec.get("entry_url")]:
            print(f"\n=== {url} ===")
            try:
                items = await _extract_pydantic_at_url(tab, url, spec)
            except Exception as exc:
                print(f"  ERROR: {exc}")
                continue
            print(f"  got {len(items)} items, first 5:")
            for it in items[:5]:
                print(f"    {it}")
    finally:
        try:
            await browser.stop()
        except Exception:
            pass


asyncio.run(main())
