"""
One automation run, end-to-end.
Called by main.py for each due automation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import nanoid  # type: ignore
from croniter import croniter  # type: ignore

import os

from worker import db
from worker.ai.ranker import rank
from worker.browser import make_chrome, start_browser
from worker.config import SCOUT_BACKEND
from worker.notify.email import send_lead_digest
from worker.notify import sheets as sheets_notify
from worker.notify import gmail_api
from worker.notify.google_auth import get_valid_token
from worker.scout import (
    enrich, jsonld_extract, network_sniff, pydantic_scout, vision_scout, vision_scout_v2,
)
from worker.scout.discover import llm_suggest_paths, crawl_home_sublinks
from worker.scout.validate import is_healthy


MAX_ITEMS_PER_SOURCE = 100
MAX_PAGES_PER_URL = 10


async def run_automation(automation: dict) -> None:
    run_id = nanoid.generate(size=10)
    automation_id = automation["id"]
    spec = json.loads(automation["spec_json"])
    sources: list[str] = spec["sources"]
    criteria: list[str] = spec.get("criteria", [])
    threshold: float = float(spec.get("threshold", 6))
    cv_text: str | None = spec.get("cv_text")
    vertical: str = automation.get("vertical", "other")

    await db.insert_run(run_id, automation_id)
    await _log(run_id, "info", f"Run started — {len(sources)} source(s)")

    items_seen = 0
    items_kept = 0
    new_leads: list[dict] = []
    errors: list[str] = []

    # Browser is created lazily — browser-free adapters (remoteok, etc.) skip it entirely.
    browser = None
    tab = None

    async def get_tab():
        nonlocal browser, tab
        if tab is None:
            browser, tab = await start_browser(retries=2)
        return tab

    try:
        for domain in sources:
            try:
                items = await _fetch_items(
                    get_tab,
                    domain=domain,
                    vertical=vertical,
                    spec=spec,
                    run_id=run_id,
                    intent_text=automation.get("intent_text"),
                )
                items_seen += len(items)
                await _log(run_id, "info", f"{domain}: fetched {len(items)} items")

                if items and not is_healthy(items):
                    await _log(
                        run_id, "warning",
                        f"{domain}: low-quality extraction — spec may need re-scouting"
                    )

                # Title-only ranks are noisy ("Project Hail Mary" → sci-fi? coming-of-age?).
                # First pass on the title is cheap; anything that clears `pre_threshold`
                # gets a detail-page fetch + description + a second rank with real signal.
                pre_threshold = max(threshold - 2.0, 3.0)

                for item in items:
                    score, reasons = await rank(
                        item,
                        criteria=criteria,
                        vertical=vertical,
                        cv_text=cv_text,
                        threshold=threshold,
                    )
                    if score < pre_threshold:
                        continue

                    if item.get("url") and not item.get("description"):
                        try:
                            desc = await enrich.fetch_description(item["url"])
                        except Exception as exc:
                            desc = None
                            await _log(run_id, "warning",
                                       f"enrich failed for {item.get('url')}: {exc}")
                        if desc:
                            item["description"] = desc
                            score, reasons = await rank(
                                item,
                                criteria=criteria,
                                vertical=vertical,
                                cv_text=cv_text,
                                threshold=threshold,
                            )

                    if score < threshold:
                        continue

                    lead_id = nanoid.generate(size=10)
                    is_new = await db.upsert_lead(
                        lead_id=lead_id,
                        automation_id=automation_id,
                        source_domain=domain,
                        external_id=str(item.get("id", lead_id)),
                        url=item.get("url", ""),
                        title=item.get("title", ""),
                        raw_json=item,
                        score=score,
                        matched_reasons=", ".join(reasons) if reasons else None,
                    )
                    if is_new:
                        items_kept += 1
                        new_leads.append(
                            {"title": item.get("title"), "url": item.get("url"), "score": score}
                        )

            except Exception as exc:
                msg = f"{domain}: {exc}"
                errors.append(msg)
                await _log(run_id, "error", msg)
                # Chrome death (ConnectionRefused, dead CDP socket, "Stop called
                # but browser is not running") leaves `tab`/`browser` pointing
                # at a corpse. Reset them so the next source spawns a fresh one
                # via get_tab().
                if _is_browser_failure(exc):
                    await _log(run_id, "info", f"{domain}: resetting browser after Chrome failure")
                    if browser is not None:
                        try:
                            await browser.stop()
                        except Exception:
                            pass
                    browser = None
                    tab = None
    finally:
        if browser is not None:
            try:
                await browser.stop()
            except Exception:
                pass

    await _log(run_id, "info", f"Kept {items_kept} / {items_seen} items ({len(new_leads)} new)")

    # Notify — Resend email
    if new_leads and automation.get("notify_email"):
        try:
            await send_lead_digest(
                to=automation["notify_email"],
                automation_name=automation["name"],
                leads=new_leads,
            )
            await _log(run_id, "info", f"Email digest sent to {automation['notify_email']}")
        except Exception as exc:
            await _log(run_id, "warning", f"Email failed: {exc}")

    # Google integrations — resolve user tokens once
    user_id = automation.get("user_id")
    google_sheet_id = automation.get("google_sheet_id")
    notify_gmail = bool(automation.get("notify_gmail"))
    _gtoken: str | None = None

    async def _google_token() -> str | None:
        nonlocal _gtoken
        if _gtoken:
            return _gtoken
        if not user_id:
            return None
        tokens = await db.get_user_google_tokens(user_id)
        if not tokens:
            return None
        client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            return None
        _gtoken = await get_valid_token(
            user_id=user_id,
            tokens=tokens,
            client_id=client_id,
            client_secret=client_secret,
        )
        return _gtoken

    # Google Sheets
    if new_leads and google_sheet_id:
        try:
            token = await _google_token()
            if token:
                n = await sheets_notify.append_leads(
                    sheet_id=google_sheet_id,
                    access_token=token,
                    leads=new_leads,
                )
                await _log(run_id, "info", f"Wrote {n} row(s) to Google Sheet")
            else:
                await _log(run_id, "warning", "Google Sheets: no valid token — skipped")
        except Exception as exc:
            await _log(run_id, "warning", f"Google Sheets failed: {exc}")

    # Gmail
    if new_leads and notify_gmail and user_id:
        try:
            token = await _google_token()
            if token:
                sender = await db.get_user_email(user_id) or ""
                await gmail_api.send_digest(
                    to=sender,
                    sender_email=sender,
                    automation_name=automation["name"],
                    leads=new_leads,
                    access_token=token,
                )
                await _log(run_id, "info", f"Gmail digest sent to {sender}")
            else:
                await _log(run_id, "warning", "Gmail: no valid token — skipped")
        except Exception as exc:
            await _log(run_id, "warning", f"Gmail failed: {exc}")

    # Update schedule
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    cron = croniter(automation["schedule_cron"], datetime.now(timezone.utc))
    next_dt = cron.get_next(datetime)
    next_ms = int(next_dt.timestamp() * 1000)

    await db.finish_run(
        run_id,
        status="error" if errors and items_kept == 0 else "success",
        items_seen=items_seen,
        items_kept=items_kept,
        errors=errors or None,
    )
    await db.update_automation_schedule(
        automation_id, last_run_at=now_ms, next_run_at=next_ms
    )
    await _log(
        run_id, "success",
        f"Done. Next run: {next_dt.strftime('%Y-%m-%d %H:%M UTC')}"
    )


async def _fetch_items(
    get_tab,
    *,
    domain: str,
    vertical: str,
    spec: dict,
    run_id: str,
    intent_text: str | None = None,
) -> list[dict]:
    """Route to the right adapter; fall back to scout for unknown domains.

    Scout discovery ladder:
      1. Try `https://{domain}` (cheap fast path for sites that are list-y)
      2. Ask LLM for likely listing paths, try each
      3. Crawl home page <a href> links, score by vertical keywords, try top
    The URL that finally produces a spec is saved as `entry_url` in the spec
    so subsequent runs go straight there.
    """
    from worker.adapters import remoteok, upwork

    # Pre-built browser-free adapters
    if domain == remoteok.DOMAIN:
        return await remoteok.fetch_items()

    if domain == upwork.DOMAIN and vertical == upwork.VERTICAL:
        query = spec.get("query") or " ".join(spec.get("criteria", []))
        return await upwork.fetch_items(await _require_tab(get_tab, run_id, domain), search_query=query)

    # Cached spec — short-circuit
    site_spec = await db.get_site_spec(domain, vertical)
    if site_spec and site_spec.get("user_confirmed"):
        tier_spec = json.loads(site_spec["spec_json"])
        if site_spec["tier"] == "api":
            return await _fetch_via_api_spec(await _require_tab(get_tab, run_id, domain), domain, tier_spec)
        if site_spec["tier"] == "jsonld":
            return await _fetch_via_jsonld_spec(
                await _require_tab(get_tab, run_id, domain), domain, tier_spec, run_id=run_id
            )
        # vision / vision_v2 specs share the (card_selector, fields) shape with
        # pydantic specs, so the same extractor handles all three. The extractor
        # checks tier internally to decide whether to apply the strict-class filter.
        if site_spec["tier"] in ("pydantic", "vision", "vision_v2"):
            return await _fetch_via_pydantic_spec(
                await _require_tab(get_tab, run_id, domain), domain, tier_spec, run_id=run_id
            )

    backend = SCOUT_BACKEND
    await _log(run_id, "info", f"{domain}: no confirmed spec, running scout (backend={backend})…")
    tab = await _require_tab(get_tab, run_id, domain)
    home_url = f"https://{domain}"

    # Choose scout backend. `vision` uses Gemini bbox grounding;
    # `pydantic` (default) uses the legacy heuristic + LLM-pick scout.
    _heavy_scout = _try_vision_scout_at if backend == "vision" else _try_scout_at

    async def scout_at(tab, *, domain, url, vertical, run_id, intent_text=None):
        # Cheapest try-path first: schema.org ItemList JSON-LD. Many SEO-
        # conscious sites (IMDB charts, recipes, e-commerce search) embed it
        # and we can extract directly with zero detection.
        jsonld_items = await _try_jsonld_at(
            tab, domain=domain, url=url, vertical=vertical, run_id=run_id
        )
        if jsonld_items is not None:
            return jsonld_items
        return await _heavy_scout(
            tab, domain=domain, url=url, vertical=vertical,
            run_id=run_id, intent_text=intent_text,
        )

    # ── Stage 1: home URL ────────────────────────────────────────────────
    try:
        items = await scout_at(tab, domain=domain, url=home_url, vertical=vertical, run_id=run_id, intent_text=intent_text)
    except HostUnreachable as exc:
        # Host is dead — no point trying LLM-suggested or sublink URLs on
        # the same domain. Bail immediately to save the rest of the run.
        await _log(run_id, "warning", f"{domain}: host unreachable — skipping ({exc})")
        return []
    if items is not None:
        return items

    # ── Stage 2: LLM-suggested listing paths ─────────────────────────────
    suggested = await llm_suggest_paths(domain, vertical, intent_text)
    if suggested:
        await _log(run_id, "info", f"{domain}: home empty, trying LLM-suggested paths: {', '.join(suggested)}")
        for url in suggested:
            try:
                items = await scout_at(tab, domain=domain, url=url, vertical=vertical, run_id=run_id, intent_text=intent_text)
            except HostUnreachable:
                # If even one alternate URL on this host is unreachable, the
                # host is dead. Stop trying its siblings.
                await _log(run_id, "warning", f"{domain}: alternate URL unreachable — abandoning domain")
                return []
            if items is not None:
                return items

    # ── Stage 3: sublink crawl from the home page ────────────────────────
    # Re-navigate home so the link extraction runs against a known page.
    try:
        from worker.browser import navigate, wait_for_content
        import asyncio as _asyncio
        await _asyncio.wait_for(navigate(tab, home_url), timeout=60.0)
        await _asyncio.wait_for(wait_for_content(tab, max_wait=15.0), timeout=20.0)
    except Exception as exc:
        await _log(run_id, "warning", f"{domain}: home re-nav for sublink crawl failed: {exc}")
    else:
        sublinks = await crawl_home_sublinks(tab, domain=domain, vertical=vertical)
        if sublinks:
            await _log(run_id, "info", f"{domain}: trying sublinks from home: {', '.join(sublinks)}")
            for url in sublinks:
                try:
                    items = await scout_at(tab, domain=domain, url=url, vertical=vertical, run_id=run_id, intent_text=intent_text)
                except HostUnreachable:
                    await _log(run_id, "warning", f"{domain}: sublink unreachable — abandoning domain")
                    return []
                if items is not None:
                    return items

    await _log(run_id, "warning", f"{domain}: scout exhausted all candidates — skipping this source")
    return []


class HostUnreachable(Exception):
    """Raised by _try_scout_at when the URL itself can't load (DNS, timeout,
    connection refused). Distinct from "loaded fine but no cards" so the
    caller can skip the rest of the discovery ladder for this domain.
    """


_DEAD_HOST_MARKERS = (
    "ERR_CONNECTION_TIMED_OUT",
    "ERR_NAME_NOT_RESOLVED",
    "ERR_CONNECTION_REFUSED",
    "ERR_CONNECTION_RESET",
    "ERR_INTERNET_DISCONNECTED",
    "ERR_ADDRESS_UNREACHABLE",
    "Navigation failed after",  # our own retry-exhausted message
    "page load hard-timed-out",
)


def _is_dead_host(exc: BaseException) -> bool:
    s = str(exc)
    return any(m in s for m in _DEAD_HOST_MARKERS)


async def _try_scout_at(
    tab,
    *,
    domain: str,
    url: str,
    vertical: str,
    run_id: str,
    intent_text: str | None = None,
) -> list[dict] | None:
    """Run Tier-1 then Tier-2 against a single URL. On Tier-2 success, also
    expand to other candidate URLs (LLM-suggested + sublinks) using the SAME
    selectors — hub sites like scholarshipdb.net often share one card spec
    across many filtered list pages. Returns aggregated items on success or
    None on failure so the caller can try the next candidate.

    Raises HostUnreachable when navigation itself failed (host is down,
    DNS broken, etc.) — caller should skip remaining URLs on this domain
    rather than burn through the discovery ladder for nothing.
    """
    nav_failed_count = 0
    try:
        tier1 = await network_sniff.scout(tab, url=url, vertical=vertical)
    except Exception as exc:
        await _log(run_id, "warning", f"{domain}: Tier-1 at {url} errored: {exc}")
        if _is_dead_host(exc):
            nav_failed_count += 1
        tier1 = None
    if tier1:
        tier1["entry_url"] = url
        await db.upsert_site_spec(domain, vertical, "api", tier1, user_confirmed=True)
        await _log(run_id, "info", f"{domain}: Tier-1 spec found at {url} — extracting")
        return await _fetch_via_api_spec(tab, domain, tier1)

    try:
        tier2 = await pydantic_scout.scout(tab, url=url, vertical=vertical)
    except Exception as exc:
        await _log(run_id, "warning", f"{domain}: Tier-2 at {url} errored: {exc}")
        if _is_dead_host(exc):
            nav_failed_count += 1
        tier2 = None

    # Both tiers failed AND both failed because the URL didn't load → the
    # host itself is unreachable. Don't try sibling URLs on the same domain.
    if tier1 is None and tier2 is None and nav_failed_count >= 2:
        raise HostUnreachable(f"{domain}: {url} unreachable")

    if tier2:
        # Quality check: extract a sample with this spec. The Tier-2 detector
        # can pick tag-cloud or nav-link groups when the page has no real
        # listings (e.g. home-page hero with a "browse by topic" widget). If
        # the items look like one-word filter links, reject the spec so the
        # discovery layer tries the next URL.
        tier2_with_url = {**tier2, "entry_url": url}
        try:
            sample = await _extract_pydantic_at_url(tab, url, tier2_with_url)
        except Exception:
            sample = []
        if not _looks_like_listings(sample):
            await _log(
                run_id, "info",
                f"{domain}: spec at {url} produced {len(sample)} low-quality items "
                f"(avg title too short — likely tag-cloud) — trying next URL"
            )
            return None
        # Expand: try the same selectors at related URLs and keep the ones
        # that produce items. Capped to avoid runaway lead volume.
        entry_urls = await _expand_with_same_spec(
            tab,
            domain=domain,
            vertical=vertical,
            successful_url=url,
            spec=tier2,
            intent_text=intent_text,
            run_id=run_id,
            cap=5,
        )
        tier2["entry_url"] = url  # back-compat for older readers
        tier2["entry_urls"] = entry_urls
        await db.upsert_site_spec(domain, vertical, "pydantic", tier2, user_confirmed=True)
        await _log(
            run_id, "info",
            f"{domain}: Tier-2 spec found — extracting from {len(entry_urls)} URL(s)"
        )
        return await _fetch_via_pydantic_spec(tab, domain, tier2, run_id=run_id)

    return None


async def _try_vision_scout_at(
    tab,
    *,
    domain: str,
    url: str,
    vertical: str,
    run_id: str,
    intent_text: str | None = None,
) -> list[dict] | None:
    """Vision-scout variant of `_try_scout_at`.

    Uses `vision_scout_v2`: screenshot → Gemini bboxes → DOM snippets at each
    centroid → second Gemini call returns CSS spec (card + title + url
    selectors). v2 is strictly better than v1's JS heuristic on every site
    where Gemini is responsive (proven via bench).

    Same return contract: items on success, None on "try the next URL",
    HostUnreachable when the host itself is dead.
    """
    from worker.ai import gemini_client as _gem

    try:
        spec = await vision_scout_v2.scout(tab, url=url, vertical=vertical)
    except Exception as exc:
        await _log(run_id, "warning", f"{domain}: vision scout at {url} errored: {exc}")
        if _is_dead_host(exc):
            raise HostUnreachable(f"{domain}: {url} unreachable") from exc
        return None

    if not spec:
        # Surface why if Gemini's selector call failed.
        err = _gem.LAST_SELECTOR_ERROR
        if err:
            await _log(run_id, "info", f"{domain}: vision at {url} → no spec ({err})")
        return None

    spec_with_url = {**spec, "entry_url": url}
    try:
        sample = await _extract_pydantic_at_url(tab, url, spec_with_url)
    except Exception:
        sample = []
    if not _looks_like_listings(sample):
        await _log(
            run_id, "info",
            f"{domain}: vision spec at {url} produced {len(sample)} low-quality items "
            f"— trying next URL"
        )
        return None

    spec["entry_url"] = url
    spec["entry_urls"] = [url]
    await db.upsert_site_spec(domain, vertical, "vision_v2", spec, user_confirmed=True)
    await _log(
        run_id, "info",
        f"{domain}: vision_v2 spec saved (selector: {spec.get('card_selector')!r}) — "
        f"extracting"
    )
    return await _fetch_via_pydantic_spec(tab, domain, spec, run_id=run_id)


async def _expand_with_same_spec(
    tab,
    *,
    domain: str,
    vertical: str,
    successful_url: str,
    spec: dict,
    intent_text: str | None,
    run_id: str,
    cap: int,
) -> list[str]:
    """After Tier-2 scout succeeds at `successful_url`, probe related URLs
    with the same card_selector/fields. Keep URLs that yield at least one
    item. Returns the working URLs (always includes successful_url first).

    Cap bounds total navigations: 1 (success) + cap-1 (probes).
    """
    working: list[str] = [successful_url]
    if cap <= 1:
        return working

    candidates: list[str] = []
    # 1. LLM-suggested paths (these are intent-aware)
    try:
        suggested = await llm_suggest_paths(domain, vertical, intent_text)
        candidates.extend(suggested)
    except Exception:
        suggested = []

    # 2. Sublinks from the successful URL (we're already on that page after scout)
    try:
        sublinks = await crawl_home_sublinks(tab, domain=domain, vertical=vertical, max_links=8)
        candidates.extend(sublinks)
    except Exception:
        sublinks = []

    # Dedupe, drop the URL we already have
    seen: set[str] = {successful_url}
    probes: list[str] = []
    for u in candidates:
        if u in seen:
            continue
        seen.add(u)
        probes.append(u)

    for url in probes:
        if len(working) >= cap:
            break
        try:
            items = await _extract_pydantic_at_url(tab, url, spec)
        except Exception as exc:
            await _log(run_id, "info", f"{domain}: probe {url} errored: {exc}")
            continue
        if items:
            working.append(url)
            await _log(run_id, "info", f"{domain}: probe {url} → {len(items)} item(s) ✓")
        # Silently skip 0-item probes — they're usually navigation menus,
        # account pages, etc. Logging them clutters run history.

    return working


async def _require_tab(get_tab, run_id: str, domain: str):
    """Start the browser tab, logging a clear error if pydoll is unavailable."""
    try:
        return await get_tab()
    except ModuleNotFoundError as exc:
        msg = f"{domain}: browser not available in this environment ({exc}) — skipping"
        await _log(run_id, "warning", msg)
        raise RuntimeError(msg) from exc


async def _fetch_via_api_spec(tab, domain: str, spec: dict) -> list[dict]:
    """Call the discovered API endpoint, walk to the items array, flatten
    each item using the spec's `fields` mapping into {id,title,url,...}.
    """
    endpoint = spec["endpoint"]
    resp = await tab.request.get(endpoint, headers={"Accept": "application/json"})
    data = resp.json()
    for key in (spec.get("item_path") or "").split("."):
        if key and isinstance(data, dict):
            data = data.get(key, {})
    if not isinstance(data, list):
        return []

    fields: dict = spec.get("fields") or {}
    out: list[dict] = []
    for raw in data:
        if not isinstance(raw, dict):
            continue
        flat = {name: _walk_path(raw, path) for name, path in fields.items() if path}
        # Always preserve raw payload so the ranker sees full context
        merged = {**raw, **{k: v for k, v in flat.items() if v is not None}}
        # Coerce id to string for stable upserts
        if merged.get("id") is not None:
            merged["id"] = str(merged["id"])
        out.append(merged)
    return out


def _walk_path(obj, path: str):
    """Walk a dot-path through nested dicts/lists. Returns None on miss."""
    if not path:
        return obj
    cur = obj
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


async def _try_jsonld_at(
    tab,
    *,
    domain: str,
    url: str,
    vertical: str,
    run_id: str,
) -> list[dict] | None:
    """Try the JSON-LD ItemList extractor at `url`. On success (≥3 items that
    pass the listings heuristic), save a `jsonld` spec, paginate up to
    MAX_ITEMS_PER_SOURCE, and return the aggregate. Returns None to fall
    through to the heavier scout backend.

    Raises HostUnreachable if the URL itself can't load (same contract as the
    other scout paths).
    """
    try:
        items = await jsonld_extract.try_extract(tab, url)
    except Exception as exc:
        if _is_dead_host(exc):
            raise HostUnreachable(f"{domain}: {url} unreachable") from exc
        await _log(run_id, "warning", f"{domain}: JSON-LD probe at {url} errored: {exc}")
        return None

    if len(items) < 3 or not _looks_like_listings(items):
        return None

    spec = {"tier": "jsonld", "entry_url": url, "entry_urls": [url]}
    await db.upsert_site_spec(domain, vertical, "jsonld", spec, user_confirmed=True)
    await _log(
        run_id, "info",
        f"{domain}: JSON-LD ItemList found at {url} ({len(items)} items) — using it"
    )

    async def _extract(u: str) -> list[dict]:
        return await jsonld_extract.try_extract(tab, u)

    return await _paginate_extract(
        base_url=url,
        initial_items=items,
        extract_fn=_extract,
        domain=domain,
        run_id=run_id,
    )


async def _fetch_via_jsonld_spec(
    tab, domain: str, spec: dict, *, run_id: str
) -> list[dict]:
    """Cached `jsonld` spec runner. Iterates entry_urls (one in practice for
    JSON-LD), paginates each, caps at MAX_ITEMS_PER_SOURCE."""
    urls = spec.get("entry_urls") or [spec.get("entry_url") or f"https://{domain}"]
    aggregated: list[dict] = []
    seen: set[str] = set()

    async def _extract(u: str) -> list[dict]:
        return await jsonld_extract.try_extract(tab, u)

    for url in urls:
        remaining = MAX_ITEMS_PER_SOURCE - len(aggregated)
        if remaining <= 0:
            break
        try:
            initial = await _extract(url)
        except Exception as exc:
            await _log(run_id, "warning", f"{domain}: JSON-LD at {url} failed: {exc}")
            continue
        page_items = await _paginate_extract(
            base_url=url,
            initial_items=initial,
            extract_fn=_extract,
            domain=domain,
            run_id=run_id,
            max_items=remaining,
        )
        for it in page_items:
            key = it.get("url") or it.get("id") or it.get("title") or ""
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            aggregated.append(it)
            if len(aggregated) >= MAX_ITEMS_PER_SOURCE:
                break
    return aggregated[:MAX_ITEMS_PER_SOURCE]


def _next_page_url(base_url: str, page: int) -> str | None:
    """Apply `?page=N` to a URL. Replaces the existing `page` query param if
    present, appends otherwise. Returns None if the URL won't parse.
    """
    from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
    try:
        p = urlparse(base_url)
        qs = dict(parse_qsl(p.query, keep_blank_values=True))
        qs["page"] = str(page)
        return urlunparse(p._replace(query=urlencode(qs)))
    except Exception:
        return None


async def _paginate_extract(
    *,
    base_url: str,
    initial_items: list[dict],
    extract_fn,
    domain: str,
    run_id: str,
    max_items: int = MAX_ITEMS_PER_SOURCE,
    max_pages: int = MAX_PAGES_PER_URL,
) -> list[dict]:
    """Aggregate items from `base_url` then `base_url?page=2..N`, stopping when
    a page returns 0 new items or we hit `max_items`. `extract_fn` takes a URL
    and returns list[dict].

    Stop conditions (any):
      - len(aggregated) >= max_items
      - extract_fn returned empty list
      - extract_fn returned only items we've already seen (page didn't paginate)
      - page index hit max_pages
    """
    aggregated: list[dict] = []
    seen_keys: set[str] = set()

    def _ingest(items: list[dict]) -> int:
        added = 0
        for it in items:
            key = it.get("url") or it.get("id") or it.get("title") or ""
            if key and key in seen_keys:
                continue
            if key:
                seen_keys.add(key)
            aggregated.append(it)
            added += 1
            if len(aggregated) >= max_items:
                return added
        return added

    _ingest(initial_items)
    if not initial_items or len(aggregated) >= max_items:
        return aggregated[:max_items]

    for page in range(2, max_pages + 1):
        if len(aggregated) >= max_items:
            await _log(run_id, "info", f"{domain}: hit {max_items}-item cap — stopping pagination")
            break
        page_url = _next_page_url(base_url, page)
        if page_url is None:
            break
        try:
            page_items = await extract_fn(page_url)
        except Exception as exc:
            await _log(run_id, "info", f"{domain}: page {page} errored: {exc}")
            break
        if not page_items:
            await _log(run_id, "info", f"{domain}: page {page} empty — pagination done")
            break
        added = _ingest(page_items)
        if added == 0:
            await _log(run_id, "info", f"{domain}: page {page} all duplicates — pagination done")
            break
        await _log(
            run_id, "info",
            f"{domain}: page {page} → +{added} item(s) (total {len(aggregated)})"
        )

    return aggregated[:max_items]


async def _fetch_via_pydantic_spec(
    tab, domain: str, spec: dict, *, run_id: str = ""
) -> list[dict]:
    """Iterate the spec's `entry_urls` (set by the discovery + expansion
    layer), paginate each, cap at MAX_ITEMS_PER_SOURCE across the source.
    Falls back to legacy single-URL specs (entry_url, or bare domain).
    """
    urls = spec.get("entry_urls") or [spec.get("entry_url") or f"https://{domain}"]
    aggregated: list[dict] = []
    seen_keys: set[str] = set()

    async def _extract(u: str) -> list[dict]:
        return await _extract_pydantic_at_url(tab, u, spec)

    for url in urls:
        remaining = MAX_ITEMS_PER_SOURCE - len(aggregated)
        if remaining <= 0:
            break
        try:
            initial = await _extract(url)
        except Exception as exc:
            # One bad URL doesn't kill the source — keep going.
            print(f"[runner] {domain}: extraction at {url} failed: {exc}", flush=True)
            continue
        page_items = await _paginate_extract(
            base_url=url,
            initial_items=initial,
            extract_fn=_extract,
            domain=domain,
            run_id=run_id,
            max_items=remaining,
        )
        for it in page_items:
            key = it.get("url") or it.get("id") or ""
            if key and key in seen_keys:
                continue
            if key:
                seen_keys.add(key)
            aggregated.append(it)
            if len(aggregated) >= MAX_ITEMS_PER_SOURCE:
                break
    return aggregated[:MAX_ITEMS_PER_SOURCE]


async def _extract_pydantic_at_url(tab, url: str, spec: dict) -> list[dict]:
    """Navigate to `url` and run the spec's selectors against the loaded DOM.
    Returns a list of {title, url, ...field} dicts. Raises RuntimeError on
    nav timeout so the caller can move on.
    """
    import asyncio
    from worker.browser import navigate, wait_for_content

    try:
        await asyncio.wait_for(navigate(tab, url), timeout=60.0)
        await asyncio.wait_for(wait_for_content(tab, max_wait=20.0), timeout=25.0)
    except asyncio.TimeoutError as exc:
        raise RuntimeError(f"page load hard-timed-out: {url}") from exc

    card_sel = spec.get("card_selector")
    fields: dict = spec.get("fields") or {}
    if not card_sel or not fields:
        return []

    # vision_v2 specs come from a Gemini call that saw the full DOM and picked
    # an item-specific selector. We trust it — don't re-apply the strict-class
    # filter and parent-grouping heuristic that v1 needs.
    trust_selector = "true" if spec.get("tier") == "vision_v2" else "false"

    js = f"""
    const cardSel = {json.dumps(card_sel)};
    const fields = {json.dumps(fields)};
    const trustSelector = {trust_selector};
    function parsePart(p) {{
      const m = p.match(/^([a-z0-9*-]+)((?:\\.[^.\\s>]+)*)$/i);
      if (!m) return null;
      return {{ tag: m[1].toLowerCase(), classes: (m[2] || '').split('.').filter(Boolean) }};
    }}
    function classSetEqual(el, classes) {{
      const ec = Array.from(el.classList).filter(Boolean);
      if (ec.length !== classes.length) return false;
      for (const c of classes) if (!ec.includes(c)) return false;
      return true;
    }}
    const all = Array.from(document.querySelectorAll(cardSel));
    let cards;
    if (trustSelector) {{
      cards = all;
    }} else {{
      const parts = cardSel.split(/\\s*>\\s*/);
      const childP = parsePart(parts[parts.length - 1]) || {{tag:'*', classes:[]}};
      const parentP = parts.length > 1 ? parsePart(parts[0]) : null;
      const strict = all.filter(m => {{
        if (childP.classes.length && !classSetEqual(m, childP.classes)) return false;
        if (parentP && parentP.classes.length) {{
          if (!m.parentElement) return false;
          if (!classSetEqual(m.parentElement, parentP.classes)) return false;
        }}
        return true;
      }});
      const byParent = new Map();
      for (const m of strict) {{
        const p = m.parentElement; if (!p) continue;
        if (!byParent.has(p)) byParent.set(p, []);
        byParent.get(p).push(m);
      }}
      cards = strict;
      let bestN = 0;
      for (const list of byParent.values()) {{
        if (list.length > bestN) {{ cards = list; bestN = list.length; }}
      }}
    }}
    const out = cards.map(card => {{
      const row = {{}};
      for (const [name, conf] of Object.entries(fields)) {{
        if (!conf) continue;
        let el = null;
        if (!conf.selector) {{
          // Empty selector means "the card itself" — used when the AI says
          // the title/url lives on an attribute of the card element.
          el = card;
        }} else {{
          try {{ el = card.querySelector(conf.selector); }} catch (e) {{ el = null; }}
        }}
        if (!el) continue;
        let v = conf.attr ? el.getAttribute(conf.attr) : el.textContent;
        if (typeof v === 'string') {{
          v = v.replace(/\\s+/g, ' ').trim();
          const isUrlAttr = conf.attr === 'href' || /url$/i.test(conf.attr || '');
          if (isUrlAttr && v && !/^https?:/i.test(v)) {{
            try {{ v = new URL(v, location.href).href; }} catch (e) {{}}
          }}
        }}
        if (v) row[name] = v;
      }}
      return row;
    }}).filter(r => r.title || r.url);
    return JSON.stringify(out);
    """
    try:
        raw = await asyncio.wait_for(
            tab.execute_script(js, return_by_value=True),
            timeout=15.0,
        )
    except asyncio.TimeoutError as exc:
        raise RuntimeError(f"extraction script timed out: {url}") from exc
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

    # Ensure stable ids so dedupe works across runs
    for it in items:
        if not it.get("id"):
            it["id"] = it.get("url") or ""
        else:
            it["id"] = str(it["id"])
    return items


async def _log(run_id: str, level: str, message: str) -> None:
    await db.append_run_log(run_id, level, message)


_BROWSER_DEAD_MARKERS = (
    "browser is not running",
    "remote computer refused",
    "ConnectionRefusedError",
    "Chrome wedged",
    "hard-timed-out",
    "FailedToStartBrowser",
    "browser closed",
)


def _is_browser_failure(exc: BaseException) -> bool:
    """Heuristic: did this exception come from a dead Chrome process?"""
    s = repr(exc)
    return any(m.lower() in s.lower() for m in _BROWSER_DEAD_MARKERS)


def _looks_like_listings(items: list[dict]) -> bool:
    """Heuristic check that scout latched onto real cards, not tag clouds.

    Real listing cards (jobs, scholarships, products) have rich titles
    averaging 25+ characters — typically a multi-word product/role/topic
    plus a brand/university/company. Tag-cloud links have short one-word
    titles ("biology", "engineering"). Nav menus have short labels too.

    Returns True if items look card-shaped enough to keep, False if we
    should reject the spec and try the next candidate URL.
    """
    if len(items) < 3:
        return False
    titles = [(i.get("title") or "").strip() for i in items]
    titles = [t for t in titles if t]
    if len(titles) < 3:
        return False
    avg_len = sum(len(t) for t in titles) / len(titles)
    multi_word = sum(1 for t in titles if len(t.split()) >= 3)
    if avg_len >= 25 or multi_word >= len(titles) * 0.6:
        return True
    # Short-title path (movies, products, songs): if Gemini-grade extraction
    # produced ≥5 items, most have URLs, and titles are distinct (rules out
    # nav menus with repeating items like "Login | Login | Login"), accept.
    urls = [(i.get("url") or "").strip() for i in items]
    urls = [u for u in urls if u]
    url_ratio = len(urls) / len(items)
    distinct_titles = len({t.lower() for t in titles})
    if (
        len(items) >= 5
        and url_ratio >= 0.8
        and distinct_titles >= len(titles) * 0.8
        and avg_len >= 5
    ):
        return True
    return False
