"""APScheduler setup for the background health-monitor job.

Usage (from app lifespan)::

    from backend.scheduler import start_scheduler, stop_scheduler

    async with lifespan(app):
        await start_scheduler()
        yield
        await stop_scheduler()
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from backend.core.config import settings
from backend.db.connection import AsyncSessionLocal
from backend.services import monitor_run_store as store
from backend.services.monitor_run_store import MonitorRun
from backend.services.monitor_service import run_monitor_check

logger = structlog.get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _monitor_job() -> None:
    """Execute one health-check cycle and record the result."""
    run = MonitorRun(
        triggered_at=datetime.now(UTC),
        status="running",
    )
    store.record_run(run)

    t0 = time.monotonic()
    try:
        async with AsyncSessionLocal() as db:
            result = await run_monitor_check(db)

        run.status = "completed"
        run.check_date = result.check_date.isoformat()
        run.anomalies_found = result.anomalies_found
        run.incidents_created = result.incidents_created
        run.detail = result.detail
        run.duration_ms = int((time.monotonic() - t0) * 1000)

    except Exception as exc:
        run.status = "error"
        run.error = str(exc)
        run.duration_ms = int((time.monotonic() - t0) * 1000)
        logger.exception("monitor_job.error", error=str(exc))

    # Update the next run timestamp so the frontend can display it
    if _scheduler is not None:
        job = _scheduler.get_job("monitor_job")
        if job is not None and job.next_run_time is not None:
            store.set_next_run_at(job.next_run_time)


async def start_scheduler() -> None:
    """Create and start the AsyncIOScheduler."""
    global _scheduler

    interval = settings.monitor_interval_minutes
    logger.info("scheduler.starting", interval_minutes=interval)

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _monitor_job,
        trigger=IntervalTrigger(minutes=interval),
        id="monitor_job",
        name="Health Monitor",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.start()

    # Record the first next-run time
    job = _scheduler.get_job("monitor_job")
    if job is not None and job.next_run_time is not None:
        store.set_next_run_at(job.next_run_time)

    logger.info("scheduler.started", interval_minutes=interval)


async def stop_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("scheduler.stopped")
    _scheduler = None


def trigger_now() -> None:
    """Manually fire the monitor job immediately (useful for debugging)."""
    if _scheduler is None:
        raise RuntimeError("Scheduler is not running.")
    _scheduler.modify_job("monitor_job", next_run_time=datetime.now(UTC))
