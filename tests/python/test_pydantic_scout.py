"""
Tests for worker.scout.pydantic_scout (Tier-2 scout).
All pydoll and Groq calls are mocked.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from tests.python.conftest import make_mock_tab

_CANDIDATES_JSON = json.dumps([{"selector": "li.job-card", "count": 20}])
_SNIPPETS_JSON = json.dumps(
    ["<li class='job-card'><h2>Engineer</h2><a href='/j/1'>View</a></li>"] * 3
)
_SPEC_RESPONSE = json.dumps({
    "card_selector": "li.job-card",
    "fields": {
        "title": {"selector": "h2", "attr": None},
        "url": {"selector": "a", "attr": "href"},
        "id": {"selector": "li", "attr": "data-id"},
    },
})


@patch("worker.scout.pydantic_scout.navigate", new_callable=AsyncMock)
@patch("worker.scout.pydantic_scout.settle", new_callable=AsyncMock)
@patch("worker.scout.pydantic_scout.chat", new_callable=AsyncMock)
async def test_scout_returns_none_when_no_candidates(mock_chat, mock_settle, mock_nav):
    from worker.scout.pydantic_scout import scout

    tab = make_mock_tab(
        execute_script_return={"result": {"result": {"value": "[]"}}}
    )
    result = await scout(tab, url="https://example.com", vertical="jobs")
    assert result is None
    mock_chat.assert_not_called()


@patch("worker.scout.pydantic_scout.navigate", new_callable=AsyncMock)
@patch("worker.scout.pydantic_scout.settle", new_callable=AsyncMock)
@patch("worker.scout.pydantic_scout.chat", new_callable=AsyncMock)
async def test_scout_returns_spec_on_happy_path(mock_chat, mock_settle, mock_nav):
    from worker.scout.pydantic_scout import scout

    tab = make_mock_tab()
    tab.execute_script.side_effect = [
        {"result": {"result": {"value": _CANDIDATES_JSON}}},
        {"result": {"result": {"value": _SNIPPETS_JSON}}},
    ]
    mock_chat.return_value = _SPEC_RESPONSE

    result = await scout(tab, url="https://example.com", vertical="jobs")
    assert result is not None
    assert result["card_selector"] == "li.job-card"
    assert "fields" in result


@patch("worker.scout.pydantic_scout.navigate", new_callable=AsyncMock)
@patch("worker.scout.pydantic_scout.settle", new_callable=AsyncMock)
@patch("worker.scout.pydantic_scout.chat", new_callable=AsyncMock)
async def test_scout_returns_none_when_groq_says_not_found(mock_chat, mock_settle, mock_nav):
    from worker.scout.pydantic_scout import scout

    tab = make_mock_tab()
    tab.execute_script.side_effect = [
        {"result": {"result": {"value": _CANDIDATES_JSON}}},
        {"result": {"result": {"value": _SNIPPETS_JSON}}},
    ]
    mock_chat.return_value = json.dumps({"found": False})

    result = await scout(tab, url="https://example.com", vertical="jobs")
    assert result is None


@patch("worker.scout.pydantic_scout.navigate", new_callable=AsyncMock)
@patch("worker.scout.pydantic_scout.settle", new_callable=AsyncMock)
async def test_scout_returns_none_when_snippets_empty(mock_settle, mock_nav):
    from worker.scout.pydantic_scout import scout

    tab = make_mock_tab()
    tab.execute_script.side_effect = [
        {"result": {"result": {"value": _CANDIDATES_JSON}}},
        {"result": {"result": {"value": "[]"}}},
    ]

    result = await scout(tab, url="https://example.com", vertical="jobs")
    assert result is None


@patch("worker.scout.pydantic_scout.navigate", new_callable=AsyncMock)
@patch("worker.scout.pydantic_scout.settle", new_callable=AsyncMock)
async def test_scout_returns_none_when_candidates_json_invalid(mock_settle, mock_nav):
    from worker.scout.pydantic_scout import scout

    tab = make_mock_tab(
        execute_script_return={"result": {"result": {"value": "not-valid-json"}}}
    )

    result = await scout(tab, url="https://example.com", vertical="jobs")
    assert result is None


@patch("worker.scout.pydantic_scout.navigate", new_callable=AsyncMock)
@patch("worker.scout.pydantic_scout.settle", new_callable=AsyncMock)
@patch("worker.scout.pydantic_scout.chat", new_callable=AsyncMock)
async def test_scout_returns_none_when_groq_json_invalid(mock_chat, mock_settle, mock_nav):
    from worker.scout.pydantic_scout import scout

    tab = make_mock_tab()
    tab.execute_script.side_effect = [
        {"result": {"result": {"value": _CANDIDATES_JSON}}},
        {"result": {"result": {"value": _SNIPPETS_JSON}}},
    ]
    mock_chat.return_value = "totally not json"

    result = await scout(tab, url="https://example.com", vertical="jobs")
    assert result is None
