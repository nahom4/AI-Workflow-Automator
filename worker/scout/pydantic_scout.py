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

from worker.ai.groq_client import chat, strip_code_fences
from worker.browser import navigate, settle, wait_for_content

_SYSTEM = """\
You are a CSS selector expert. You will be shown several candidate "card"
groups detected on a listing page. Pick the group whose HTML most clearly
represents one item in the listing (e.g. one job posting), then write CSS
selectors that extract fields *within* a card.

Rules:
- card_selector is a CSS selector usable via document.querySelectorAll that
  matches every card on the page. Pick the candidate selector you chose.
- field selectors are evaluated via card.querySelector(...) — they are
  RELATIVE to a single card root.
- For "url", prefer the first meaningful anchor: typical pattern is "a[href]"
  or "a.title" — extract the href via {"selector": "...", "attr": "href"}.
- For "title", prefer headings (h1/h2/h3) or anchor text.
- For "id", prefer a stable data-* attribute on the card or a child; else
  null and we will use the URL as id.

Respond with valid JSON only:
{
  "card_selector": "<CSS selector for one item card>",
  "fields": {
    "title":   {"selector": "<CSS>", "attr": null},
    "url":     {"selector": "<CSS>", "attr": "href"},
    "id":      {"selector": "<CSS or null>", "attr": "<data-attr or null>"},
    "salary":  {"selector": "<CSS or null>", "attr": null},
    "company": {"selector": "<CSS or null>", "attr": null},
    "location":{"selector": "<CSS or null>", "attr": null}
  }
}
If none of the candidates look like an item listing, respond: {"found": false}
"""


async def scout(tab, *, url: str, vertical: str) -> dict | None:
    """
    Navigate to url, detect repeating card DOM, sample 3 cards, ask Groq
    for selectors. Returns tier-2 spec or None.
    """
    await navigate(tab, url)
    await wait_for_content(tab, max_wait=20.0)

    candidates = await _find_repeating_subtrees(tab)
    if not candidates:
        return None

    # Build multi-candidate prompt: top 5 candidates, each with up to 2 sample HTMLs.
    blocks: list[str] = []
    for i, cand in enumerate(candidates[:5]):
        html_list = await _sample_card_html(tab, cand["selector"], n=2, max_len=1800)
        if not html_list:
            continue
        blocks.append(
            f"### Candidate {i + 1}\n"
            f"selector: {cand['selector']}\n"
            f"count: {cand['count']}\n"
            f"sample HTML:\n" + "\n--\n".join(html_list)
        )

    if not blocks:
        return None

    prompt = (
        f"Vertical: {vertical}\n"
        f"Page URL: {url}\n\n"
        f"Below are {len(blocks)} candidate repeating element groups detected on "
        f"the page. Pick the one that represents an item listing for the vertical "
        f"and write field selectors RELATIVE to one card.\n\n"
        + "\n\n".join(blocks)
    )
    try:
        raw = await chat(prompt, system=_SYSTEM, max_tokens=1024)
    except Exception:
        return None
    try:
        result = json.loads(strip_code_fences(raw))
    except (json.JSONDecodeError, TypeError):
        return None

    if result.get("found") is False:
        return None
    if not result.get("card_selector") or not result.get("fields"):
        return None
    return result


async def _find_repeating_subtrees(tab) -> list[dict]:
    """Run the detection JS and return a list of {selector, count} dicts."""
    raw = await tab.execute_script(_REPEATING_SUBTREE_JS, return_by_value=True)
    try:
        value = raw["result"]["result"]["value"]
    except (KeyError, TypeError):
        return []
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


async def _sample_card_html(tab, selector: str, *, n: int = 3, max_len: int = 2000) -> list[str]:
    """Grab outerHTML of up to `n` cards matching `selector`.

    NOTE: pydoll auto-wraps scripts containing `return` in an IIFE — but only
    if the script does NOT already start with `function(` or `(...) =>`. We
    deliberately use a plain return statement so the wrap kicks in cleanly.
    """
    js = (
        f"const cards = Array.from(document.querySelectorAll({json.dumps(selector)})).slice(0, {n});\n"
        f"return JSON.stringify(cards.map(c => c.outerHTML.slice(0, {max_len})));"
    )
    raw = await tab.execute_script(js, return_by_value=True)
    try:
        value = raw["result"]["result"]["value"]
    except (KeyError, TypeError):
        return []
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


# Detect repeating tag+class patterns. Each class is CSS.escape()'d so Tailwind
# classes like `hover:underline` and `md:gap-4` survive — the colon would
# otherwise be parsed as a pseudo-class. We also count tag+parent fallback
# patterns for sites with mostly inline-styled cards.
_REPEATING_SUBTREE_JS = r"""
const classCounts = {};
const tagCounts = {};
const skip = new Set(['SCRIPT','STYLE','META','LINK','HEAD','BR','HR','OPTION']);
const esc = (typeof CSS !== 'undefined' && CSS.escape)
  ? CSS.escape
  : (s => s.replace(/([\\!"#$%&'()*+,./:;<=>?@\[\\\]^`{|}~])/g, '\\$1'));

document.querySelectorAll('*').forEach(el => {
  if (skip.has(el.tagName)) return;
  const parent = el.parentElement;
  if (!parent) return;
  const siblings = Array.from(parent.children).filter(c => c.tagName === el.tagName);
  if (siblings.length < 3) return;

  const tag = el.tagName.toLowerCase();
  const cls = Array.from(el.classList).filter(Boolean);
  if (cls.length) {
    const key = tag + cls.map(c => '.' + esc(c)).join('');
    classCounts[key] = (classCounts[key] || 0) + 1;
  }
  const pcls = Array.from(parent.classList).filter(Boolean);
  const psig = parent.tagName.toLowerCase()
    + (pcls.length ? pcls.map(c => '.' + esc(c)).join('') : '');
  const tkey = psig + ' > ' + tag;
  tagCounts[tkey] = (tagCounts[tkey] || 0) + 1;
});

const classCands = Object.entries(classCounts)
  .filter(([, n]) => n >= 3)
  .sort((a, b) => b[1] - a[1])
  .slice(0, 8)
  .map(([sel, count]) => ({ selector: sel, count, kind: 'class' }));

const tagCands = Object.entries(tagCounts)
  .filter(([, n]) => n >= 4)
  .sort((a, b) => b[1] - a[1])
  .slice(0, 3)
  .map(([sel, count]) => ({ selector: sel, count, kind: 'tag' }));

const out = classCands.length ? classCands : tagCands;
return JSON.stringify(out);
"""
