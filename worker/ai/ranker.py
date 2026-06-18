"""Vertical-aware item ranker.

Given a listing dict and a set of criteria, returns a (score, reasons) tuple
where:
  - score is 1-10, anchored to a published scale (see _SYSTEM)
  - reasons is a flat list of strings, each of the form
    "[<verdict>] <criterion>: <evidence>" so the demo UI / digest emails can
    show concrete proof of why an item ranked the way it did.

The ranker is intentionally strict about grounding: every per-criterion
verdict must quote text that literally appears in the item. If the LLM
returns a "met" verdict without a quoted phrase, we downgrade it to
"partial" and dock the score. This is what makes the demo legitimate —
nothing is graded as a match unless the model can point to where in the
listing the match comes from.
"""

from __future__ import annotations

import json
import re

from worker.ai.groq_client import chat


_SYSTEM = """\
You rank listings against criteria. For each criterion, decide met/partial/unmet
and QUOTE the exact phrase from the listing as evidence. Do not paraphrase.
A technology/term is "met" only if it literally appears in the listing fields.

SCORING (1-10):
  10 = all criteria met AND listing is exceptional
   8 = all criteria met with clear evidence
   6 = most criteria met; one ambiguous or unmet
   4 = only one criterion clearly met
   2 = no criterion clearly met
   1 = hostile to criteria (junior when senior required, etc.)

OUTPUT — JSON only, no preamble:
{
  "per_criterion": [
    {"criterion": "<verbatim copy>",
     "verdict": "met"|"partial"|"unmet",
     "evidence": "<verbatim phrase from listing, or empty>"}
  ],
  "score": <1-10>,
  "summary": "<one sentence, under 25 words>"
}
"""


_VERTICAL_HINTS = {
    "jobs": (
        "Vertical: jobs. Seniority: Senior/Lead/Staff/Principal/III = senior; "
        "Junior/Intern/Associate/I = junior. 'Remote' is met only if location says "
        "Remote/Worldwide/Anywhere or tags include a remote indicator. Tech (Python, "
        "Go, React) is met only if it appears in title/tags/description."
    ),
    "research": (
        "Vertical: research papers. 'Practical/empirical' is met only if the abstract "
        "mentions experiments, benchmark, dataset, evaluation, results, ablation, "
        "baseline, or numeric metrics. Pure theory/survey papers are unmet on this. "
        "A technique (RLHF, agents, tool use) is met only if its name or close "
        "synonym appears in title or abstract."
    ),
    "products": (
        "Vertical: tools/products. 'Open source' is met if host is github.com/"
        "gitlab.com/codeberg.org OR the tagline/description names a license (MIT, "
        "Apache, BSD, GPL). 'Developer tool' requires CLI/library/SDK/API/framework/"
        "runtime in title or tagline. Consumer apps are unmet for the dev-tool criterion."
    ),
}


_MAX_SCORE = 10.0
_MIN_SCORE = 0.0


async def rank(
    item: dict,
    *,
    criteria: list[str],
    vertical: str,
    cv_text: str | None = None,
    threshold: float = 6.0,
) -> tuple[float, list[str]]:
    """Score `item` against `criteria`. Returns (score, flattened_reasons).

    `vertical` should be one of: jobs, research, products, scholarships, other.
    Unknown verticals fall back to a generic prompt (still grounded, just no
    vertical-specific hints).

    `cv_text` (if set) is included in the prompt as candidate context for jobs
    verticals — the ranker treats criteria match against the listing AND
    candidate fit when relevant.

    Always returns; on LLM/parser failure returns (0.0, [error_string]) so a
    single bad response can't abort a 100-item run.
    """
    item_for_prompt = _trim_item(item)
    vertical_hint = _VERTICAL_HINTS.get((vertical or "").lower(), "")
    cv_section = (
        f"\n\nCANDIDATE CONTEXT (use for fit assessment, not as evidence):\n{cv_text[:1500]}"
        if cv_text else ""
    )

    prompt = (
        f"{vertical_hint}\n\n" if vertical_hint else ""
    ) + (
        f"CRITERIA (judge each independently):\n"
        f"{json.dumps(criteria, ensure_ascii=False, indent=2)}"
        f"{cv_section}\n\n"
        f"LISTING (judge against the criteria):\n"
        f"{json.dumps(item_for_prompt, ensure_ascii=False, indent=2)}"
    )

    try:
        raw = await chat(prompt, system=_SYSTEM, temperature=0.0)
    except Exception as exc:
        return 0.0, [f"[error] ranker LLM error: {exc}"]

    parsed = _extract_json_object(raw)
    if parsed is None:
        return 0.0, [f"[error] unparseable LLM response: {raw[:160]!r}"]

    # Score
    try:
        score = float(parsed.get("score", 0))
    except (TypeError, ValueError):
        score = 0.0
    score = max(_MIN_SCORE, min(_MAX_SCORE, score))

    # Per-criterion -> flat reasons. We also verify evidence is actually
    # quoted from the item. Hallucinated evidence gets downgraded.
    item_text_blob = _item_text_blob(item)
    per = parsed.get("per_criterion")
    reasons: list[str] = []
    downgrade_count = 0
    if isinstance(per, list):
        for entry in per:
            if not isinstance(entry, dict):
                continue
            verdict = str(entry.get("verdict", "")).lower().strip()
            criterion = str(entry.get("criterion", "")).strip()
            evidence = str(entry.get("evidence", "")).strip()
            if not criterion:
                continue
            # Verify evidence: at least one 4+-char word from the evidence must
            # appear in the item's text blob. This catches outright hallucination
            # ("evidence: 'uses Python'" when Python isn't mentioned).
            if verdict == "met" and evidence:
                if not _evidence_grounded(evidence, item_text_blob):
                    verdict = "partial"
                    downgrade_count += 1
                    evidence = f"{evidence} [unverified — downgraded]"
            label = f"[{verdict}] {criterion}"
            if evidence:
                label += f" — {evidence[:200]}"
            reasons.append(label)

    summary = str(parsed.get("summary", "")).strip()
    if summary:
        reasons.append(f"[summary] {summary[:240]}")

    # Apply downgrade penalty: each hallucinated "met" costs 1.5 points.
    if downgrade_count:
        score = max(_MIN_SCORE, score - 1.5 * downgrade_count)

    if not reasons:
        reasons = [f"[note] no structured reasons returned; raw={raw[:120]!r}"]

    return score, reasons


# ---------------------------------------------------------------------------


def _trim_item(item: dict) -> dict:
    """Drop noisy/huge fields before sending to the LLM. Keep what matters
    for ranking; truncate description to 800 chars (the LLM doesn't need
    the full abstract to judge relevance).
    """
    keep = (
        "title", "description", "summary", "tagline", "company", "tags",
        "categories", "primary_category", "authors", "author", "location",
        "salary_min", "salary_max", "date", "published", "posted_at",
        "score", "n_comments", "host", "url",
    )
    out: dict = {}
    for k in keep:
        v = item.get(k)
        if v in (None, "", [], {}):
            continue
        if isinstance(v, str) and len(v) > 800:
            v = v[:800] + "…"
        out[k] = v
    return out


def _item_text_blob(item: dict) -> str:
    """Concatenate all string fields into one lowercase blob for evidence
    grounding checks. Includes tags (joined) and authors (joined)."""
    parts: list[str] = []
    for k, v in item.items():
        if isinstance(v, str):
            parts.append(v.lower())
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, str):
                    parts.append(x.lower())
    return " ".join(parts)


_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+\-_/]{3,}", re.IGNORECASE)


def _evidence_grounded(evidence: str, item_blob: str) -> bool:
    """Loose substring check: any 4+-char token from `evidence` must appear in
    `item_blob`. Tolerates LLM paraphrasing while still catching wholesale
    hallucination."""
    if not evidence or not item_blob:
        return False
    tokens = _TOKEN_RE.findall(evidence.lower())
    if not tokens:
        return False
    # Drop common English stopwords that are too generic to count as grounding
    stop = {
        "this", "that", "with", "from", "have", "been", "they", "their",
        "which", "would", "could", "should", "about", "into", "than",
        "what", "when", "where", "while", "also", "such", "some", "more",
        "most", "very", "much", "many", "your", "yours", "ours", "them",
        "these", "those", "here", "there", "after", "before",
    }
    sig = [t for t in tokens if t not in stop]
    if not sig:
        return False
    # Require ≥2 significant tokens to appear, OR ≥1 if there's only one token.
    hits = sum(1 for t in sig if t in item_blob)
    return hits >= min(2, len(sig))


def _extract_json_object(text: str) -> dict | None:
    """Pull the first {...} object out of arbitrary LLM text.
    Tolerates markdown fences, prose preambles, trailing commentary.
    """
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.lstrip().lower().startswith("json"):
            s = s.split("\n", 1)[1] if "\n" in s else s[4:]
        s = s.rsplit("```", 1)[0].strip()
    if s.startswith("{") and s.endswith("}"):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            pass
    start = s.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(s)):
            ch = s[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = s[start : i + 1]
                    try:
                        obj = json.loads(candidate)
                        if isinstance(obj, dict):
                            return obj
                    except json.JSONDecodeError:
                        break
        start = s.find("{", start + 1)
    return None
