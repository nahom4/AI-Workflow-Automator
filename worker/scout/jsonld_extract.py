"""JSON-LD ItemList extractor — the cheapest possible try-path.

Many SEO-conscious listing sites (IMDB charts, recipe sites, e-commerce
search, job boards) embed a schema.org `ItemList` JSON-LD block in their
page <head> for Google rich results. When present, it gives us the
listing items directly — no card detection, no DOM mapping, no LLM.

This runs *before* the vision/pydantic scout. If it returns 3+ items we
skip the heavier path entirely and cache a `jsonld` spec.
"""

from __future__ import annotations

import asyncio
import json

from worker.browser import navigate, wait_for_content


async def try_extract(tab, url: str) -> list[dict]:
    """Navigate to `url`, parse JSON-LD blocks, return flattened ItemList items.

    Each item is `{title, url, id}` (id mirrors url for dedupe). Returns []
    if no ItemList is found, navigation fails, or the page has no JSON-LD.
    """
    try:
        await asyncio.wait_for(navigate(tab, url), timeout=60.0)
        await asyncio.wait_for(wait_for_content(tab, max_wait=15.0), timeout=20.0)
    except asyncio.TimeoutError:
        return []

    js = r"""
    const out = [];
    function pushItem(item) {
        if (!item || typeof item !== 'object') return;
        const title = item.name || item.headline || item.title || '';
        const u = item.url || item['@id'] || '';
        const t = String(title || '').trim();
        const uu = String(u || '').trim();
        if (t || uu) out.push({title: t, url: uu});
    }
    function walk(node) {
        if (!node || typeof node !== 'object') return;
        const type = node['@type'];
        const isItemList = type === 'ItemList'
            || (Array.isArray(type) && type.includes('ItemList'));
        if (isItemList && Array.isArray(node.itemListElement)) {
            for (const e of node.itemListElement) {
                const item = (e && typeof e === 'object' && e.item) ? e.item : e;
                pushItem(item);
            }
        }
        if (Array.isArray(node['@graph'])) {
            for (const child of node['@graph']) walk(child);
        }
    }
    const blocks = Array.from(
        document.querySelectorAll('script[type="application/ld+json"]')
    );
    for (const b of blocks) {
        try {
            const data = JSON.parse(b.textContent);
            const arr = Array.isArray(data) ? data : [data];
            for (const node of arr) walk(node);
        } catch (e) { /* skip malformed */ }
    }
    return JSON.stringify(out);
    """
    try:
        raw = await asyncio.wait_for(
            tab.execute_script(js, return_by_value=True), timeout=10.0
        )
    except asyncio.TimeoutError:
        return []
    try:
        value = raw["result"]["result"]["value"]
    except (KeyError, TypeError):
        return []
    if not value:
        return []
    try:
        items = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(items, list):
        return []

    seen: set[str] = set()
    out: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        key = it.get("url") or it.get("title") or ""
        if not key or key in seen:
            continue
        seen.add(key)
        it["id"] = it.get("url") or it.get("title") or ""
        out.append(it)
    return out
