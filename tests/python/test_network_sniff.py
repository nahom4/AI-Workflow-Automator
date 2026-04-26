"""
Tests for worker.scout.network_sniff (Tier-1 scout).
All pydoll and Groq calls are mocked.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from tests.python.conftest import make_mock_tab
from worker.scout.network_sniff import _collect_json_responses, _summarise

# ── _summarise unit tests ────────────────────────────────────────────────────

def test_summarise_dict_truncates_to_8_keys():
    d = {str(i): i for i in range(12)}
    result = _summarise(d)
    assert len(result) == 8


def test_summarise_list_shows_first_item_type():
    result = _summarise([1, 2, 3])
    assert result == ["int"]


def test_summarise_empty_list():
    assert _summarise([]) == []


def test_summarise_nested_dict():
    result = _summarise({"a": {"b": 1}})
    assert result == {"a": {"b": "int"}}


def test_summarise_depth_limit_returns_ellipsis():
    deep = {"a": {"b": {"c": {"d": {"e": "hi"}}}}}
    result = _summarise(deep)
    # depth > 4 triggers "...", so at depth=5 the leaf string becomes "..."
    assert result["a"]["b"]["c"]["d"]["e"] == "..."


# ── _collect_json_responses ──────────────────────────────────────────────────

_BIG_JSON = json.dumps([{"id": i, "title": f"Job {i}"} for i in range(100)])


async def test_collect_returns_empty_when_no_logs():
    tab = make_mock_tab(network_logs=[])
    result = await _collect_json_responses(tab)
    assert result == []


async def test_collect_skips_static_file_urls():
    logs = [
        {"params": {"requestId": "r1", "type": "XHR", "request": {"url": "https://ex.com/app.js"}}},
        {"params": {"requestId": "r2", "type": "XHR", "request": {"url": "https://ex.com/style.css"}}},
        {"params": {"requestId": "r3", "type": "XHR", "request": {"url": "https://ex.com/logo.png"}}},
    ]
    tab = make_mock_tab(network_logs=logs, network_response_body=_BIG_JSON)
    result = await _collect_json_responses(tab)
    assert result == []


async def test_collect_skips_non_xhr_resource_types():
    logs = [
        {"params": {"requestId": "r1", "type": "Script", "request": {"url": "https://ex.com/api"}}},
        {"params": {"requestId": "r2", "type": "Image", "request": {"url": "https://ex.com/api2"}}},
        {"params": {"requestId": "r3", "type": "Document", "request": {"url": "https://ex.com/api3"}}},
    ]
    tab = make_mock_tab(network_logs=logs, network_response_body=_BIG_JSON)
    result = await _collect_json_responses(tab)
    assert result == []


async def test_collect_skips_bodies_below_min_size():
    small = json.dumps({"ok": True})  # well under 2048 bytes
    logs = [
        {"params": {"requestId": "r1", "type": "XHR", "request": {"url": "https://ex.com/api"}}}
    ]
    tab = make_mock_tab(network_logs=logs, network_response_body=small)
    result = await _collect_json_responses(tab)
    assert result == []


async def test_collect_skips_non_json_bodies():
    not_json = "x" * 3000  # big but not JSON
    logs = [
        {"params": {"requestId": "r1", "type": "XHR", "request": {"url": "https://ex.com/api"}}}
    ]
    tab = make_mock_tab(network_logs=logs, network_response_body=not_json)
    result = await _collect_json_responses(tab)
    assert result == []


async def test_collect_returns_captured_entry_for_valid_xhr():
    logs = [
        {"params": {"requestId": "r1", "type": "XHR", "request": {"url": "https://ex.com/api/jobs"}}}
    ]
    tab = make_mock_tab(network_logs=logs, network_response_body=_BIG_JSON)
    result = await _collect_json_responses(tab)
    assert len(result) == 1
    assert result[0]["url"] == "https://ex.com/api/jobs"
    assert "shape" in result[0]


async def test_collect_accepts_fetch_resource_type():
    logs = [
        {"params": {"requestId": "r1", "type": "Fetch", "request": {"url": "https://ex.com/api/jobs"}}}
    ]
    tab = make_mock_tab(network_logs=logs, network_response_body=_BIG_JSON)
    result = await _collect_json_responses(tab)
    assert len(result) == 1


# ── scout() integration ──────────────────────────────────────────────────────

_SPEC = {
    "endpoint": "https://ex.com/api/jobs",
    "item_path": "jobs",
    "fields": {"title": "title", "url": "url", "id": "id"},
}

_LOGS = [
    {"params": {"requestId": "r1", "type": "XHR", "request": {"url": "https://ex.com/api/jobs"}}}
]


@patch("worker.scout.network_sniff.navigate", new_callable=AsyncMock)
@patch("worker.scout.network_sniff.settle", new_callable=AsyncMock)
@patch("worker.scout.network_sniff.chat", new_callable=AsyncMock)
async def test_scout_returns_none_when_no_logs(mock_chat, mock_settle, mock_nav):
    from worker.scout.network_sniff import scout

    tab = make_mock_tab(network_logs=[])
    result = await scout(tab, url="https://ex.com", vertical="jobs")
    assert result is None
    mock_chat.assert_not_called()


@patch("worker.scout.network_sniff.navigate", new_callable=AsyncMock)
@patch("worker.scout.network_sniff.settle", new_callable=AsyncMock)
@patch("worker.scout.network_sniff.chat", new_callable=AsyncMock)
async def test_scout_returns_spec_on_happy_path(mock_chat, mock_settle, mock_nav):
    from worker.scout.network_sniff import scout

    tab = make_mock_tab(network_logs=_LOGS, network_response_body=_BIG_JSON)
    mock_chat.return_value = json.dumps(_SPEC)

    result = await scout(tab, url="https://ex.com", vertical="jobs")
    assert result == _SPEC


@patch("worker.scout.network_sniff.navigate", new_callable=AsyncMock)
@patch("worker.scout.network_sniff.settle", new_callable=AsyncMock)
@patch("worker.scout.network_sniff.chat", new_callable=AsyncMock)
async def test_scout_returns_none_when_groq_says_not_found(mock_chat, mock_settle, mock_nav):
    from worker.scout.network_sniff import scout

    tab = make_mock_tab(network_logs=_LOGS, network_response_body=_BIG_JSON)
    mock_chat.return_value = json.dumps({"found": False})

    result = await scout(tab, url="https://ex.com", vertical="jobs")
    assert result is None


@patch("worker.scout.network_sniff.navigate", new_callable=AsyncMock)
@patch("worker.scout.network_sniff.settle", new_callable=AsyncMock)
@patch("worker.scout.network_sniff.chat", new_callable=AsyncMock)
async def test_scout_returns_none_when_groq_response_missing_endpoint(mock_chat, mock_settle, mock_nav):
    from worker.scout.network_sniff import scout

    tab = make_mock_tab(network_logs=_LOGS, network_response_body=_BIG_JSON)
    mock_chat.return_value = json.dumps({"fields": {"title": "t"}})  # missing endpoint

    result = await scout(tab, url="https://ex.com", vertical="jobs")
    assert result is None


@patch("worker.scout.network_sniff.navigate", new_callable=AsyncMock)
@patch("worker.scout.network_sniff.settle", new_callable=AsyncMock)
@patch("worker.scout.network_sniff.chat", new_callable=AsyncMock)
async def test_scout_returns_none_when_groq_returns_invalid_json(mock_chat, mock_settle, mock_nav):
    from worker.scout.network_sniff import scout

    tab = make_mock_tab(network_logs=_LOGS, network_response_body=_BIG_JSON)
    mock_chat.return_value = "not json at all"

    result = await scout(tab, url="https://ex.com", vertical="jobs")
    assert result is None


@patch("worker.scout.network_sniff.navigate", new_callable=AsyncMock)
@patch("worker.scout.network_sniff.settle", new_callable=AsyncMock)
async def test_scout_calls_enable_network_events(mock_settle, mock_nav):
    from worker.scout.network_sniff import scout

    tab = make_mock_tab(network_logs=[])
    await scout(tab, url="https://ex.com", vertical="jobs")
    tab.enable_network_events.assert_called_once()
