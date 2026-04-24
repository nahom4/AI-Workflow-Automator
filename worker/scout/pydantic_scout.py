"""
Tier 2 scout: find repeating DOM elements, extract sample HTML, ask Groq for
CSS selectors, build a pydoll ExtractionModel. Falls back gracefully.

Returns a spec dict:
{
  "card_selector": "section.job-tile",
  "fields": {
    "title": {"selector": "h2.title", "attr": null},
    "url": {"selector": "a.job-link", "attr": "href"},
    "id": {"selector": "[data-id]", "attr": "data-id"}
  }
}
"""

from __future__ import annotations

import json

from worker.ai.groq_client import chat
from worker.browser import navigate, settle

_SYSTEM = """\
You are a CSS selector expert. Given sample HTML cards from a listing page,
return CSS selectors to extract structured data.

Respond with valid JSON only:
{
  "card_selector": "<CSS selector for one item card>",
  "fields": {
    "title":   {"selector": "<CSS>", "attr": null},
    "url":     {"selector": "<CSS>", "attr": "href"},
    "id":      {"selector": "<CSS>", "attr": "<data-attr or null>"},
    "salary":  {"selector": "<CSS or null>", "attr": null}
  }
}
If you cannot identify a card structure, respond: {"found": false}
"""


async def scout(tab, *, url: str, vertical: str) -> dict | None:
    """
    Navigate to url, detect repeating card DOM, sample 3 cards, ask Groq
    for selectors. Returns tier-2 spec or None.
    """
    await navigate(tab, url)
    await settle(tab, 2)

    # Find the repeating subtree via JS
    card_candidates = await tab.evaluate(
        _REPEATING_SUBTREE_JS,
        return_by_value=True,
    )
    candidates = card_candidates.get("result", {}).get("result", {}).get("value", "[]")
    try:
        candidates = json.loads(candidates)
    except Exception:
        return None

    if not candidates:
        return None

    # Take the best candidate and sample 3 card HTML snippets
    best = candidates[0]
    sample_html = await tab.evaluate(
        f"""
        (function() {{
            const cards = Array.from(document.querySelectorAll({json.dumps(best['selector'])})).slice(0, 3);
            return JSON.stringify(cards.map(c => c.outerHTML.slice(0, 2000)));
        }})()
        """,
        return_by_value=True,
    )
    raw_html = sample_html.get("result", {}).get("result", {}).get("value", "[]")
    try:
        snippets = json.loads(raw_html)
    except Exception:
        return None

    if not snippets:
        return None

    prompt = (
        f"Vertical: {vertical}\n"
        f"Page URL: {url}\n\n"
        f"Sample card HTML ({len(snippets)} cards):\n"
        + "\n---\n".join(snippets[:3])
    )
    raw = await chat(prompt, system=_SYSTEM)
    try:
        result = json.loads(raw)
        if result.get("found") is False:
            return None
        return result
    except Exception:
        return None


# Finds the most common repeating tag+class pattern among siblings
_REPEATING_SUBTREE_JS = """
(function() {
  const counts = {};
  document.querySelectorAll('*').forEach(el => {
    const parent = el.parentElement;
    if (!parent) return;
    const siblings = Array.from(parent.children);
    if (siblings.length < 5) return;
    const key = el.tagName + '.' + Array.from(el.classList).join('.');
    if (!key || key === el.tagName + '.') return;
    counts[key] = (counts[key] || 0) + 1;
  });
  const sorted = Object.entries(counts)
    .filter(([, n]) => n >= 5)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([sel, count]) => ({ selector: sel.replace(/\\./g, '.').replace(/^(\\w+)/, '$1'), count }));
  return JSON.stringify(sorted);
})()
"""
