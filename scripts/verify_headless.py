"""Verify scraping works in headless mode.

Runs the full pipeline (wait_for_content -> repeating-card detection ->
spec-driven extraction) against a set of sites we previously verified in
headed mode. Uses pre-built specs so we don't burn LLM tokens just to
prove the browser works headless.

Run as:
    $env:CHROME_HEADLESS="true"; python scripts/verify_headless.py
"""
import asyncio, sys, os, pathlib, json
sys.path.insert(0, ".")
# Force line-buffered stdout so progress is visible when piped/redirected.
sys.stdout.reconfigure(line_buffering=True)

_envfile = pathlib.Path(".env.local")
if _envfile.exists():
    for line in _envfile.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

from worker.browser import make_chrome, start_browser
from worker.runner import _fetch_via_pydantic_spec
from worker.config import CHROME_HEADLESS, CHROME_BINARY

# Known-good specs from prior verification — used to prove the browser
# (not the LLM) gets the same data in headless mode it gets in headed mode.
CASES_FULL = [
    ("news.ycombinator.com", "Hacker News", {
        "card_selector": "tr.athing.submission",
        "fields": {
            "title": {"selector": "td.title span.titleline a", "attr": None},
            "url":   {"selector": "td.title span.titleline a", "attr": "href"},
        },
    }),
    ("books.toscrape.com", "Books to Scrape", {
        "card_selector": "li.col-xs-6.col-sm-4.col-md-3.col-lg-3",
        "fields": {
            "title": {"selector": "h3 a", "attr": None},
            "url":   {"selector": "h3 a", "attr": "href"},
        },
    }),
    ("quotes.toscrape.com", "Quotes to Scrape", {
        "card_selector": "div.quote",
        "fields": {
            "title":  {"selector": "span.text", "attr": None},
            "url":    {"selector": "a[href]", "attr": "href"},
            "author": {"selector": "small.author", "attr": None},
        },
    }),
    ("www.imdb.com/chart/top", "IMDb Top 250", {
        "card_selector": "li.ipc-metadata-list-summary-item",
        "fields": {
            "title":  {"selector": "h3.ipc-title__text", "attr": None},
            "url":    {"selector": "a.ipc-title-link-wrapper", "attr": "href"},
            "rating": {"selector": "span.ipc-rating-star--rating", "attr": None},
        },
    }),
    ("www.producthunt.com", "Product Hunt", {
        "card_selector": "section.group.relative.isolate",
        "fields": {
            "title":   {"selector": "a[href^='/products/']", "attr": None},
            "url":     {"selector": "a[href^='/products/']", "attr": "href"},
            "tagline": {"selector": "span.text-secondary", "attr": None},
        },
    }),
]

# Reverse for stress-test (proves failure is positional, not site-specific)
CASES = list(reversed(CASES_FULL)) if os.getenv("REVERSE") else CASES_FULL


async def main():
    print(f"Mode: {'HEADLESS' if CHROME_HEADLESS else 'HEADED'}")
    if CHROME_BINARY:
        print(f"Chrome binary: {CHROME_BINARY}")

    # Use a fresh Chrome per site so a single page crash can't poison the run.
    # Production runner.py will get the same treatment.
    results = []
    for domain, label, spec in CASES:
        print(f"\n=== {label} ({domain}) ===")
        # Per-site retry: a Chrome crash on attempt 1 gets a fresh browser.
        items = None
        last_error = None
        for attempt in range(2):
            try:
                browser, tab = await start_browser(retries=2)
            except Exception as exc:
                last_error = f"launch failed: {exc}"
                continue
            try:
                items = await _fetch_via_pydantic_spec(tab, domain, spec)
                break  # success
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt == 0:
                    print(f"  attempt 1 failed ({last_error}), retrying with fresh browser…")
            finally:
                try:
                    await browser.stop()
                except Exception:
                    pass

        if items is None:
            print(f"  ERROR: {last_error}")
            results.append((label, 0, "error"))
            await asyncio.sleep(2)  # cooldown before next site
            continue

        print(f"  Extracted: {len(items)} items")
        for it in items[:3]:
            preview = {
                k: (v[:80] + "..." if isinstance(v, str) and len(v) > 80 else v)
                for k, v in it.items()
                if k in ("id", "title", "url", "author", "rating", "tagline")
            }
            print(f"    {json.dumps(preview, ensure_ascii=False)}")
        status = "ok" if items else "empty"
        results.append((label, len(items), status))
        await asyncio.sleep(2)  # cooldown so previous Chrome's TCP sockets clear

    print("\n=== SUMMARY ===")
    ok_count = 0
    for label, n, status in results:
        flag = "OK " if status == "ok" else "FAIL"
        print(f"  [{flag}] {label}: {n} items")
        if status == "ok":
            ok_count += 1
    print(f"\n{ok_count}/{len(results)} sites scraped successfully "
          f"in {'headless' if CHROME_HEADLESS else 'headed'} mode.")


asyncio.run(main())
