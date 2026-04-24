"""
Tests for the AI ranker (worker/ai/ranker.py).
Mocks Groq so no real API calls are made.
"""

import json
import pytest
from unittest.mock import patch, AsyncMock


GOOD_MATCH_ITEM = {
    "id": "~01abc",
    "title": "Senior React Developer",
    "url": "https://www.upwork.com/jobs/~01abc",
    "skills": ["React", "TypeScript", "Next.js"],
    "budget": {"type": "hourly", "min": 80, "max": 120},
    "description": "We need a senior React/TypeScript developer for a SaaS product.",
}

POOR_MATCH_ITEM = {
    "id": "~01xyz",
    "title": "Junior Data Entry Clerk",
    "url": "https://www.upwork.com/jobs/~01xyz",
    "skills": [],
    "description": "Copy-paste data from PDFs to spreadsheets.",
}

CRITERIA = ["React", "TypeScript", "senior level", "SaaS"]


def _mock_chat(score: float, reasons: list[str]):
    """Return an AsyncMock for groq_client.chat that returns a fixed score."""
    payload = json.dumps({"score": score, "reasons": reasons})
    return AsyncMock(return_value=payload)


# ---------------------------------------------------------------------------
# rank()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rank_returns_score_and_reasons():
    with patch("worker.ai.ranker.chat", _mock_chat(8.5, ["Matches React", "Senior level"])):
        from worker.ai.ranker import rank
        score, reasons = await rank(GOOD_MATCH_ITEM, criteria=CRITERIA, vertical="jobs")

    assert score == 8.5
    assert "Matches React" in reasons


@pytest.mark.asyncio
async def test_rank_low_score_for_poor_match():
    with patch("worker.ai.ranker.chat", _mock_chat(2.0, ["Unrelated to criteria"])):
        from worker.ai.ranker import rank
        score, reasons = await rank(POOR_MATCH_ITEM, criteria=CRITERIA, vertical="jobs")

    assert score == 2.0
    assert len(reasons) > 0


@pytest.mark.asyncio
async def test_rank_score_is_float():
    with patch("worker.ai.ranker.chat", _mock_chat(7, [])):
        from worker.ai.ranker import rank
        score, _ = await rank(GOOD_MATCH_ITEM, criteria=CRITERIA, vertical="jobs")

    assert isinstance(score, float)


@pytest.mark.asyncio
async def test_rank_raises_on_bad_llm_response():
    with patch("worker.ai.ranker.chat", AsyncMock(return_value="not valid json {")):
        from worker.ai.ranker import rank
        with pytest.raises(ValueError, match="bad LLM response"):
            await rank(GOOD_MATCH_ITEM, criteria=CRITERIA, vertical="jobs")


@pytest.mark.asyncio
async def test_rank_raises_on_missing_score_field():
    payload = json.dumps({"reasons": ["Something"]})  # no "score" key
    with patch("worker.ai.ranker.chat", AsyncMock(return_value=payload)):
        from worker.ai.ranker import rank
        with pytest.raises((ValueError, KeyError)):
            await rank(GOOD_MATCH_ITEM, criteria=CRITERIA, vertical="jobs")


@pytest.mark.asyncio
async def test_rank_passes_cv_text_in_prompt():
    """Verify that cv_text is forwarded to the LLM prompt."""
    captured_prompt = {}

    async def mock_chat(prompt, **kwargs):
        captured_prompt["value"] = prompt
        return json.dumps({"score": 7.0, "reasons": []})

    with patch("worker.ai.ranker.chat", mock_chat):
        from worker.ai.ranker import rank
        await rank(GOOD_MATCH_ITEM, criteria=CRITERIA, vertical="jobs", cv_text="5 years React")

    assert "5 years React" in captured_prompt["value"]


@pytest.mark.asyncio
async def test_rank_truncates_large_items():
    """Very large items should not exceed the 3000-char cap in the prompt."""
    big_item = {**GOOD_MATCH_ITEM, "description": "x" * 10_000}
    captured_prompt = {}

    async def mock_chat(prompt, **kwargs):
        captured_prompt["value"] = prompt
        return json.dumps({"score": 5.0, "reasons": []})

    with patch("worker.ai.ranker.chat", mock_chat):
        from worker.ai.ranker import rank
        await rank(big_item, criteria=CRITERIA, vertical="jobs")

    # The serialized item in the prompt should be capped
    assert len(captured_prompt["value"]) < 15_000
