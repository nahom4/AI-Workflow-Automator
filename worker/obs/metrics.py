"""Observability shim — every LLM call lands in `llm_calls` for cost/latency tracking.

The runner enters `bind_context(run_id=..., automation_id=..., user_id=...)`
at the top of `run_automation()`. We pull those identifiers off the
structlog contextvars so LLM client modules don't have to thread them
through every call site.

If recording fails (e.g. Turso unreachable mid-run), we swallow the error
and log it — losing a metrics row should not kill the actual workflow.
"""

from __future__ import annotations

from typing import Any

import structlog

from worker import db
from worker.obs.logging import get_logger
from worker.obs.pricing import estimate_cost_cents

_log = get_logger("worker.obs.metrics")


def _ctx_get(key: str) -> str | None:
    ctx = structlog.contextvars.get_contextvars()
    val = ctx.get(key)
    return str(val) if val is not None else None


async def observe_llm_call(
    *,
    provider: str,
    model: str,
    purpose: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    latency_ms: int = 0,
    status: str = "success",
    error: str | None = None,
) -> None:
    """Record one LLM call to the `llm_calls` table.

    Context (run_id, automation_id, user_id) is pulled off structlog
    contextvars set by `bind_context()` in the runner.
    """
    run_id = _ctx_get("run_id")
    automation_id = _ctx_get("automation_id")
    user_id = _ctx_get("user_id")
    cost_cents = estimate_cost_cents(model, tokens_in, tokens_out)

    _log.info(
        "llm_call",
        provider=provider,
        model=model,
        purpose=purpose,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_cents=round(cost_cents, 4),
        latency_ms=latency_ms,
        status=status,
    )

    try:
        await db.record_llm_call(
            run_id=run_id,
            automation_id=automation_id,
            user_id=user_id,
            provider=provider,
            model=model,
            purpose=purpose,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_cents=cost_cents,
            latency_ms=latency_ms,
            status=status,
            error=error,
        )
    except Exception as exc:  # noqa: BLE001
        # Never let metrics persistence break the workflow path.
        _log.warning("llm_call_record_failed", error=str(exc)[:200])
