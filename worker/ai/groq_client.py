"""Groq client with key rotation, tenacity retry, and observability hooks.

Keys: comma-separated `GROQ_API_KEYS` (or single `GROQ_API_KEY`).

Failure modes handled:
  - 429 / rate-limit  -> rotate to the next key, retry with exponential backoff
  - 5xx               -> retry with exponential backoff on the same key
  - 403 (CF WAF)      -> trip the process-wide disabled flag and raise. All
                        callers fail fast after this; Groq's Cloudflare layer
                        blocks the whole datacenter IP, not the key, so
                        rotation is pointless.
  - 4xx (auth/bad)    -> raise immediately, no retry

Every call records a row in llm_calls (provider, model, tokens, cost, status)
via the observability shim, scoped by the contextvars set by the runner.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from worker.config import GROQ_API_KEYS, GROQ_MODEL, GROQ_REQUEST_INTERVAL
from worker.obs.logging import get_logger
from worker.obs.metrics import observe_llm_call

log = get_logger("worker.ai.groq")

_key_index = 0
_last_call_time = 0.0
# Cloudflare WAF 403 is per-IP, not per-key. Trip once -> every subsequent
# caller raises immediately so the ranker fallback (Gemini) takes over with
# no per-call latency penalty.
_disabled_reason: str | None = None


def strip_code_fences(text: str) -> str:
    """Remove a single ```lang ... ``` markdown fence from an LLM response."""
    if not text:
        return text
    s = text.strip()
    if not s.startswith("```"):
        return s
    s = s[3:]
    nl = s.find("\n")
    if nl != -1:
        first_line = s[:nl].strip().lower()
        if first_line and all(c.isalnum() or c in "+-_" for c in first_line):
            s = s[nl + 1:]
    if "```" in s:
        s = s.rsplit("```", 1)[0]
    return s.strip()


def _current_key() -> str:
    return GROQ_API_KEYS[_key_index % len(GROQ_API_KEYS)]


def _rotate() -> None:
    global _key_index
    _key_index += 1


class _HardFail(Exception):
    """Wraps non-retryable exceptions (4xx auth, CF 403) so tenacity stops."""

    def __init__(self, inner: BaseException):
        super().__init__(str(inner))
        self.inner = inner


def _should_retry(exc: BaseException) -> bool:
    """True for rate-limit + transient 5xx, False for everything else.

    _HardFail bypasses retry — tenacity sees the wrapper and gives up.
    """
    if isinstance(exc, _HardFail):
        return False
    s = str(exc).lower()
    if "403" in s or "forbidden" in s:
        return False
    if "429" in s or "rate" in s:
        return True
    if any(code in s for code in ("500", "502", "503", "504")):
        return True
    return False


async def chat(
    prompt: str,
    *,
    system: str = "You are a helpful assistant. Respond with valid JSON only.",
    max_tokens: int = 2048,
    temperature: float = 0.1,
    purpose: str = "generic",
) -> str:
    """Tenacity-backed Groq call with key rotation + cost tracking.

    Raises RuntimeError("groq disabled: ...") if the process-wide kill switch
    has been tripped by a prior CF 403.
    """
    global _last_call_time, _disabled_reason

    if not GROQ_API_KEYS:
        raise RuntimeError("Set GROQ_API_KEYS or GROQ_API_KEY in the environment")
    if _disabled_reason:
        raise RuntimeError(f"groq disabled: {_disabled_reason}")

    from groq import AsyncGroq  # lazy import — keeps test env light

    async def _attempt() -> str:
        global _last_call_time, _disabled_reason
        # Honour the per-key request-spacing (Groq's free tier is RPM-limited)
        elapsed = time.time() - _last_call_time
        if elapsed < GROQ_REQUEST_INTERVAL:
            await asyncio.sleep(GROQ_REQUEST_INTERVAL - elapsed)

        start = time.time()
        client = AsyncGroq(api_key=_current_key())
        try:
            response = await client.chat.completions.create(
                model=GROQ_MODEL,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            )
            _last_call_time = time.time()
            latency_ms = int((_last_call_time - start) * 1000)
            usage = getattr(response, "usage", None)
            tokens_in = getattr(usage, "prompt_tokens", 0) if usage else 0
            tokens_out = getattr(usage, "completion_tokens", 0) if usage else 0
            await observe_llm_call(
                provider="groq", model=GROQ_MODEL, purpose=purpose,
                tokens_in=tokens_in, tokens_out=tokens_out,
                latency_ms=latency_ms, status="success",
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:
            _last_call_time = time.time()
            latency_ms = int((_last_call_time - start) * 1000)
            s = str(exc)
            if "403" in s or "forbidden" in s.lower():
                _disabled_reason = f"403 from host (CF WAF IP block): {s[:120]}"
                await observe_llm_call(
                    provider="groq", model=GROQ_MODEL, purpose=purpose,
                    latency_ms=latency_ms, status="error", error=s[:300],
                )
                raise _HardFail(exc) from exc
            if "429" in s or "rate" in s.lower():
                _rotate()
                await observe_llm_call(
                    provider="groq", model=GROQ_MODEL, purpose=purpose,
                    latency_ms=latency_ms, status="retry", error=s[:300],
                )
            else:
                await observe_llm_call(
                    provider="groq", model=GROQ_MODEL, purpose=purpose,
                    latency_ms=latency_ms, status="error", error=s[:300],
                )
            raise

    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            retry=retry_if_exception(_should_retry),
            reraise=True,
        ):
            with attempt:
                return await _attempt()
    except RetryError as re:
        raise re.last_attempt.exception() or RuntimeError("Groq: retries exhausted")
    except _HardFail as hf:
        raise hf.inner
    raise RuntimeError("Groq: unreachable")
