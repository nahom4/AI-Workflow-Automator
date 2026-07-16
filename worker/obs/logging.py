"""Structured logging setup.

JSON output in prod (systemd journal aggregators / log shippers parse it
trivially), console-renderer in dev so humans can read it.

Usage in any module:

    from worker.obs.logging import get_logger
    log = get_logger(__name__)
    log.info("run_started", run_id=run_id, automation_id=automation_id)

Context that should appear on every line within a scope:

    from worker.obs.logging import bind_context
    with bind_context(run_id=run_id, automation_id=automation_id):
        log.info("scout_started")   # automatically carries run_id + automation_id
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import contextmanager
from typing import Any, Generator

import structlog


_CONFIGURED = False


def configure(*, force_json: bool | None = None) -> None:
    """Configure structlog once. Idempotent. JSON renderer when stdout is not
    a TTY (systemd, containers), console renderer in dev.

    Env overrides:
      LOG_FORMAT=json    -> force JSON
      LOG_FORMAT=console -> force console
      LOG_LEVEL=INFO     -> standard library log level
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_format = (os.getenv("LOG_FORMAT") or "").lower()
    if force_json is True:
        as_json = True
    elif force_json is False:
        as_json = False
    elif log_format == "json":
        as_json = True
    elif log_format == "console":
        as_json = False
    else:
        as_json = not sys.stdout.isatty()

    level_name = (os.getenv("LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    # stdlib logging -> structlog adapter, so groq SDK / httpx / pydoll logs
    # also flow through our JSON renderer.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if as_json:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _CONFIGURED = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    if not _CONFIGURED:
        configure()
    return structlog.get_logger(name) if name else structlog.get_logger()


@contextmanager
def bind_context(**kwargs: Any) -> Generator[None, None, None]:
    """Bind kwargs into structlog context for the duration of the block.

    Useful at the top of run_automation() — every log line inside the run
    automatically carries run_id, automation_id, user_id without each call
    repeating them.
    """
    tokens = structlog.contextvars.bind_contextvars(**kwargs)
    try:
        yield
    finally:
        structlog.contextvars.reset_contextvars(**tokens)


def clear_context() -> None:
    structlog.contextvars.clear_contextvars()
