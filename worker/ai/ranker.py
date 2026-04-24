"""
Scores a scraped item against the automation's criteria (and optional CV).
Returns a float 1-10.
"""

from __future__ import annotations

import json

from worker.ai.groq_client import chat

_SYSTEM = """\
You are a relevance ranker. Given a job/product/scholarship listing and a set of
criteria, score the match from 1 (irrelevant) to 10 (perfect match).

Respond with a JSON object:
{
  "score": <number 1-10>,
  "reasons": ["<reason 1>", "<reason 2>"]
}
"""


async def rank(
    item: dict,
    *,
    criteria: list[str],
    vertical: str,
    cv_text: str | None = None,
    threshold: float = 6.0,
) -> tuple[float, list[str]]:
    """Return (score, reasons). Raises on LLM failure."""
    cv_section = f"\n\nCandidate CV summary:\n{cv_text}" if cv_text else ""
    prompt = (
        f"Vertical: {vertical}\n"
        f"Criteria: {json.dumps(criteria)}"
        f"{cv_section}\n\n"
        f"Listing:\n{json.dumps(item, ensure_ascii=False)[:3000]}"
    )
    raw = await chat(prompt, system=_SYSTEM)
    try:
        data = json.loads(raw)
        score = float(data["score"])
        reasons: list[str] = data.get("reasons", [])
        return score, reasons
    except Exception as exc:
        raise ValueError(f"Ranker: bad LLM response: {raw!r}") from exc
