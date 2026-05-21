"""
Groq client with multi-key rotation and per-key rate limiting.
Ported from upwork-research/analysis/pipeline.py.

Keys are loaded from GROQ_API_KEYS env var (comma-separated).
Falls back to GROQ_API_KEY for single-key setups.
"""

from __future__ import annotations

import asyncio
import time

from worker.config import GROQ_API_KEYS, GROQ_MODEL, GROQ_REQUEST_INTERVAL

_key_index = 0
_last_call_time = 0.0


def strip_code_fences(text: str) -> str:
    """Remove a single ```lang ... ``` markdown fence from an LLM response.

    Handles ``` and ```json forms, trims surrounding whitespace. Pass-through
    when no fence is present.
    """
    if not text:
        return text
    s = text.strip()
    if not s.startswith("```"):
        return s
    s = s[3:]
    # Drop optional language hint (json, javascript, etc.) on the first line
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


async def chat(
    prompt: str,
    *,
    system: str = "You are a helpful assistant. Respond with valid JSON only.",
    max_tokens: int = 2048,
    temperature: float = 0.1,
    retries: int = 3,
) -> str:
    """Rate-limited Groq call with key rotation on rate-limit errors."""
    global _last_call_time

    if not GROQ_API_KEYS:
        raise RuntimeError("Set GROQ_API_KEYS or GROQ_API_KEY in the environment")

    for attempt in range(retries):
        elapsed = time.time() - _last_call_time
        if elapsed < GROQ_REQUEST_INTERVAL:
            await asyncio.sleep(GROQ_REQUEST_INTERVAL - elapsed)

        from groq import AsyncGroq  # lazy — not needed in test env
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
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:
            _last_call_time = time.time()
            if "rate" in str(exc).lower() or "429" in str(exc):
                _rotate()
                if attempt < retries - 1:
                    continue
            raise
    raise RuntimeError("Groq: all retries exhausted")
