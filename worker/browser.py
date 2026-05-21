"""
Chrome factory using pydoll.

Server modes (set via env vars):
  - CHROME_HEADLESS=false (default): runs headed Chrome. On a Linux VPS this
    requires Xvfb (`xvfb-run -a python worker/main.py` or DISPLAY=:99).
  - CHROME_HEADLESS=true: runs `--headless=new`, the modern headless mode that
    is close to headed and significantly harder to fingerprint than legacy
    `--headless`. No Xvfb needed.

CHROME_BINARY can point to a specific Chrome/Chromium executable when the
default lookup fails (containers, multiple Chrome installs, etc.).

pydoll is imported lazily so that worker modules can be imported and tested
without pydoll installed (it's a VPS-only dependency).
"""

from __future__ import annotations

from worker.config import (
    CHROME_BINARY,
    CHROME_HEADLESS,
    CHROME_STEALTH,
    NAV_TIMEOUT,
    SETTLE_SECONDS,
)


async def start_browser(retries: int = 2):
    """Build a Chrome via make_chrome() and start it with launch retries.

    pydoll picks a random CDP port from 9223–9322; a single-port collision
    or a slow Chrome boot can throw ConnectionRefusedError. Retrying once
    or twice with a fresh Chrome instance handles both reliably.

    Returns (browser, tab).
    """
    import asyncio

    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        browser = make_chrome()
        try:
            tab = await asyncio.wait_for(browser.start(), timeout=45)
            return browser, tab
        except Exception as exc:
            last_exc = exc
            try:
                await browser.stop()
            except Exception:
                pass
            if attempt < retries:
                await asyncio.sleep(2 + attempt)  # 2s, then 3s
                continue
            raise RuntimeError(
                f"Chrome failed to start after {retries + 1} attempts: {exc}"
            ) from last_exc
    raise RuntimeError("unreachable")


def make_chrome():
    """Return a Chrome instance with anti-detection + server-mode flags."""
    from pydoll.browser.chromium import Chrome  # lazy — not needed in test env
    from pydoll.browser.options import ChromiumOptions

    opts = ChromiumOptions()
    if CHROME_BINARY:
        opts.binary_location = CHROME_BINARY

    args: list[str] = []
    if CHROME_STEALTH:
        args += [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--window-size=1280,900",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--no-proxy-server",  # bypass system SOCKS proxy in dev
        ]
    if CHROME_HEADLESS:
        # --headless=new is the modern headless implementation (Chrome 109+)
        # that runs the same rendering pipeline as headed Chrome. Avoid the
        # legacy --headless which is a separate, easily-detected codepath.
        args += [
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--mute-audio",
            "--disable-extensions",
            # Use a real user-agent string — Chrome's headless UA includes the
            # word "HeadlessChrome" which any half-decent bot detector matches.
            "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        ]

    for arg in args:
        try:
            opts.add_argument(arg)
        except Exception:
            pass
    return Chrome(options=opts)


async def navigate(tab, url: str, retries: int = 2) -> None:
    """Navigate with retries; one slow page shouldn't kill the whole run.

    Each attempt is wrapped in an asyncio timeout so that a dead Chrome
    process (CDP responses never coming) can't hang the worker forever.
    """
    import asyncio

    # Convert NAV_TIMEOUT (ms) to a hard asyncio budget in seconds, plus 5s slack.
    hard_timeout = (NAV_TIMEOUT / 1000.0) + 5

    for attempt in range(retries + 1):
        try:
            await asyncio.wait_for(
                tab.go_to(url, timeout=NAV_TIMEOUT),
                timeout=hard_timeout,
            )
            return
        except asyncio.TimeoutError as exc:
            if attempt < retries:
                await asyncio.sleep(5)
            else:
                raise RuntimeError(
                    f"Navigation hard-timed-out after {retries + 1} attempts: {exc}"
                ) from exc
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


async def wait_for_content(
    tab,
    *,
    min_elements: int = 50,
    stability_seconds: float = 1.5,
    poll_interval: float = 0.5,
    max_wait: float = 25.0,
) -> int:
    """Wait until the DOM stops growing significantly.

    Polls `document.querySelectorAll('*').length` every `poll_interval`s.
    Returns once the count has not changed by more than 1% for
    `stability_seconds`, or when `max_wait` is reached. Always waits at least
    `min_elements`-many before considering the page populated.

    Returns the final element count (useful for diagnostics).
    """
    import asyncio
    import time

    start = time.monotonic()
    last_count = -1
    stable_since: float | None = None

    while time.monotonic() - start < max_wait:
        try:
            r = await asyncio.wait_for(
                tab.execute_script(
                    "return document.querySelectorAll('*').length",
                    return_by_value=True,
                ),
                timeout=5.0,
            )
            count = int(r.get("result", {}).get("result", {}).get("value", 0) or 0)
        except asyncio.TimeoutError:
            # CDP unresponsive — assume Chrome is wedged and bail out
            raise RuntimeError("wait_for_content: tab.execute_script timed out (Chrome wedged?)")
        except Exception:
            count = 0

        # Page is being torn down / reloaded — reset stability tracking
        if count < min_elements:
            stable_since = None
            last_count = count
            await asyncio.sleep(poll_interval)
            continue

        # Count delta as a fraction of last_count; treat <=1% as stable
        if last_count > 0:
            delta = abs(count - last_count) / max(last_count, 1)
        else:
            delta = 1.0

        if delta < 0.01 and count >= min_elements:
            if stable_since is None:
                stable_since = time.monotonic()
            elif time.monotonic() - stable_since >= stability_seconds:
                return count
        else:
            stable_since = None

        last_count = count
        await asyncio.sleep(poll_interval)

    return last_count if last_count > 0 else 0
