"""
Upwork adapter — ported from upwork-research/scraper/upwork_scraper.py.

Scrapes the public Upwork job search (no login required).
Uses pydoll in headed+stealth mode to bypass Cloudflare Turnstile.

Interface: fetch_items(tab, *, search_query, max_jobs=50) -> list[dict]
Each returned dict has at minimum: id, title, url (standard runner contract).
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from worker.browser import navigate, settle
from worker.config import NAV_TIMEOUT, SETTLE_SECONDS

DOMAIN = "upwork.com"
VERTICAL = "jobs"
_BASE_SEARCH = "https://www.upwork.com/nx/search/jobs/"

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def fetch_items(tab, *, search_query: str, max_jobs: int = 50) -> list[dict]:
    """
    Navigate to Upwork job search, extract job cards, return normalized items.
    Handles Cloudflare Turnstile via pydoll's built-in bypass.
    """
    await tab.enable_auto_solve_cloudflare_captcha(time_to_wait_captcha=60)
    url = _build_search_url(search_query)
    await navigate(tab, url)
    await asyncio.sleep(3.5 + SETTLE_SECONDS)
    await _scroll(tab)
    await _wait_hydrated(tab)

    raw_cards = await _extract_raw_cards(tab)
    items = [_normalize(c) for c in raw_cards if c.get("jobId")]
    return items[:max_jobs]


# ---------------------------------------------------------------------------
# Helpers — all independently testable
# ---------------------------------------------------------------------------

def _build_search_url(query: str) -> str:
    return f"{_BASE_SEARCH}?q={quote(query)}&sort=recency&per_page=50"


def _normalize(card: dict) -> dict:
    budget = parse_budget(card.get("budgetRaw", ""))
    posted_at = parse_relative_date(card.get("postedText", ""))
    return {
        "id": card["jobId"],
        "title": card["title"],
        "url": card["url"],
        "skills": card.get("skills", []),
        "proposals_text": card.get("proposalsText", ""),
        "description": card.get("descSnippet", ""),
        "posted_at": posted_at.isoformat() if posted_at else None,
        "budget": budget,
    }


async def _extract_raw_cards(tab) -> list[dict]:
    resp = await tab.execute_script(_EXTRACT_CARDS_JS, return_by_value=True)
    raw = resp.get("result", {}).get("result", {}).get("value")
    return raw if isinstance(raw, list) else []


async def _wait_hydrated(tab, timeout_s: float = 30.0) -> int:
    """Poll until job tile count is stable; return final tile count."""
    deadline = time.monotonic() + timeout_s
    last_n = -1
    stable = 0

    while time.monotonic() < deadline:
        resp = await tab.execute_script(_COUNT_TILES_JS, return_by_value=True)
        try:
            n = int(resp.get("result", {}).get("result", {}).get("value", 0))
        except Exception:
            n = 0

        if n >= 1:
            if n == last_n:
                stable += 1
                if stable >= 3:
                    return n
            else:
                stable = 1
                last_n = n
        else:
            last_n = n
            stable = 0

        await asyncio.sleep(1.5)

    return await _count_tiles(tab)


async def _count_tiles(tab) -> int:
    resp = await tab.execute_script(_COUNT_TILES_JS, return_by_value=True)
    try:
        return int(resp.get("result", {}).get("result", {}).get("value", 0))
    except Exception:
        return 0


async def _scroll(tab) -> None:
    try:
        await tab.execute_script(
            "window.scrollTo(0, Math.min(2000, document.body.scrollHeight));"
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Pure parsing helpers (no browser)
# ---------------------------------------------------------------------------

def parse_budget(text: str) -> dict:
    text = text.replace(",", "").strip()
    result: dict = {"raw": text, "min": None, "max": None, "type": "fixed"}
    tl = text.lower()
    if "/hr" in tl or tl.startswith("hourly") or "hourly:" in tl:
        result["type"] = "hourly"
    nums = re.findall(r"\d+(?:\.\d+)?", text)
    if len(nums) >= 2:
        result["min"] = float(nums[0])
        result["max"] = float(nums[1])
    elif len(nums) == 1:
        result["min"] = result["max"] = float(nums[0])
    return result


def parse_relative_date(text: str) -> datetime | None:
    text = text.lower().strip()
    now = datetime.now(timezone.utc)
    if not text:
        return None
    if "just now" in text or ("minute" in text and re.search(r"\d", text) is None):
        return now
    m = re.search(r"(\d+)\s+minute", text)
    if m:
        return now - timedelta(minutes=int(m.group(1)))
    m = re.search(r"(\d+)\s+hour", text)
    if m:
        return now - timedelta(hours=int(m.group(1)))
    if "yesterday" in text:
        return now - timedelta(days=1)
    m = re.search(r"(\d+)\s+day", text)
    if m:
        return now - timedelta(days=int(m.group(1)))
    m = re.search(r"(\d+)\s+week", text)
    if m:
        return now - timedelta(weeks=int(m.group(1)))
    m = re.search(r"(\d+)\s+month", text)
    if m:
        return now - timedelta(days=int(m.group(1)) * 30)
    return None


# ---------------------------------------------------------------------------
# JavaScript strings (injected into the browser)
# ---------------------------------------------------------------------------

_COUNT_TILES_JS = """(function() {
  const sels = [
    'article.job-tile','section.job-tile','div.job-tile',
    '.job-tile','[data-test="job-tile"]','[data-ev-label="job_tile"]'
  ];
  for (const s of sels) {
    const n = document.querySelectorAll(s).length;
    if (n > 0) return n;
  }
  return 0;
})()"""

_EXTRACT_CARDS_JS = r"""
(function() {
  const TILE_SELS = [
    'article.job-tile','section.job-tile','div.job-tile',
    '.job-tile','[data-test="job-tile"]','[data-ev-label="job_tile"]'
  ];
  let tiles = [];
  for (const s of TILE_SELS) {
    tiles = Array.from(document.querySelectorAll(s));
    if (tiles.length) break;
  }

  // Fallback: collect by job links if no tile selector matched
  if (!tiles.length) {
    const seen = new Set();
    const items = [];
    for (const a of document.querySelectorAll('a[href*="/jobs/"], a[href*="/freelance-jobs/"]')) {
      let href = a.getAttribute('href') || '';
      try { href = decodeURIComponent(href); } catch(e) {}
      if (href.includes('/jobs/apply/')) continue;
      if (href.startsWith('/')) href = 'https://www.upwork.com' + href;
      const m = href.match(/~([A-Za-z0-9]+)/);
      if (!m) continue;
      const jobId = m[1];
      if (seen.has(jobId)) continue;
      let title = (a.innerText || '').trim().split('\n')[0].trim();
      if (title.length < 5) continue;
      seen.add(jobId);
      items.push({jobId, url: href.split('?')[0], title, skills:[], proposalsText:'', postedText:'', budgetRaw:'', descSnippet:''});
    }
    return items;
  }

  function txt(el) { return el ? (el.innerText || el.textContent || '').trim() : ''; }
  function q(el, sel) { try { return el.querySelector(sel); } catch(e) { return null; } }
  function qa(el, sel) { try { return Array.from(el.querySelectorAll(sel)); } catch(e) { return []; } }

  const items = [];
  for (const tile of tiles) {
    const titleSels = [
      'a.job-title-link','.job-tile-title a','h2 a','h3 a',
      '[data-test="job-title"] a','a[href*="/jobs/"]'
    ];
    let anchor = null;
    for (const s of titleSels) { anchor = q(tile, s); if (anchor) break; }
    if (!anchor) continue;

    let href = anchor.getAttribute('href') || '';
    try { href = decodeURIComponent(href); } catch(e) {}
    if (href.startsWith('/')) href = 'https://www.upwork.com' + href;
    const idMatch = href.match(/~([A-Za-z0-9]+)/);
    if (!idMatch) continue;
    const jobId = idMatch[1];
    const url = href.split('?')[0].split('#')[0];
    let title = txt(anchor).split('\n')[0].trim();
    if (title.length < 5) continue;

    // Budget
    const budgetSels = [
      '[data-test="budget"]','[data-test="job-type-label"]',
      '.js-budget','[class*="budget"]','[class*="Budget"]',
      '[data-test="hourly-rate"]','[data-test="fixed-price"]'
    ];
    let budgetRaw = '';
    for (const s of budgetSels) {
      const el = q(tile, s);
      if (el) { budgetRaw = txt(el); if (budgetRaw) break; }
    }
    if (!budgetRaw) {
      for (const el of qa(tile, '*')) {
        const t = txt(el);
        if (t.includes('$') && t.length < 50 && !t.includes(title.slice(0,10))) {
          budgetRaw = t; break;
        }
      }
    }

    // Skills
    const skillSels = [
      '[data-test="TokenClamp"] button','[data-test="TokenClamp"] span',
      '.air3-token-container button','.air3-token','[class*="skill"] button',
      '[data-test="skillsList"] button','.skills-list li'
    ];
    let skills = [];
    for (const s of skillSels) {
      const els = qa(tile, s);
      if (els.length) { skills = els.map(e => txt(e)).filter(Boolean); break; }
    }

    // Proposals
    const propSels = [
      '[data-test="proposals-tier"]','[data-test="proposals"]',
      '.proposals-count','[class*="proposals"]'
    ];
    let proposalsText = '';
    for (const s of propSels) {
      const el = q(tile, s);
      if (el) { proposalsText = txt(el); if (proposalsText) break; }
    }
    if (!proposalsText) {
      for (const el of qa(tile, 'small, span, li')) {
        const t = txt(el).toLowerCase();
        if (t.includes('proposal') || t.includes('bid')) { proposalsText = txt(el); break; }
      }
    }

    // Posted date
    const dateSels = [
      '[data-test="job-pubilshed-date"]','[data-test="job-published-date"]',
      '.job-pubilshed-date','[class*="posted"]','time'
    ];
    let postedText = '';
    for (const s of dateSels) {
      const el = q(tile, s);
      if (el) { postedText = el.getAttribute('datetime') || txt(el); if (postedText) break; }
    }
    if (!postedText) {
      for (const el of qa(tile, 'small, span')) {
        const t = txt(el).toLowerCase();
        if (t.includes(' ago') || t.startsWith('posted')) { postedText = txt(el); break; }
      }
    }

    // Description snippet
    const descSels = [
      '[data-test="job-description-text"]','.job-description-text',
      '[class*="description"]','p.mb-0','p'
    ];
    let descSnippet = '';
    for (const s of descSels) {
      const el = q(tile, s);
      if (el) { const t = txt(el); if (t.length > 20) { descSnippet = t.slice(0, 500); break; } }
    }

    items.push({jobId, url, title, budgetRaw, skills, proposalsText, postedText, descSnippet});
  }
  return items;
})()
"""
