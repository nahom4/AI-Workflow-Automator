# Scraping Layer — Broken Root Cause Report

## Context

The application's most important feature is automated lead generation: for each source URL the user adds, a 3-tier scout discovers **how** to scrape it, then a runner executes that spec on a schedule. Without working scouting, every new source (other than the hardcoded remoteok adapter) silently produces zero leads.

---

## Architecture (What Should Happen)

```
User adds source URL (e.g. https://jobs.greenhouse.io/anthropic)
        │
        ▼
runner.py: _fetch_items()
        │
        ├── Known adapter? (remoteok, upwork) → use direct adapter
        │
        └── Unknown domain → run 3-tier scout
                │
                ├── Tier 1: network_sniff.scout()
                │     Capture XHR/Fetch JSON responses during page load
                │     Ask Groq: "which endpoint carries jobs data?"
                │     → Returns { endpoint, item_path, fields } or None
                │
                ├── Tier 2: pydantic_scout.scout()  (if Tier 1 fails)
                │     Find repeating DOM elements via JS
                │     Sample 3 card HTML snippets
                │     Ask Groq: "give me CSS selectors for title/url/id"
                │     → Returns { card_selector, fields } or None
                │
                └── Tier 3: vision (not yet implemented)

Scout result is saved to site_specs DB table.
On next run, the confirmed spec is used to extract leads.
```

---

## The Problem

**Both Tier-1 and Tier-2 return `None` for every site.** The entire scout layer produces nothing, so unknown sources always log `"scout found nothing — skipping this source"` and generate zero leads.

---

## Root Cause: Tier-1 (Critical)

**File:** `worker/scout/network_sniff.py`

The code does this:

```python
await tab.enable_network_events()
await navigate(tab, url)
await settle(tab, 3)
logs = await tab.get_network_logs()      # ← the bug is here

for log in logs:
    resource_type = params.get("type", "")
    if resource_type and resource_type not in _FETCH_TYPES:  # _FETCH_TYPES = {"XHR", "Fetch"}
        continue
    body = await tab.get_network_response_body(request_id)
```

### What `get_network_logs()` Actually Returns

`get_network_logs()` reads from `self._connection_handler.network_logs` which is a list populated only by `Network.requestWillBeSent` and `Network.requestWillBeSentExtraInfoEvent` CDP events. These are **outgoing request events only** — they fire the moment Chrome decides to make a request, *before any response exists*.

**There are no `Network.responseReceived` events in this list.** There are no response bodies. Every call to `get_network_response_body()` either throws or returns an empty string because the request IDs come from request-sent events, not response events, and Chrome's response buffer has already been freed by the time we ask.

This was confirmed by running `scripts/debug_network2.py` against `https://jobicy.com`:
- `responseReceived` count in `get_network_logs()`: **0**
- All `get_network_response_body()` calls: **ERROR**

### The Fix

Pydoll v2.22.1 ships a proper HAR recorder (`HarRecorder`) that uses `tab.on()` to register callbacks for `Network.responseReceived` and `Network.loadingFinished` **before navigation**, correlates events by `requestId`, and fetches response bodies at `loadingFinished` time when the buffer is guaranteed populated.

The public API is `tab.request.record()` — an async context manager:

```python
from pydoll.protocol.network.types import ResourceType

async with tab.request.record(resource_types=[ResourceType.XHR, ResourceType.FETCH]) as capture:
    await navigate(tab, url)
    await settle(tab, 4)

# After the block, capture.entries has full HAR 1.2 entries with response bodies
for entry in capture.entries:
    url   = entry['request']['url']
    body  = entry['response']['content'].get('text', '')
    # parse body as JSON, summarise, send to Groq
```

**`network_sniff.py` needs to be rewritten around this API.** The `_collect_json_responses()` function and everything that calls `get_network_logs()` must be replaced.

---

## Root Cause: Tier-2 (Secondary)

**File:** `worker/scout/pydantic_scout.py`

### Problem 1 — `execute_script` return value (confirmed correct)

The code accesses `card_candidates.get("result", {}).get("result", {}).get("value", "[]")`.
This matches how pydoll's `_execute_command` wraps CDP responses:
`result["result"]["result"]["value"]` — **this part is correct**, confirmed by reading `request.py` which uses the same pattern.

### Problem 2 — JavaScript threshold too strict

`_REPEATING_SUBTREE_JS` only yields candidates when **both**:
- A parent has ≥ 5 children (`if (siblings.length < 5) return`)
- The same `tagName.class1.class2` pattern appears ≥ 5 times globally

Many job listing pages have 10–20 cards but a parent with exactly 4 visible siblings, or use slightly varied class sets. The threshold should be lowered to 3.

### Problem 3 — CSS selector uses uppercase tag names

The JS builds selectors like `ARTICLE.job-card` (HTML `tagName` is always uppercase). CSS selectors are case-insensitive for HTML tags so this technically works, but it's worth converting to lowercase for readability and to avoid any edge cases.

### Problem 4 — Tier-2 never ran cleanly

Because Tier-1 always ran first and always navigated the page (and consumed settle time), Tier-2 was called with the browser in an inconsistent state. Once Tier-1 is fixed with the HAR context manager, Tier-2 will navigate cleanly.

### The Fix

Lower the threshold in `_REPEATING_SUBTREE_JS` from `>= 5` to `>= 3` in both the `siblings.length` check and the `filter` clause. Also lowercase the tag in the generated selector.

---

## What Is Working

- **Chrome launches correctly** (`pydoll.browser.chromium.Chrome` + `--no-proxy-server` flag)
- **Navigation works** (`tab.go_to()` loads pages)
- **JS execution works** (`tab.execute_script()` runs code and returns results)
- **`tab.request.record()`** exists in pydoll v2.22.1 and is the correct API (confirmed by reading `pydoll/browser/requests/har_recorder.py` and `pydoll/browser/requests/request.py`)
- **remoteok.com adapter** works: 10 leads fetched, ranked, and saved (this adapter uses `httpx` directly, no browser)
- **Groq LLM calls** work (ranker, chat route, code-fence stripping all fixed)

---

## Files to Change

| File | Change needed |
|---|---|
| `worker/scout/network_sniff.py` | Full rewrite of `scout()` and `_collect_json_responses()` to use `tab.request.record()` instead of `get_network_logs()` |
| `worker/scout/pydantic_scout.py` | Lower sibling/occurrence thresholds from 5 → 3; lowercase tag name in selector |

---

## Key pydoll v2.22.1 API Facts

```python
# WRONG (current code) — only captures outgoing request events, no bodies
logs = await tab.get_network_logs()         # list[RequestWillBeSentEvent]
body = await tab.get_network_response_body(request_id)  # fails

# CORRECT — HAR context manager captures full request+response cycle
from pydoll.protocol.network.types import ResourceType
async with tab.request.record(resource_types=[ResourceType.XHR, ResourceType.FETCH]) as capture:
    await navigate(tab, url)
    await settle(tab, 4)
# capture.entries → list[HarEntry]
# entry['request']['url']                   → str
# entry['response']['status']               → int  
# entry['response']['content']['text']      → str (response body, may be absent)
# entry['response']['content']['mimeType']  → str
# entry.get('_resourceType')                → 'XHR' | 'Fetch' | ...

# tab.on() also works for custom event subscriptions:
callback_id = await tab.on("Network.responseReceived", my_callback)
await tab.remove_callback(callback_id)
```

---

## How to Test After Fix

```bash
# cd to project root, set PYTHONUTF8=1 on Windows
$env:PYTHONUTF8=1
python scripts/test_scout.py https://boards.greenhouse.io/anthropic jobs
# Expected: Tier-1 spec found (endpoint, item_path, fields) OR Tier-2 spec (card_selector)

python scripts/test_scout.py https://jobicy.com jobs
# jobicy is SSR so Tier-1 should fail; Tier-2 should find repeating article cards
```

If `test_scout.py` returns a spec for any site, end-to-end scraping works and leads will be generated for user-added sources.
