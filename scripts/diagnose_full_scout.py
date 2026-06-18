"""Run pydantic_scout end-to-end on a URL with debug output enabled."""
import asyncio, os, pathlib, sys

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)

_envfile = pathlib.Path(".env.local")
if _envfile.exists():
    for line in _envfile.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

os.environ["SCOUT_DEBUG"] = "1"

from worker.browser import start_browser
from worker.scout import pydantic_scout


async def main():
    url = sys.argv[1]
    vertical = sys.argv[2] if len(sys.argv) > 2 else "scholarships"
    browser, tab = await start_browser(retries=2)
    try:
        spec = await pydantic_scout.scout(tab, url=url, vertical=vertical)
        print(f"\n=== final spec ===\n{spec}")
    finally:
        try:
            await browser.stop()
        except Exception:
            pass


asyncio.run(main())
