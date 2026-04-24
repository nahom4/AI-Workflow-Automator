"""
Chrome factory using pydoll. Runs in headed mode under Xvfb on the VPS —
headless Chrome is detectable by Cloudflare; headed + virtual display is not.

pydoll is imported lazily so that worker modules can be imported and tested
without pydoll installed (it's a VPS-only dependency).
"""

from __future__ import annotations

from worker.config import CHROME_STEALTH, NAV_TIMEOUT, SETTLE_SECONDS


def make_chrome():
    """Return a Chrome instance with optional anti-detection flags."""
    from pydoll.browser.chrome import Chrome  # lazy — not needed in test env
    from pydoll.browser.options import ChromiumOptions

    if not CHROME_STEALTH:
        return Chrome()
    opts = ChromiumOptions()
    for arg in (
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--window-size=1280,900",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ):
        try:
            opts.add_argument(arg)
        except Exception:
            pass
    return Chrome(options=opts)


async def navigate(tab, url: str, retries: int = 2) -> None:
    """Navigate with retries; one slow page shouldn't kill the whole run."""
    import asyncio

    for attempt in range(retries + 1):
        try:
            await tab.go_to(url, timeout=NAV_TIMEOUT)
            return
        except Exception as exc:
            if attempt < retries:
                await asyncio.sleep(5)
            else:
                raise RuntimeError(
                    f"Navigation failed after {retries + 1} attempts: {exc}"
                ) from exc


async def settle(tab, seconds: float | None = None) -> None:
    """Wait for dynamic content to hydrate after initial page load."""
    import asyncio

    await asyncio.sleep(seconds if seconds is not None else SETTLE_SECONDS)
