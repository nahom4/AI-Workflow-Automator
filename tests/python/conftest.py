"""
Shared pytest fixtures for worker unit tests.
All tests run from the project root so `worker` is importable directly.
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Make sure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def make_mock_tab(
    *,
    execute_script_return=None,
    request_get_return=None,
    network_logs=None,
    network_response_body=None,
):
    """Return a minimal AsyncMock that looks like a pydoll tab."""
    tab = MagicMock()

    tab.execute_script = AsyncMock(
        return_value=execute_script_return or {"result": {"result": {"value": []}}}
    )
    tab.go_to = AsyncMock()
    tab.enable_auto_solve_cloudflare_captcha = AsyncMock()
    tab.enable_network_events = AsyncMock()
    tab.on = MagicMock()
    tab.get_network_logs = AsyncMock(return_value=network_logs or [])
    tab.get_network_response_body = AsyncMock(return_value=network_response_body or "")

    req_response = MagicMock()
    req_response.json = MagicMock(return_value=request_get_return or [])
    req = MagicMock()
    req.get = AsyncMock(return_value=req_response)
    tab.request = req

    return tab
