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
from worker.browser import make_chrome
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

    browser = make_chrome()
    tab = await browser.start()
    try:
        for domain in sources:
            try:
                items = await _fetch_items(
                    tab,
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
    finally:
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
    tab,
    *,
    domain: str,
    vertical: str,
    spec: dict,
    run_id: str,
) -> list[dict]:
    """Route to the right adapter; fall back to scout for unknown domains."""
    from worker.adapters import remoteok, upwork

    # Pre-built adapters
    if domain == remoteok.DOMAIN:
        return await remoteok.fetch_items()  # no browser needed

    if domain == upwork.DOMAIN and vertical == upwork.VERTICAL:
        query = spec.get("query") or " ".join(spec.get("criteria", []))
        return await upwork.fetch_items(tab, search_query=query)

    # Unknown domain — run the 3-tier scout
    site_spec = await db.get_site_spec(domain, vertical)

    if site_spec and site_spec.get("user_confirmed"):
        tier_spec = json.loads(site_spec["spec_json"])
        if site_spec["tier"] == "api":
            return await _fetch_via_api_spec(tab, domain, tier_spec)
        if site_spec["tier"] == "pydantic":
            return await _fetch_via_pydantic_spec(tab, domain, tier_spec)

    # Scout — Tier 1 then Tier 2
    await _log(run_id, "info", f"{domain}: no confirmed spec, running scout…")
    url = f"https://{domain}"

    tier1 = await network_sniff.scout(tab, url=url, vertical=vertical)
    if tier1:
        await db.upsert_site_spec(domain, vertical, "api", tier1)
        await _log(run_id, "info", f"{domain}: Tier-1 spec discovered — confirm in dashboard")
        return []

    tier2 = await pydantic_scout.scout(tab, url=url, vertical=vertical)
    if tier2:
        await db.upsert_site_spec(domain, vertical, "pydantic", tier2)
        await _log(run_id, "info", f"{domain}: Tier-2 spec discovered — confirm in dashboard")
        return []

    await _log(run_id, "warning", f"{domain}: scout found nothing — skipping this source")
    return []


async def _fetch_via_api_spec(tab, domain: str, spec: dict) -> list[dict]:
    endpoint = spec["endpoint"]
    resp = await tab.request.get(endpoint, headers={"Accept": "application/json"})
    data = resp.json()
    for key in (spec.get("item_path") or "").split("."):
        if key and isinstance(data, dict):
            data = data[key]
    return data if isinstance(data, list) else []


async def _fetch_via_pydantic_spec(tab, domain: str, spec: dict) -> list[dict]:
    raise NotImplementedError("Pydantic extraction wired in Day 3")


async def _log(run_id: str, level: str, message: str) -> None:
    await db.append_run_log(run_id, level, message)
