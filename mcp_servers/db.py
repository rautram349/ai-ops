"""Shared synchronous database connection pool for all MCP servers.

MCP servers run synchronously (FastMCP is sync), so we use psycopg2 with a
ThreadedConnectionPool rather than asyncpg.  The pool is initialised once on
first access and reused across tool calls.

Usage::

    from mcp_servers.db import get_conn, release_conn, execute_query

    conn = get_conn()
    try:
        rows = execute_query("SELECT 1", conn=conn)
    finally:
        release_conn(conn)

    # Or use the context-manager helper:
    with db_connection() as conn:
        rows = execute_query("SELECT ...", conn=conn)
"""

from __future__ import annotations

import calendar
import contextlib
import datetime
import os
import threading
from collections.abc import Iterator
from typing import Any, overload

import psycopg2
import psycopg2.extras
import psycopg2.pool
from dotenv import load_dotenv

load_dotenv()

_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()

_MIN_CONN = 1
_MAX_CONN = 10


def _build_pool() -> psycopg2.pool.ThreadedConnectionPool:
    dsn = os.environ.get(
        "DATABASE_URL_SYNC",
        "postgresql://postgres:postgres@localhost:5432/ecommerce_ops_brain",
    )
    return psycopg2.pool.ThreadedConnectionPool(_MIN_CONN, _MAX_CONN, dsn=dsn)


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = _build_pool()
    return _pool


def get_conn() -> psycopg2.extensions.connection:
    """Borrow a connection from the pool."""
    return _get_pool().getconn()


def release_conn(conn: psycopg2.extensions.connection) -> None:
    """Return a connection to the pool."""
    _get_pool().putconn(conn)


@contextlib.contextmanager
def db_connection() -> Iterator[psycopg2.extensions.connection]:
    """Context manager that borrows and returns a connection automatically."""
    conn = get_conn()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        release_conn(conn)


def execute_query(
    sql: str,
    params: tuple | dict | None = None,
    conn: psycopg2.extensions.connection | None = None,
) -> list[dict[str, Any]]:
    """Execute a SELECT query and return results as a list of dicts.

    If *conn* is provided it is used directly (no pool checkout).  Otherwise
    a connection is borrowed from the pool for the duration of the call.
    """
    if conn is not None:
        return _run_query(conn, sql, params)

    with db_connection() as c:
        return _run_query(c, sql, params)


# ── helpers ──────────────────────────────────────────────────────────────────

@overload
def safe_date(date_str: str) -> str: ...
@overload
def safe_date(date_str: None) -> None: ...
def safe_date(date_str: str | None) -> str | None:
    """Clamp a date string to a valid calendar date.

    Handles LLM-generated dates like "2026-02-29" (Feb has only 28 days in
    non-leap years) by clamping the day to the last valid day of the month.
    Returns ``None`` unchanged.
    """
    if date_str is None:
        return None
    try:
        datetime.date.fromisoformat(date_str)
        return date_str
    except ValueError:
        parts = date_str.split("-")
        if len(parts) == 3:
            try:
                y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                last_day = calendar.monthrange(y, m)[1]
                clamped = f"{y:04d}-{m:02d}-{min(d, last_day):02d}"
                return clamped
            except (ValueError, IndexError):
                pass
        return date_str


def _run_query(
    conn: psycopg2.extensions.connection,
    sql: str,
    params: tuple | dict | None,
) -> list[dict[str, Any]]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]
