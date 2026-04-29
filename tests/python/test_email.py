"""Tests for worker.notify.email — Resend calls are fully mocked."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest


def _make_resend_stub():
    stub = types.ModuleType("resend")
    stub.api_key = ""
    stub.Emails = MagicMock()
    stub.Emails.send = MagicMock(return_value={"id": "test-email-id"})
    return stub


_LEADS = [
    {"title": "Senior Engineer", "url": "https://example.com/1", "score": 8.5},
    {"title": "ML Engineer", "url": "https://example.com/2", "score": 9.0},
]


async def test_raises_when_no_api_key():
    from worker.notify.email import send_lead_digest

    with patch("worker.notify.email.RESEND_API_KEY", ""):
        with pytest.raises(RuntimeError, match="RESEND_API_KEY"):
            await send_lead_digest(
                to="user@example.com", automation_name="Jobs", leads=_LEADS
            )


async def test_returns_early_when_no_leads():
    resend_stub = _make_resend_stub()
    sys.modules["resend"] = resend_stub

    from worker.notify.email import send_lead_digest

    with patch("worker.notify.email.RESEND_API_KEY", "re_test_key"):
        await send_lead_digest(to="user@example.com", automation_name="Jobs", leads=[])
    resend_stub.Emails.send.assert_not_called()


async def test_calls_resend_with_correct_recipient():
    resend_stub = _make_resend_stub()
    sys.modules["resend"] = resend_stub

    from worker.notify.email import send_lead_digest

    with patch("worker.notify.email.RESEND_API_KEY", "re_test_key"):
        await send_lead_digest(
            to="user@example.com", automation_name="My Jobs", leads=_LEADS
        )

    call_args = resend_stub.Emails.send.call_args[0][0]
    assert call_args["to"] == ["user@example.com"]


async def test_subject_includes_automation_name_and_count():
    resend_stub = _make_resend_stub()
    sys.modules["resend"] = resend_stub

    from worker.notify.email import send_lead_digest

    with patch("worker.notify.email.RESEND_API_KEY", "re_test_key"):
        await send_lead_digest(
            to="user@example.com", automation_name="My Jobs", leads=_LEADS
        )

    call_args = resend_stub.Emails.send.call_args[0][0]
    assert "My Jobs" in call_args["subject"]
    assert "2" in call_args["subject"]


async def test_html_contains_lead_titles():
    resend_stub = _make_resend_stub()
    sys.modules["resend"] = resend_stub

    from worker.notify.email import send_lead_digest

    with patch("worker.notify.email.RESEND_API_KEY", "re_test_key"):
        await send_lead_digest(
            to="user@example.com", automation_name="My Jobs", leads=_LEADS
        )

    call_args = resend_stub.Emails.send.call_args[0][0]
    html = call_args["html"]
    assert "Senior Engineer" in html
    assert "ML Engineer" in html
    assert "8.5" in html
    assert "9.0" in html


async def test_sets_resend_api_key():
    resend_stub = _make_resend_stub()
    sys.modules["resend"] = resend_stub

    from worker.notify.email import send_lead_digest

    with patch("worker.notify.email.RESEND_API_KEY", "re_live_abc123"):
        await send_lead_digest(
            to="user@example.com", automation_name="Jobs", leads=_LEADS
        )
    assert resend_stub.api_key == "re_live_abc123"
