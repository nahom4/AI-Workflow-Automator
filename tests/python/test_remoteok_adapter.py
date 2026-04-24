"""
Tests for the RemoteOK adapter.
Uses httpx mocking — no real network or browser required.
"""

import json
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock


# Realistic sample from the RemoteOK public API
SAMPLE_API_RESPONSE = [
    # First element is always a legal notice dict, not a job
    {
        "legal": "This data is from the RemoteOK.com API...",
        "apiVersion": "1.0",
    },
    {
        "id": 123456,
        "epoch": 1714000000,
        "date": "2024-04-25T00:00:00+00:00",
        "company": "Acme Corp",
        "company_logo": "https://remoteok.com/assets/logo.png",
        "position": "Senior Python Engineer",
        "tags": ["python", "django", "postgresql"],
        "logo": None,
        "description": "<p>We need a senior Python engineer...</p>",
        "location": "Worldwide",
        "salary_min": 120000,
        "salary_max": 180000,
        "url": "https://remoteok.com/jobs/123456",
        "apply_url": "https://acme.com/apply",
    },
    {
        "id": 789012,
        "epoch": 1713900000,
        "date": "2024-04-24T00:00:00+00:00",
        "company": "TechStartup",
        "position": "React Frontend Developer",
        "tags": ["react", "javascript", "typescript"],
        "salary_min": 90000,
        "salary_max": 130000,
        "url": "https://remoteok.com/jobs/789012",
        "apply_url": "https://techstartup.com/apply",
    },
    # Entry with no id — should be filtered out
    {
        "slug": "some-slug",
        "description": "No id field here",
    },
]


@pytest.fixture
def mock_httpx_response():
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.json.return_value = SAMPLE_API_RESPONSE
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


@pytest.fixture
def mock_httpx_client(mock_httpx_response):
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_httpx_response)
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    return mock_cm


# ---------------------------------------------------------------------------
# fetch_items
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_items_excludes_legal_notice(mock_httpx_client):
    with patch("httpx.AsyncClient", return_value=mock_httpx_client):
        from worker.adapters.remoteok import fetch_items
        items = await fetch_items()

    assert len(items) == 2
    # The legal notice dict and the no-id entry should both be excluded
    for item in items:
        assert item.get("id"), "every item must have an id"


@pytest.mark.asyncio
async def test_fetch_items_normalizes_fields(mock_httpx_client):
    with patch("httpx.AsyncClient", return_value=mock_httpx_client):
        from worker.adapters.remoteok import fetch_items
        items = await fetch_items()

    first = items[0]
    # Standard contract fields
    assert first["id"] == "123456"
    assert first["title"] == "Senior Python Engineer"
    assert first["url"] == "https://remoteok.com/jobs/123456"
    assert first["company"] == "Acme Corp"
    assert "python" in first["tags"]
    assert first["salary_min"] == 120000
    assert first["salary_max"] == 180000


@pytest.mark.asyncio
async def test_fetch_items_second_entry(mock_httpx_client):
    with patch("httpx.AsyncClient", return_value=mock_httpx_client):
        from worker.adapters.remoteok import fetch_items
        items = await fetch_items()

    second = items[1]
    assert second["id"] == "789012"
    assert second["title"] == "React Frontend Developer"


@pytest.mark.asyncio
async def test_fetch_items_handles_empty_response(mock_httpx_client):
    mock_httpx_client.__aenter__.return_value.get.return_value.json.return_value = []
    with patch("httpx.AsyncClient", return_value=mock_httpx_client):
        from worker.adapters.remoteok import fetch_items
        items = await fetch_items()

    assert items == []


@pytest.mark.asyncio
async def test_fetch_items_handles_legal_notice_only(mock_httpx_client):
    mock_httpx_client.__aenter__.return_value.get.return_value.json.return_value = [
        {"legal": "Only legal notice, no jobs"}
    ]
    with patch("httpx.AsyncClient", return_value=mock_httpx_client):
        from worker.adapters.remoteok import fetch_items
        items = await fetch_items()

    assert items == []
