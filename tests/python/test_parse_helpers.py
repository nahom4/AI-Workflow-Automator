"""
Unit tests for the pure-Python parsing helpers in worker/adapters/upwork.py.
No browser or network required.
"""

import pytest
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# parse_budget
# ---------------------------------------------------------------------------

def test_parse_budget_hourly_range():
    from worker.adapters.upwork import parse_budget
    result = parse_budget("$50.00-$80.00/hr")
    assert result["type"] == "hourly"
    assert result["min"] == 50.0
    assert result["max"] == 80.0


def test_parse_budget_fixed():
    from worker.adapters.upwork import parse_budget
    result = parse_budget("$500")
    assert result["type"] == "fixed"
    assert result["min"] == 500.0
    assert result["max"] == 500.0


def test_parse_budget_hourly_prefix():
    from worker.adapters.upwork import parse_budget
    result = parse_budget("Hourly: $30.00-$60.00")
    assert result["type"] == "hourly"
    assert result["min"] == 30.0
    assert result["max"] == 60.0


def test_parse_budget_empty():
    from worker.adapters.upwork import parse_budget
    result = parse_budget("")
    assert result["min"] is None
    assert result["max"] is None
    assert result["raw"] == ""


def test_parse_budget_with_commas():
    from worker.adapters.upwork import parse_budget
    result = parse_budget("$1,500")
    assert result["min"] == 1500.0


# ---------------------------------------------------------------------------
# parse_relative_date
# ---------------------------------------------------------------------------

def test_parse_relative_date_hours():
    from worker.adapters.upwork import parse_relative_date
    now = datetime.now(timezone.utc)
    result = parse_relative_date("3 hours ago")
    assert result is not None
    diff = now - result
    assert 2 * 3600 < diff.total_seconds() < 4 * 3600


def test_parse_relative_date_days():
    from worker.adapters.upwork import parse_relative_date
    now = datetime.now(timezone.utc)
    result = parse_relative_date("5 days ago")
    assert result is not None
    diff = now - result
    assert 4 * 86400 < diff.total_seconds() < 6 * 86400


def test_parse_relative_date_yesterday():
    from worker.adapters.upwork import parse_relative_date
    now = datetime.now(timezone.utc)
    result = parse_relative_date("Posted yesterday")
    assert result is not None
    diff = now - result
    assert diff.total_seconds() < 2 * 86400


def test_parse_relative_date_weeks():
    from worker.adapters.upwork import parse_relative_date
    now = datetime.now(timezone.utc)
    result = parse_relative_date("2 weeks ago")
    assert result is not None
    diff = now - result
    assert 13 * 86400 < diff.total_seconds() < 15 * 86400


def test_parse_relative_date_unknown_returns_none():
    from worker.adapters.upwork import parse_relative_date
    result = parse_relative_date("some unknown format")
    assert result is None


# ---------------------------------------------------------------------------
# _normalize (Upwork card → standard item dict)
# ---------------------------------------------------------------------------

def test_normalize_standard_card():
    from worker.adapters.upwork import _normalize
    card = {
        "jobId": "~01abc",
        "url": "https://www.upwork.com/jobs/~01abc",
        "title": "Senior React Developer",
        "budgetRaw": "$80.00-$120.00/hr",
        "skills": ["React", "TypeScript"],
        "proposalsText": "10-15",
        "postedText": "2 hours ago",
        "descSnippet": "Looking for a senior developer",
    }
    item = _normalize(card)
    assert item["id"] == "~01abc"
    assert item["title"] == "Senior React Developer"
    assert item["url"] == "https://www.upwork.com/jobs/~01abc"
    assert item["skills"] == ["React", "TypeScript"]
    assert item["budget"]["type"] == "hourly"
    assert item["budget"]["min"] == 80.0
    assert item["posted_at"] is not None


def test_normalize_missing_optional_fields():
    from worker.adapters.upwork import _normalize
    card = {
        "jobId": "~01xyz",
        "url": "https://www.upwork.com/jobs/~01xyz",
        "title": "Python Developer",
        "budgetRaw": "",
        "skills": [],
        "proposalsText": "",
        "postedText": "",
        "descSnippet": "",
    }
    item = _normalize(card)
    assert item["id"] == "~01xyz"
    assert item["budget"]["min"] is None
    assert item["posted_at"] is None
    assert item["skills"] == []
