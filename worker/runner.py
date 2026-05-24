"""
One automation run, end-to-end.
Called by main.py for each due automation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import nanoid  # type: ignore
from croniter import croniter  # type: ignore

from worker import db
from worker.ai.ranker import rank
from worker.browser import make_chrome, start_browser
from worker.notify.email import send_lead_digest
from worker.scout import network_sniff, pydantic_scout
from worker.scout.validate import is_healthy


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
                )
                items_seen += len(items)
                await _log(run_id, "info", f"{domain}: fetched {len(items)} items")

                if items and not is_healthy(items):
                    await _log(
                        run_id, "warning",
                        f"{domain}: low-quality extraction — spec may need re-scouting"
                    )

                for item in items:
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

    # Notify
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
) -> list[dict]:
    """Route to the right adapter; fall back to scout for unknown domains."""
    from worker.adapters import remoteok, upwork

    # Pre-built browser-free adapters
    if domain == remoteok.DOMAIN:
        return await remoteok.fetch_items()

    if domain == upwork.DOMAIN and vertical == upwork.VERTICAL:
        query = spec.get("query") or " ".join(spec.get("criteria", []))
        return await upwork.fetch_items(await _require_tab(get_tab, run_id, domain), search_query=query)

    # Unknown domain — run the 3-tier scout (needs browser)
    site_spec = await db.get_site_spec(domain, vertical)

    if site_spec and site_spec.get("user_confirmed"):
        tier_spec = json.loads(site_spec["spec_json"])
        if site_spec["tier"] == "api":
            return await _fetch_via_api_spec(await _require_tab(get_tab, run_id, domain), domain, tier_spec)
        if site_spec["tier"] == "pydantic":
            return await _fetch_via_pydantic_spec(await _require_tab(get_tab, run_id, domain), domain, tier_spec)

    # Scout — Tier 1 then Tier 2
    await _log(run_id, "info", f"{domain}: no confirmed spec, running scout…")
    url = f"https://{domain}"
    tab = await _require_tab(get_tab, run_id, domain)

    tier1 = await network_sniff.scout(tab, url=url, vertical=vertical)
    if tier1:
        await db.upsert_site_spec(domain, vertical, "api", tier1, user_confirmed=True)
        await _log(run_id, "info", f"{domain}: Tier-1 spec found — extracting now")
        return await _fetch_via_api_spec(tab, domain, tier1)

    tier2 = await pydantic_scout.scout(tab, url=url, vertical=vertical)
    if tier2:
        await db.upsert_site_spec(domain, vertical, "pydantic", tier2, user_confirmed=True)
        await _log(run_id, "info", f"{domain}: Tier-2 spec found — extracting now")
        return await _fetch_via_pydantic_spec(tab, domain, tier2)

    await _log(run_id, "warning", f"{domain}: scout found nothing — skipping this source")
    return []


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


async def _fetch_via_pydantic_spec(tab, domain: str, spec: dict) -> list[dict]:
    """Navigate to the source URL, query cards via the saved spec, extract
    each field with document.querySelector inside the card root.

    The whole call is wrapped in a 90s timeout so a wedged Chrome instance
    can't block the worker — the runner catches the resulting exception,
    logs it, and moves on to the next source.
    """
    import asyncio
    from worker.browser import navigate, wait_for_content

    url = f"https://{domain}"
    try:
        await asyncio.wait_for(navigate(tab, url), timeout=60.0)
        await asyncio.wait_for(wait_for_content(tab, max_wait=20.0), timeout=25.0)
    except asyncio.TimeoutError as exc:
        raise RuntimeError(f"{domain}: page load hard-timed-out") from exc

    card_sel = spec.get("card_selector")
    fields: dict = spec.get("fields") or {}
    if not card_sel or not fields:
        return []

    # Plain script with `return` — pydoll auto-wraps it into an IIFE for us.
    js = f"""
    const cardSel = {json.dumps(card_sel)};
    const fields = {json.dumps(fields)};
    const cards = Array.from(document.querySelectorAll(cardSel));
    const out = cards.map(card => {{
      const row = {{}};
      for (const [name, conf] of Object.entries(fields)) {{
        if (!conf || !conf.selector) continue;
        let el = null;
        try {{ el = card.querySelector(conf.selector); }} catch (e) {{ el = null; }}
        if (!el) continue;
        let v = conf.attr ? el.getAttribute(conf.attr) : el.textContent;
        if (typeof v === 'string') {{
          v = v.trim();
          if (conf.attr === 'href' && v && !/^https?:/i.test(v)) {{
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
        raise RuntimeError(f"{domain}: extraction script timed out") from exc
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
