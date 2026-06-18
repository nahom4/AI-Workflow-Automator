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
    import os as _os
    if _os.getenv("SCOUT_DEBUG"):
        print(f"[scout] {url}: detector returned {len(candidates)} candidates", flush=True)
    if not candidates:
        return None

    # Build multi-candidate prompt: top 5 candidates, each with up to 2 sample HTMLs.
    blocks: list[str] = []
    for i, cand in enumerate(candidates[:5]):
        html_list = await _sample_card_html(tab, cand["selector"], n=2, max_len=1800)
        if _os.getenv("SCOUT_DEBUG"):
            print(f"[scout]   cand[{i}] selector={cand['selector']} count={cand['count']} samples={len(html_list)}", flush=True)
        if not html_list:
            continue
        blocks.append(
            f"### Candidate {i + 1}\n"
            f"selector: {cand['selector']}\n"
            f"count: {cand['count']}\n"
            f"sample HTML:\n" + "\n--\n".join(html_list)
        )

    if _os.getenv("SCOUT_DEBUG"):
        print(f"[scout] {url}: built {len(blocks)} prompt blocks", flush=True)
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
    except Exception as exc:
        import os, sys
        if os.getenv("SCOUT_DEBUG"):
            print(f"[pydantic_scout] LLM error at {url}: {exc}", flush=True)
        return None

    import os, sys
    if os.getenv("SCOUT_DEBUG"):
        print(f"[pydantic_scout] LLM response at {url}:\n{raw}\n---", flush=True)

    try:
        result = json.loads(strip_code_fences(raw))
    except (json.JSONDecodeError, TypeError):
        if os.getenv("SCOUT_DEBUG"):
            print(f"[pydantic_scout] JSON parse failed at {url}", flush=True)
        return None

    if result.get("found") is False:
        if os.getenv("SCOUT_DEBUG"):
            print(f"[pydantic_scout] LLM said found=false at {url}", flush=True)
        return None
    if not result.get("card_selector") or not result.get("fields"):
        if os.getenv("SCOUT_DEBUG"):
            print(f"[pydantic_scout] missing card_selector/fields at {url}: {result}", flush=True)
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

    CSS class selectors are subset-matchers: `.list-unstyled` matches BOTH
    `class="list-unstyled"` AND `class="list-unstyled padding-left-10"`. So
    when the detector reports `ul.list-unstyled > li` count=12 (only matching
    parents whose class set is exactly {list-unstyled}), the sampler's CSS
    query pulls in 200+ subset-matches from sidebar filter wrappers.

    Fix: parse the selector's class lists and apply STRICT class-set equality
    when grouping by parent. Then pick the parent with the most matches.

    NOTE: pydoll auto-wraps scripts containing `return` in an IIFE — but only
    if the script does NOT already start with `function(` or `(...) =>`. We
    deliberately use a plain return statement so the wrap kicks in cleanly.
    """
    js = (
        f"const sel = {json.dumps(selector)};\n"
        "// Parse selector into {parent: {tag, classes}, child: {tag, classes}}\n"
        "function parsePart(p) {\n"
        "  const m = p.match(/^([a-z0-9*]+)((?:\\.[^.\\s>]+)*)$/i);\n"
        "  if (!m) return null;\n"
        "  return { tag: m[1].toLowerCase(), classes: (m[2] || '').split('.').filter(Boolean) };\n"
        "}\n"
        "const parts = sel.split(/\\s*>\\s*/);\n"
        "const childP = parsePart(parts[parts.length - 1]) || {tag:'*', classes:[]};\n"
        "const parentP = parts.length > 1 ? parsePart(parts[0]) : null;\n"
        "function classSetEqual(el, classes) {\n"
        "  const ec = Array.from(el.classList).filter(Boolean);\n"
        "  if (ec.length !== classes.length) return false;\n"
        "  for (const c of classes) if (!ec.includes(c)) return false;\n"
        "  return true;\n"
        "}\n"
        "const allMatches = Array.from(document.querySelectorAll(sel));\n"
        "// Strict-filter: child must have exact class set; parent (if any) too.\n"
        "const matches = allMatches.filter(m => {\n"
        "  if (childP.classes.length && !classSetEqual(m, childP.classes)) return false;\n"
        "  if (parentP && parentP.classes.length) {\n"
        "    if (!m.parentElement) return false;\n"
        "    if (!classSetEqual(m.parentElement, parentP.classes)) return false;\n"
        "  }\n"
        "  return true;\n"
        "});\n"
        "if (!matches.length) return JSON.stringify([]);\n"
        "// Group by parent, pick the parent with the most strict-matching children\n"
        "const byParent = new Map();\n"
        "for (const m of matches) {\n"
        "  const p = m.parentElement; if (!p) continue;\n"
        "  if (!byParent.has(p)) byParent.set(p, []);\n"
        "  byParent.get(p).push(m);\n"
        "}\n"
        "let best = matches; let bestN = 0;\n"
        "for (const list of byParent.values()) {\n"
        "  if (list.length > bestN) { best = list; bestN = list.length; }\n"
        "}\n"
        f"return JSON.stringify(best.slice(0, {n}).map(c => c.outerHTML.slice(0, {max_len})));"
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
// tagGroups[key] = { total, max, bestParentN }
//   total = sum of same-tag children across all parents matching this signature
//   max   = largest single-parent group (this is what we actually care about
//           — a real listing container has all cards under ONE parent)
const tagGroups = {};
const skip = new Set(['SCRIPT','STYLE','META','LINK','HEAD','BR','HR','OPTION']);
const esc = (typeof CSS !== 'undefined' && CSS.escape)
  ? CSS.escape
  : (s => s.replace(/([\\!"#$%&'()*+,./:;<=>?@\[\\\]^`{|}~])/g, '\\$1'));

// Class-fingerprint pass — same as before.
document.querySelectorAll('*').forEach(el => {
  if (skip.has(el.tagName)) return;
  const parent = el.parentElement;
  if (!parent) return;
  const siblings = Array.from(parent.children).filter(c => c.tagName === el.tagName);
  if (siblings.length < 3) return;
  const cls = Array.from(el.classList).filter(Boolean);
  if (cls.length) {
    const key = el.tagName.toLowerCase() + cls.map(c => '.' + esc(c)).join('');
    classCounts[key] = (classCounts[key] || 0) + 1;
  }
});

// Tag-pattern pass — walk every parent and bucket its same-tag children.
// We track BOTH `total` (sum across page) and `max` (best single parent),
// then sort by `max` so a single 12-child <ul> beats a 17-spread sidebar.
document.querySelectorAll('*').forEach(parent => {
  if (skip.has(parent.tagName)) return;
  const childTagCounts = {};
  for (const c of parent.children) {
    if (skip.has(c.tagName)) continue;
    const t = c.tagName;
    childTagCounts[t] = (childTagCounts[t] || 0) + 1;
  }
  for (const [tagUpper, n] of Object.entries(childTagCounts)) {
    if (n < 4) continue;
    const tag = tagUpper.toLowerCase();
    const pcls = Array.from(parent.classList).filter(Boolean);
    const psig = parent.tagName.toLowerCase()
      + (pcls.length ? pcls.map(c => '.' + esc(c)).join('') : '');
    const key = psig + ' > ' + tag;
    if (!tagGroups[key]) tagGroups[key] = { total: 0, max: 0 };
    tagGroups[key].total += n;
    if (n > tagGroups[key].max) tagGroups[key].max = n;
  }
});

const classCands = Object.entries(classCounts)
  .filter(([, n]) => n >= 3)
  .sort((a, b) => b[1] - a[1])
  .slice(0, 8)
  .map(([sel, count]) => ({ selector: sel, count, kind: 'class' }));

// Sort tag candidates by MAX single-parent count, not total — the parent
// with the largest same-tag child group is the listing container. Without
// this, scattered filter-sidebar `<li>`s (cumulative count 17) outrank a
// genuine 12-card `<ul>`.
const tagCands = Object.entries(tagGroups)
  .filter(([, v]) => v.max >= 4)
  .sort((a, b) => b[1].max - a[1].max)
  .slice(0, 6)
  .map(([sel, v]) => ({ selector: sel, count: v.max, kind: 'tag' }));

// Merge both lists — sites like scholarshipdb render listing cards as
// plain <li> with no class, so the tag-fallback is the only signal.
const merged = [...classCands, ...tagCands].sort((a, b) => b.count - a.count);
return JSON.stringify(merged.slice(0, 10));
"""
