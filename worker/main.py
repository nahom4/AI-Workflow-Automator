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

try:
    from rich.console import Console as _Console
    console = _Console()
except ImportError:
    import re as _re

    class console:  # type: ignore[no-redef]
        @staticmethod
        def print(*args, **kwargs):
            text = " ".join(str(a) for a in args)
            print(_re.sub(r"\[/?[^\]]*\]", "", text))

from worker.config import POLL_INTERVAL
from worker.runner import run_automation
from worker import db
_shutdown = False


def _handle_signal(sig, frame):
    global _shutdown
    console.print(f"\n[yellow]Received signal {sig} — shutting down after current run...[/yellow]")
    _shutdown = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


async def main() -> None:
    console.print("[bold green]AI Workflow Automator — worker started[/bold green]")
    console.print(f"Poll interval: {POLL_INTERVAL}s")
    await db.ensure_schema()

    while not _shutdown:
        try:
            due = await db.fetch_due_automations()
            if due:
                console.print(f"[cyan]Found {len(due)} due automation(s)[/cyan]")
            for automation in due:
                if _shutdown:
                    break
                console.print(f"  Running: [bold]{automation['name']}[/bold] ({automation['id']})")
                try:
                    await run_automation(automation)
                    console.print(f"  [green]OK {automation['name']} completed[/green]")
                except Exception as exc:
                    console.print(f"  [red]FAIL {automation['name']}: {exc}[/red]")
                    await db.mark_automation_broken(automation["id"])
        except Exception as exc:
            console.print(f"[red]Poll error: {exc}[/red]")

        await asyncio.sleep(POLL_INTERVAL)

    console.print("[yellow]Worker stopped.[/yellow]")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
