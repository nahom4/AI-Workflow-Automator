"""Take a screenshot of a URL after our normal load+settle so we can see
exactly what pydoll renders. Saves to pics/diagnose-<safe-url>.png.
"""
import asyncio, base64, os, pathlib, re, sys

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


async def main():
    url = sys.argv[1]
    print(f"Loading: {url}")
    out_dir = pathlib.Path("pics"); out_dir.mkdir(exist_ok=True)
    safe = re.sub(r"[^a-z0-9]+", "_", url.lower()).strip("_")[:80]

    browser, tab = await start_browser(retries=2)
    try:
        await navigate(tab, url)
        await wait_for_content(tab, max_wait=20.0)
        await asyncio.sleep(3)

        # Get viewport screenshot first
        out_path = out_dir / f"diagnose_{safe}_viewport.png"
        await tab.take_screenshot(str(out_path))
        print(f"  saved viewport: {out_path}")

        # Then full page
        out_path_full = out_dir / f"diagnose_{safe}_fullpage.png"
        try:
            await tab.take_screenshot(str(out_path_full), full_page=True)
            print(f"  saved fullpage: {out_path_full}")
        except TypeError:
            # older pydoll API
            print("  (fullpage screenshot API not available)")

        # Also dump body innerText sample so we can see what the user reads
        r = await tab.execute_script(
            "return document.body.innerText.slice(0, 4000)",
            return_by_value=True,
        )
        text = r.get("result", {}).get("result", {}).get("value", "")
        text_path = out_dir / f"diagnose_{safe}_innerText.txt"
        text_path.write_text(text, encoding="utf-8")
        print(f"  saved innerText sample ({len(text)} chars): {text_path}")
        print("\n  --- first 2000 chars of innerText ---")
        print(text[:2000])
    finally:
        try:
            await browser.stop()
        except Exception:
            pass


asyncio.run(main())
