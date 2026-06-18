"""Crawl4AI spike: compare against our pydantic_scout on the two pain sites.

Goal: prove (or disprove) that Crawl4AI's JsonCssExtractionStrategy.generate_schema()
+ LLMExtractionStrategy can do what our hand-rolled scout does, with Groq, no rewrites.

Run:
  python scripts/spike_crawl4ai.py scholarshipdb
  python scripts/spike_crawl4ai.py fulbright
  python scripts/spike_crawl4ai.py both
"""
import asyncio
import json
import os
import pathlib
import sys
import time

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)

# Load .env.local so GROQ_API_KEY is available.
_envfile = pathlib.Path(".env.local")
if _envfile.exists():
    for line in _envfile.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.extraction_strategy import (
    JsonCssExtractionStrategy,
    LLMExtractionStrategy,
)
from crawl4ai import LLMConfig

GROQ_KEY = os.environ.get("GROQ_API_KEY")
GEMINI_KEYS = [k.strip() for k in (os.environ.get("GEMINI_API_KEYS") or "").split(",") if k.strip()]
# Gemini 2.0 Flash free tier: 1M context, 1500 RPD per key, plenty of TPM headroom.
# We try keys in order and rotate on rate-limit.
LLM_MODEL_SCHEMA = "gemini/gemini-2.5-flash"
LLM_MODEL_EXTRACT = "gemini/gemini-2.5-flash"


def _next_gemini_key(used_idx: list) -> tuple[str, int] | tuple[None, None]:
    """Pick the next unused Gemini key. used_idx is mutated."""
    for i, k in enumerate(GEMINI_KEYS):
        if i not in used_idx:
            used_idx.append(i)
            return k, i
    return None, None

SITES = {
    "scholarshipdb": {
        # Diagnostics confirmed homepage has 12 real cards in `ul.list-unstyled > li`.
        "url": "https://scholarshipdb.net/",
        "vertical": "scholarships",
        "instruction": (
            "From this page, extract every distinct scholarship/PhD listing card. "
            "For each, return: title, university or organization, country, deadline (if shown), and the link to the listing page. "
            "Do NOT extract navigation links, filter chips, or category tags."
        ),
    },
    "fulbright": {
        # Their listing/programs page — homepage has no cards.
        "url": "https://fulbright.org/grants/",
        "vertical": "scholarships",
        "instruction": (
            "From this page, extract every distinct scholarship or program listing. "
            "For each, return: title, description, and the link. "
            "Do NOT extract navigation links, social-media buttons, or footer links."
        ),
    },
}


async def run_llm_extraction(name: str, site: dict) -> dict:
    """Use LLMExtractionStrategy: most direct test of 'does the LLM understand the page'."""
    print(f"\n{'='*60}")
    print(f"[{name}] LLMExtractionStrategy via {LLM_MODEL_EXTRACT}")
    print(f"URL: {site['url']}")
    print('='*60)

    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "organization": {"type": "string"},
                        "location": {"type": "string"},
                        "deadline": {"type": "string"},
                        "url": {"type": "string"},
                        "description": {"type": "string"},
                    },
                },
            }
        },
    }

    api_token = GEMINI_KEYS[0] if GEMINI_KEYS else GROQ_KEY
    llm_strategy = LLMExtractionStrategy(
        llm_config=LLMConfig(provider=LLM_MODEL_EXTRACT, api_token=api_token),
        schema=schema,
        extraction_type="schema",
        instruction=site["instruction"],
        chunk_token_threshold=4000,
        overlap_rate=0.0,
        apply_chunking=True,
        input_format="markdown",
        extra_args={"temperature": 0.0, "max_tokens": 2000},
    )

    browser_cfg = BrowserConfig(headless=True, verbose=False)
    run_cfg = CrawlerRunConfig(
        extraction_strategy=llm_strategy,
        cache_mode=CacheMode.BYPASS,
        word_count_threshold=10,
        # Focus the LLM on the listings region; falls back to whole page if absent.
        target_elements=site.get("target_elements") or None,
    )

    started = time.time()
    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        try:
            result = await crawler.arun(url=site["url"], config=run_cfg)
        except Exception as exc:
            print(f"  ERROR: {exc!r}")
            return {"name": name, "strategy": "llm", "error": repr(exc)}

    elapsed = time.time() - started
    print(f"  elapsed: {elapsed:.1f}s, success={result.success}")
    if not result.success:
        print(f"  reason: {result.error_message}")
        return {"name": name, "strategy": "llm", "error": result.error_message}

    raw = result.extracted_content
    items = []
    if raw:
        try:
            parsed = json.loads(raw)
            # crawl4ai sometimes returns list of objects each with 'items' key, sometimes flat.
            if isinstance(parsed, list):
                for chunk in parsed:
                    if isinstance(chunk, dict) and "items" in chunk:
                        items.extend(chunk["items"])
                    elif isinstance(chunk, dict):
                        items.append(chunk)
            elif isinstance(parsed, dict) and "items" in parsed:
                items = parsed["items"]
        except Exception as exc:
            print(f"  parse error: {exc}")

    print(f"  extracted {len(items)} items")
    for i, it in enumerate(items[:5], 1):
        print(f"    [{i}] {json.dumps(it, ensure_ascii=False)[:200]}")

    # Show LLM call usage
    try:
        usage = llm_strategy.show_usage() if hasattr(llm_strategy, "show_usage") else None
    except Exception:
        usage = None
    if usage:
        print(f"  usage: {usage}")

    return {
        "name": name,
        "strategy": "llm",
        "elapsed_s": round(elapsed, 1),
        "item_count": len(items),
        "first_items": items[:5],
    }


async def run_css_schema_generation(name: str, site: dict) -> dict:
    """Use JsonCssExtractionStrategy.generate_schema(): one LLM call to make a reusable
    CSS schema, then extract with zero further LLM calls. This is the *cost-saving*
    pattern that should fix our Groq TPD problem."""
    print(f"\n{'='*60}")
    print(f"[{name}] generate_schema → JsonCssExtractionStrategy")
    print(f"URL: {site['url']}")
    print('='*60)

    browser_cfg = BrowserConfig(headless=True, verbose=False)

    # Step 1: fetch the page once to get HTML for schema generation
    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        prefetch = await crawler.arun(
            url=site["url"],
            config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS, word_count_threshold=10),
        )
        if not prefetch.success:
            print(f"  prefetch failed: {prefetch.error_message}")
            return {"name": name, "strategy": "css_schema", "error": prefetch.error_message}
        # Use RAW html, not cleaned — cleaning strips the listings on dynamic sites.
        html = prefetch.html or prefetch.cleaned_html
        if not html:
            print("  no html returned")
            return {"name": name, "strategy": "css_schema", "error": "no html"}
        # Keep prompt manageable; trim to 60k chars (≈15k tokens).
        if len(html) > 60_000:
            print(f"  trimming raw html from {len(html)} to 60000 chars")
            html = html[:60_000]
        print(f"  fetched {len(html)} chars of raw html")

        # Step 2: generate schema (rotate Gemini keys on rate-limit failure)
        used_idx: list = []
        schema = None
        last_err = None
        keys_to_try = GEMINI_KEYS or [GROQ_KEY]
        for attempt in range(len(keys_to_try)):
            key, idx = _next_gemini_key(used_idx) if GEMINI_KEYS else (GROQ_KEY, 0)
            if not key:
                break
            print(f"  schema-gen attempt {attempt+1} (key #{idx})...")
            try:
                schema = JsonCssExtractionStrategy.generate_schema(
                    html=html,
                    schema_type="CSS",
                    target_json_example=json.dumps({
                        "title": "PhD in Foo",
                        "organization": "University of Bar",
                        "location": "Netherlands",
                        "deadline": "2026-08-01",
                        "url": "https://...",
                    }),
                    query=site["instruction"],
                    llm_config=LLMConfig(provider=LLM_MODEL_SCHEMA, api_token=key),
                )
                break
            except Exception as exc:
                last_err = exc
                msg = str(exc)
                print(f"  schema-gen failed: {msg[:200]}")
                if "rate" not in msg.lower() and "quota" not in msg.lower():
                    break  # non-rate-limit error, no point trying other keys
        if schema is None:
            return {"name": name, "strategy": "css_schema", "error": f"generate_schema: {last_err!r}"}

        print(f"  schema: {json.dumps(schema, indent=2)[:500]}")

        # Step 3: extract with the generated schema (no LLM)
        css_strategy = JsonCssExtractionStrategy(schema=schema)
        run_cfg = CrawlerRunConfig(
            extraction_strategy=css_strategy,
            cache_mode=CacheMode.BYPASS,
            word_count_threshold=10,
        )
        started = time.time()
        result = await crawler.arun(url=site["url"], config=run_cfg)

    elapsed = time.time() - started
    print(f"  elapsed: {elapsed:.1f}s, success={result.success}")
    if not result.success:
        print(f"  reason: {result.error_message}")
        return {"name": name, "strategy": "css_schema", "error": result.error_message, "schema": schema}

    items = []
    if result.extracted_content:
        try:
            items = json.loads(result.extracted_content)
        except Exception as exc:
            print(f"  parse error: {exc}")
    print(f"  extracted {len(items)} items")
    for i, it in enumerate(items[:5], 1):
        print(f"    [{i}] {json.dumps(it, ensure_ascii=False)[:200]}")

    return {
        "name": name,
        "strategy": "css_schema",
        "elapsed_s": round(elapsed, 1),
        "item_count": len(items),
        "schema": schema,
        "first_items": items[:5],
    }


async def main():
    if not GROQ_KEY:
        print("ERROR: GROQ_API_KEY not set")
        sys.exit(1)

    target = sys.argv[1] if len(sys.argv) > 1 else "both"
    targets = list(SITES.keys()) if target == "both" else [target]

    results = []
    for name in targets:
        site = SITES[name]
        # Run css-schema first (one LLM call) so we don't blow the budget.
        results.append(await run_css_schema_generation(name, site))
        results.append(await run_llm_extraction(name, site))

    print(f"\n\n{'#'*60}\n# SUMMARY\n{'#'*60}")
    for r in results:
        line = f"[{r['name']}/{r['strategy']}]"
        if "error" in r:
            line += f" ERROR: {str(r['error'])[:120]}"
        else:
            line += f" {r['item_count']} items in {r['elapsed_s']}s"
        print(line)


asyncio.run(main())
