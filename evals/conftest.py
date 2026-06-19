"""Pytest fixtures for the eval harness.

Requires MCP servers and the backend to be running.
Set EVAL_SERVICES_AVAILABLE=1 in the environment to enable integration tests.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ── Skip marker ───────────────────────────────────────────────────────────────

def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: marks tests that require live MCP servers and DB",
    )


def services_available() -> bool:
    """Return True if the environment has MCP services ready for eval."""
    return os.getenv("EVAL_SERVICES_AVAILABLE", "0").strip() in ("1", "true", "yes")


skip_if_no_services = pytest.mark.skipif(
    not services_available(),
    reason="Set EVAL_SERVICES_AVAILABLE=1 to run integration tests",
)
