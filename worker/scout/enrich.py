"""Detail-page enrichment.

After the scout produces a list of cards `{title, url}`, the ranker needs more
than a title to make meaningful judgments — "Project Hail Mary" doesn't tell
an LLM whether it's sci-fi or a coming-of-age drama.

This module fetches the detail page over plain HTTP (no browser) and pulls a
description via:
  1. `meta[name="description"]`
  2. `meta[property="og:description"]`
  3. `meta[name="twitter:description"]`
  4. JSON-LD `description` field on a Movie/Product/Article/Course/etc.
  5. JSON-LD `abstract` (papers)
  6. First long-ish `<p>` inside <article>/<main>

Pure HTTP is ~10x faster than spinning up a tab per URL and works for most
content sites (server-rendered metadata is the norm). Pages that 100% depend
on JS for og: tags will return nothing — caller falls back to title-only
ranking in that case.
"""

from __future__ import annotations

import asyncio
import json
import re
from html.parser import HTMLParser

import requests


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

_MAX_DESCRIPTION = 1200  # chars; long enough for ranker, short enough for prompt budget


# Phrases that strongly suggest a description is the site's social-share /
# marketing boilerplate rather than the actual item content. RT serves
# "Discover reviews, ratings, and trailers for X. Stay updated with critic
# and audience scores today!" — that's worse than no description because
# the ranker treats empty-content templates as "no info → low score" and
# DOWNGRADES items relative to their title-only score.
_TEMPLATE_PHRASES = (
    "discover reviews",
    "ratings, and trailers",
    "ratings and trailers",
    "stay updated",
    "today!",
    "critic and audience scores",
    "visit our site",
    "subscribe to our",
    "sign up for our",
    "buy now",
    "click here to",
    "watch trailers and",
    "find showtimes",
    # Fandango / streaming-CTA boilerplate served by Rotten Tomatoes
    "tickets on fandango",
    "on fandango at home",
    "buy it on fandango",
    "rent it on fandango",
    "with a subscription on",
    "buy or rent",
    "available to rent",
    "stream now on",
)


def _looks_like_template(text: str) -> bool:
    """Heuristic: short descriptions with multiple marketing phrases are
    site-boilerplate, not item content. Long descriptions (400+ chars) are
    almost always real even if they include 'subscribe' somewhere.
    """
    if len(text) >= 400:
        return False
    low = text.lower()
    hits = sum(1 for p in _TEMPLATE_PHRASES if p in low)
    return hits >= 2


class _MetaAndJsonLdParser(HTMLParser):
    """Pulls every meta tag + every <script type='application/ld+json'> body.

    We're not trying to be a full HTML parser — just collect the two structures
    the description-extraction logic needs. Anything else is skipped.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.metas: list[dict[str, str]] = []
        self.jsonld_blobs: list[str] = []
        self._in_jsonld = False
        self._jsonld_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "meta":
            d = {k: (v or "") for k, v in attrs}
            self.metas.append(d)
        elif tag == "script":
            t = next((v for k, v in attrs if k == "type"), None) or ""
            if t.lower() == "application/ld+json":
                self._in_jsonld = True
                self._jsonld_buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_jsonld:
            self._in_jsonld = False
            blob = "".join(self._jsonld_buf).strip()
            if blob:
                self.jsonld_blobs.append(blob)
            self._jsonld_buf = []

    def handle_data(self, data: str) -> None:
        if self._in_jsonld:
            self._jsonld_buf.append(data)


_P_TAG_RE = re.compile(
    r"<(article|main)\b[^>]*>(.*?)</\1>", re.IGNORECASE | re.DOTALL
)
_INNER_P_RE = re.compile(r"<p\b[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    text = _TAG_STRIP_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text[:_MAX_DESCRIPTION]


def _walk_jsonld(node, out: list[str]) -> None:
    """Walk a JSON-LD object/list and collect every string-typed
    description/abstract/headline encountered. Many sites nest the real payload
    under @graph or itemListElement, so we recurse.
    """
    if isinstance(node, dict):
        for key in ("description", "abstract", "articleBody"):
            v = node.get(key)
            if isinstance(v, str) and v.strip():
                out.append(v.strip())
        # Recurse into known container fields
        for k in ("@graph", "itemListElement", "mainEntity", "hasPart"):
            sub = node.get(k)
            if sub:
                _walk_jsonld(sub, out)
    elif isinstance(node, list):
        for x in node:
            _walk_jsonld(x, out)


def _extract_from_html(html: str) -> str | None:
    """Collect every plausible description source, then return the longest
    non-template one. Single-source priority order was broken for sites like
    Rotten Tomatoes that serve identical marketing boilerplate to og/twitter/
    meta/JSON-LD — we'd find a "match" early and never look at richer signals.
    """
    parser = _MetaAndJsonLdParser()
    try:
        parser.feed(html)
    except Exception:
        # Malformed HTML — best-effort: use what we collected before the failure
        pass

    candidates: list[str] = []

    # Meta tags
    for key, value in (
        ("property", "og:description"),
        ("name", "twitter:description"),
        ("name", "description"),
    ):
        for m in parser.metas:
            if m.get(key, "").lower() == value:
                content = (m.get("content") or "").strip()
                if content:
                    candidates.append(content)

    # JSON-LD description/abstract
    for blob in parser.jsonld_blobs:
        try:
            data = json.loads(blob)
        except (json.JSONDecodeError, ValueError):
            continue
        found: list[str] = []
        _walk_jsonld(data, found)
        candidates.extend(found)

    # First long <p> inside <article> or <main>
    container = _P_TAG_RE.search(html)
    inner = container.group(2) if container else html
    for m in _INNER_P_RE.finditer(inner):
        text = _normalize(m.group(1))
        if len(text) >= 80:
            candidates.append(text)
            break

    # Drop templates and dedupe
    seen: set[str] = set()
    real: list[str] = []
    for c in candidates:
        norm = _normalize(c)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        if _looks_like_template(norm):
            continue
        real.append(norm)

    if not real:
        return None
    # Longest is usually the most informative — short candidates are often
    # truncated meta tags while JSON-LD or article bodies have full content.
    return max(real, key=len)


def _fetch_sync(url: str, timeout: float) -> str | None:
    try:
        r = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    ctype = r.headers.get("content-type", "").lower()
    if "html" not in ctype and "xml" not in ctype:
        return None
    return _extract_from_html(r.text)


async def fetch_description(url: str, *, timeout: float = 10.0) -> str | None:
    """Async wrapper around the sync HTTP fetch. Returns the extracted
    description (≤1200 chars) or None.
    """
    if not url or not url.startswith(("http://", "https://")):
        return None
    return await asyncio.to_thread(_fetch_sync, url, timeout)
