"""In-memory store for the last N scheduled-monitor run results.

This module is intentionally simple: the records live only for the lifetime of
the Python process and are never persisted to the database.  The frontend polls
``GET /api/monitor/status`` which reads from this store.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class MonitorRun:
    """A single execution of the background health-check job."""

    triggered_at: datetime
    status: str  # "running" | "completed" | "error"
    check_date: str | None = None  # ISO date string, e.g. "2026-04-05"
    anomalies_found: int = 0
    incidents_created: int = 0
    duration_ms: int | None = None
    error: str | None = None
    detail: list[dict[str, Any]] = field(default_factory=list)


# ── Store ─────────────────────────────────────────────────────────────────────

_lock = threading.Lock()
_runs: deque[MonitorRun] = deque(maxlen=20)
_next_run_at: datetime | None = None


def record_run(run: MonitorRun) -> None:
    """Append *run* to the in-memory history (thread-safe)."""
    with _lock:
        _runs.append(run)


def set_next_run_at(dt: datetime) -> None:
    """Store the timestamp of the next scheduled execution."""
    global _next_run_at
    with _lock:
        _next_run_at = dt


def get_latest() -> MonitorRun | None:
    """Return the most recent run, or *None* if nothing has run yet."""
    with _lock:
        return _runs[-1] if _runs else None


def get_all() -> list[MonitorRun]:
    """Return all stored runs, newest first."""
    with _lock:
        return list(reversed(_runs))


def get_next_run_at() -> datetime | None:
    """Return the scheduled time of the next run."""
    with _lock:
        return _next_run_at


def count_new_incidents_since(since: datetime | None) -> int:
    """Return the total number of incidents created by runs after *since*.

    Args:
        since: UTC datetime threshold.  ``None`` means *all* runs.
    """
    with _lock:
        runs = list(_runs)

    if since is None:
        return sum(r.incidents_created for r in runs)

    return sum(
        r.incidents_created
        for r in runs
        if r.triggered_at > since
    )
