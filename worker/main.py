"""
Worker entry point — polls Turso/SQLite for due automations and runs them.

Usage:
  python -m worker.main

On the VPS:
  xvfb-run -a python -m worker.main
"""

from __future__ import annotations

import asyncio
import signal
import sys

# Load .env.local (dev) then .env so config picks up GROQ_API_KEY, CHROME_BINARY, etc.
try:
    from dotenv import load_dotenv as _load
    _load(".env.local", override=False)
    _load(".env", override=False)
except ImportError:
    pass

from worker.obs.logging import configure as _configure_logging, get_logger
_configure_logging()
log = get_logger("worker.main")

from worker.config import POLL_INTERVAL
from worker.runner import run_automation
from worker import db

_shutdown = False


def _handle_signal(sig, frame):
    global _shutdown
    log.warning("worker_shutdown_signal", signal=sig)
    _shutdown = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


async def main() -> None:
    log.info("worker_started", poll_interval_seconds=POLL_INTERVAL)
    await db.ensure_schema()

    while not _shutdown:
        try:
            due = await db.fetch_due_automations()
            if due:
                log.info("poll_found_due", count=len(due))
            for automation in due:
                if _shutdown:
                    break
                log.info(
                    "automation_starting",
                    automation_id=automation["id"],
                    automation_name=automation["name"],
                )
                try:
                    await run_automation(automation)
                    log.info(
                        "automation_completed",
                        automation_id=automation["id"],
                        automation_name=automation["name"],
                    )
                except Exception as exc:
                    log.exception(
                        "automation_failed",
                        automation_id=automation["id"],
                        automation_name=automation["name"],
                        error=str(exc),
                    )
                    await db.mark_automation_broken(automation["id"])
        except Exception as exc:
            log.exception("poll_error", error=str(exc))

        await asyncio.sleep(POLL_INTERVAL)

    log.info("worker_stopped")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
