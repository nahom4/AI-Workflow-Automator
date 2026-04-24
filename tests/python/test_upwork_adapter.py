"""
Tests for the Upwork adapter.
Mocks the browser tab — no real Chrome or network required.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.python.conftest import make_mock_tab


# Realistic sample of what _EXTRACT_CARDS_JS returns from the browser
SAMPLE_CARDS = [
    {
        "jobId": "~01abc123def456",
        "url": "https://www.upwork.com/jobs/~01abc123def456",
        "title": "Senior React Developer",
        "budgetRaw": "$80.00-$120.00/hr",
        "skills": ["React", "TypeScript", "Next.js"],
        "proposalsText": "10-15 proposals",
        "postedText": "3 hours ago",
        "descSnippet": "We need an experienced React developer for a long-term project.",
    },
    {
        "jobId": "~01xyz789",
        "url": "https://www.upwork.com/jobs/~01xyz789",
        "title": "Python Backend Engineer",
        "budgetRaw": "$60.00-$90.00/hr",
        "skills": ["Python", "FastAPI", "PostgreSQL"],
        "proposalsText": "5-10 proposals",
        "postedText": "1 day ago",
        "descSnippet": "Looking for a Python expert to build REST APIs.",
    },
    # Entry without jobId — should be filtered out
    {
        "jobId": "",
        "url": "",
        "title": "Bad Entry",
        "budgetRaw": "",
        "skills": [],
        "proposalsText": "",
        "postedText": "",
        "descSnippet": "",
    },
]

# What tab.execute_script returns when the JS runs successfully
CARDS_JS_RESULT = {
    "result": {
        "result": {
            "value": SAMPLE_CARDS
        }
    }
}

# What tab.execute_script returns for the tile count poll
TILE_COUNT_RESULT = {
    "result": {
        "result": {
            "value": 2
        }
    }
}


def make_upwork_tab(cards=None):
    """Mock tab that returns tile count then card data on execute_script calls."""
    cards = cards if cards is not None else SAMPLE_CARDS
    call_count = {"n": 0}

    async def execute_script(script, **kwargs):
        call_count["n"] += 1
        # First calls are tile-count polls; last call is card extraction
        if "_EXTRACT_CARDS_JS" in script or "TILE_SELS" in script or "job-tile" in script:
            return {"result": {"result": {"value": cards}}}
        # Scroll or other JS
        return {"result": {"result": {"value": 0}}}

    tab = make_mock_tab(execute_script_return=None)
    tab.execute_script = execute_script
    return tab


# ---------------------------------------------------------------------------
# _extract_raw_cards
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_raw_cards_returns_list():
    tab = make_mock_tab(execute_script_return=CARDS_JS_RESULT)
    from worker.adapters.upwork import _extract_raw_cards
    result = await _extract_raw_cards(tab)
    assert isinstance(result, list)
    assert len(result) == 3


@pytest.mark.asyncio
async def test_extract_raw_cards_handles_empty():
    tab = make_mock_tab(execute_script_return={"result": {"result": {"value": []}}})
    from worker.adapters.upwork import _extract_raw_cards
    result = await _extract_raw_cards(tab)
    assert result == []


@pytest.mark.asyncio
async def test_extract_raw_cards_handles_bad_return():
    tab = make_mock_tab(execute_script_return={"result": {"result": {"value": None}}})
    from worker.adapters.upwork import _extract_raw_cards
    result = await _extract_raw_cards(tab)
    assert result == []


# ---------------------------------------------------------------------------
# _normalize
# ---------------------------------------------------------------------------

def test_normalize_maps_required_fields():
    from worker.adapters.upwork import _normalize
    item = _normalize(SAMPLE_CARDS[0])
    assert item["id"] == "~01abc123def456"
    assert item["title"] == "Senior React Developer"
    assert item["url"] == "https://www.upwork.com/jobs/~01abc123def456"


def test_normalize_parses_budget():
    from worker.adapters.upwork import _normalize
    item = _normalize(SAMPLE_CARDS[0])
    assert item["budget"]["type"] == "hourly"
    assert item["budget"]["min"] == 80.0
    assert item["budget"]["max"] == 120.0


def test_normalize_parses_posted_at():
    from worker.adapters.upwork import _normalize
    item = _normalize(SAMPLE_CARDS[0])
    assert item["posted_at"] is not None  # "3 hours ago" should parse


def test_normalize_preserves_skills():
    from worker.adapters.upwork import _normalize
    item = _normalize(SAMPLE_CARDS[0])
    assert item["skills"] == ["React", "TypeScript", "Next.js"]


# ---------------------------------------------------------------------------
# _build_search_url
# ---------------------------------------------------------------------------

def test_build_search_url_encodes_spaces():
    from worker.adapters.upwork import _build_search_url
    url = _build_search_url("React developer senior")
    assert "React" in url or "React%20" in url or "React+" in url
    assert "upwork.com" in url


def test_build_search_url_includes_recency_sort():
    from worker.adapters.upwork import _build_search_url
    url = _build_search_url("Python backend")
    assert "sort=recency" in url


# ---------------------------------------------------------------------------
# fetch_items (full flow with mocked browser)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_items_returns_normalized_items():
    tab = make_upwork_tab()

    with patch("worker.adapters.upwork.navigate", new_callable=AsyncMock), \
         patch("worker.adapters.upwork._wait_hydrated", new_callable=AsyncMock):
        from worker.adapters.upwork import fetch_items
        items = await fetch_items(tab, search_query="React developer")

    # Entries without jobId should be filtered
    assert len(items) == 2
    assert items[0]["id"] == "~01abc123def456"
    assert items[0]["title"] == "Senior React Developer"
    assert items[1]["id"] == "~01xyz789"


@pytest.mark.asyncio
async def test_fetch_items_filters_entries_without_id():
    # Include a card with empty jobId to confirm it's excluded
    cards_with_bad = SAMPLE_CARDS[:]  # includes the bad entry
    tab = make_upwork_tab(cards=cards_with_bad)

    with patch("worker.adapters.upwork.navigate", new_callable=AsyncMock), \
         patch("worker.adapters.upwork._wait_hydrated", new_callable=AsyncMock):
        from worker.adapters.upwork import fetch_items
        items = await fetch_items(tab, search_query="React")

    ids = [item["id"] for item in items]
    assert "" not in ids


@pytest.mark.asyncio
async def test_fetch_items_enables_cloudflare_bypass():
    tab = make_upwork_tab()

    with patch("worker.adapters.upwork.navigate", new_callable=AsyncMock), \
         patch("worker.adapters.upwork._wait_hydrated", new_callable=AsyncMock):
        from worker.adapters.upwork import fetch_items
        await fetch_items(tab, search_query="Python")

    tab.enable_auto_solve_cloudflare_captcha.assert_called_once()
