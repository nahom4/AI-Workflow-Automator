"""
URL discovery for unknown domains.

When the bare home page yields no listings (typical for marketing sites like
fulbright.org or government portals), we expand the search:

1. `llm_suggest_paths()` — ask Groq for likely listing-page paths given the
   domain, vertical, and the user's intent text. Returns absolute URLs.

2. `crawl_home_sublinks()` — extract all <a href> links from the currently
   loaded tab, score each by how many vertical-specific keywords appear in
   its anchor text and href, return top N same-origin URLs.

The runner tries (home → LLM-suggested → sublink-crawl) and saves the URL
that finally produces items into the site_specs row as `entry_url`.
"""

from __future__ import annotations

import asyncio
import json
import re

from worker.ai.groq_client import chat, strip_code_fences

VERTICAL_KEYWORDS: dict[str, list[str]] = {
    "scholarships": [
        "scholarship", "scholarships", "fellowship", "fellowships",
        "grant", "grants", "award", "funding", "bursary", "stipend",
        "study", "apply", "program", "programs", "opportunit",
    ],
    "jobs": [
        "job", "jobs", "career", "careers", "vacancy", "vacancies",
        "openings", "hiring", "positions", "roles", "employment",
        "work", "remote",
    ],
    "products": [
        "product", "products", "shop", "store", "browse", "catalog",
        "catalogue", "category", "deals", "trending", "new",
    ],
    "other": [],
}


_PATH_PROMPT = """\
A user wants to scrape a site for items matching their intent. The site's
home page does not contain a list of items — it's a marketing or landing
page. Suggest up to 3 URL paths on the same domain that are most likely to
contain a *list* of items (not detail pages, not search forms).

Return ONLY a JSON object: {{"paths": ["/path-1", "/path-2"]}}
- Paths must start with /
- Do NOT include the protocol or domain
- Prefer common listing patterns: /scholarships, /jobs, /careers,
  /opportunities, /programs, /grants, /search, /browse
- If you have no good guesses, return {{"paths": []}}

Domain: {domain}
Vertical: {vertical}
User intent: {intent}
"""


async def llm_suggest_paths(
    domain: str,
    vertical: str,
    intent: str | None,
) -> list[str]:
    """Ask the LLM for likely listing URLs. Returns absolute URLs (max 3).

    Errors and unparseable responses produce an empty list.
    """
    try:
        raw = await chat(
            _PATH_PROMPT.format(
                domain=domain,
                vertical=vertical or "other",
                intent=intent or vertical or "items",
            ),
            system="You produce only valid JSON. No prose, no preamble.",
            max_tokens=200,
            temperature=0.2,
        )
    except Exception:
        return []

    text = strip_code_fences(raw).strip()
    # Tolerate prose wrapping by extracting the first {...} block.
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        obj = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []

    paths = obj.get("paths") or []
    if not isinstance(paths, list):
        return []
    out: list[str] = []
    for p in paths:
        if not isinstance(p, str):
            continue
        path = p.strip()
        if not path or path == "/":
            continue
        if not path.startswith("/"):
            path = "/" + path
        out.append(f"https://{domain}{path}")
    # De-dup preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for u in out:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped[:3]


async def crawl_home_sublinks(
    tab,
    *,
    domain: str,
    vertical: str,
    max_links: int = 3,
) -> list[str]:
    """Extract <a href> links from the loaded tab, rank by vertical keywords,
    return top `max_links` same-origin URLs. Caller must have navigated.

    Returns [] if the vertical has no keywords or no scoring links found.
    """
    keywords = VERTICAL_KEYWORDS.get(vertical, [])
    if not keywords:
        return []

    # Collect href + visible text. Cap text length to keep payload small.
    js = """
    const out = [];
    for (const a of document.querySelectorAll('a[href]')) {
      const href = a.href;
      if (!/^https?:/i.test(href)) continue;
      const text = (a.textContent || '').trim().slice(0, 200);
      out.push({href, text});
    }
    return JSON.stringify(out);
    """
    try:
        r = await asyncio.wait_for(
            tab.execute_script(js, return_by_value=True),
            timeout=10.0,
        )
        value = r["result"]["result"]["value"]
        links = json.loads(value)
    except Exception:
        return []
    if not isinstance(links, list):
        return []

    domain_re = re.escape(domain)
    same_origin = re.compile(rf"^https?://(?:www\.)?{domain_re}(?:[/?#]|$)", re.I)

    scored: list[tuple[int, str]] = []
    seen: set[str] = set()
    for link in links:
        href = (link.get("href") or "").split("#")[0]
        if not href or not same_origin.match(href):
            continue
        if href in seen:
            continue
        seen.add(href)
        text_lc = (link.get("text") or "").lower()
        path_lc = href.lower()
        score = 0
        for kw in keywords:
            if kw in text_lc:
                score += 2
            if kw in path_lc:
                score += 3
        # Bias against bare home and very short paths
        path_only = re.sub(r"^https?://[^/]+", "", href)
        if path_only in ("", "/"):
            score = 0
        if score > 0:
            scored.append((score, href))

    scored.sort(reverse=True)
    return [u for _, u in scored[:max_links]]
