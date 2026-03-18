"""
APScheduler-based backup scheduler.

Maps human-friendly schedule strings from the YAML config to APScheduler
triggers and registers one job per enabled PLC.
"""
from __future__ import annotations

import logging
from typing import List

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config.schema import PlcDefinition
from app.jobs.backup_job import BackupJobRunner

logger = logging.getLogger(__name__)

# Map friendly schedule names to APScheduler IntervalTrigger kwargs
_SCHEDULE_MAP = {
    "hourly": {"hours": 1},
    "daily": {"hours": 24},
    "weekly": {"weeks": 1},
}


class BackupScheduler:
    """
    Manages scheduled PLC backup jobs using APScheduler.

    Usage::

        scheduler = BackupScheduler()
        scheduler.setup_schedules(config.plcs, job_runner)
        scheduler.start()
        # ... application runs ...
        scheduler.stop()
    """

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()

    def setup_schedules(
        self,
        plcs: List[PlcDefinition],
        job_runner: BackupJobRunner,
    ) -> None:
        """
        Register a scheduled job for each enabled PLC in *plcs*.

        Supported schedule string formats:
        - ``"hourly"`` — every hour
        - ``"daily"``  — every 24 hours
        - ``"weekly"`` — every 7 days
        - ``"0 2 * * *"`` — any valid 5-field cron expression

        Parameters
        ----------
        plcs:
            List of PLC definitions from the app configuration.
        job_runner:
            ``BackupJobRunner`` instance that will execute the backups.
        """
        for plc in plcs:
            if not plc.enabled:
                logger.debug("Skipping scheduler registration for disabled PLC: %s", plc.name)
                continue

            trigger = _build_trigger(plc.schedule)
            if trigger is None:
                logger.error(
                    "Could not parse schedule %r for PLC %s — job will not be scheduled",
                    plc.schedule,
                    plc.name,
                )
                continue

            # Capture plc.name in closure
            plc_name = plc.name

            async def _job(name: str = plc_name) -> None:
                logger.info("Scheduled backup triggered for %s", name)
                await job_runner.run_all_enabled(filter_names=[name])

            self._scheduler.add_job(
                _job,
                trigger=trigger,
                id=f"backup_{plc.name}",
                name=f"Backup {plc.name}",
                replace_existing=True,
                misfire_grace_time=300,  # 5 minutes
            )
            logger.info(
                "Registered schedule '%s' for PLC %s", plc.schedule, plc.name
            )

    def start(self) -> None:
        """Start the APScheduler event loop."""
        logger.info("Starting backup scheduler")
        self._scheduler.start()

    def stop(self) -> None:
        """Gracefully shut down the scheduler."""
        logger.info("Stopping backup scheduler")
        self._scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _build_trigger(schedule: str):
    """
    Convert a schedule string to an APScheduler trigger object.

    Returns None if the string cannot be parsed.
    """
    # Check friendly names first
    if schedule in _SCHEDULE_MAP:
        return IntervalTrigger(**_SCHEDULE_MAP[schedule])

    # Try to parse as a 5-field cron expression
    parts = schedule.strip().split()
    if len(parts) == 5:
        try:
            minute, hour, day, month, day_of_week = parts
            return CronTrigger(
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to parse cron expression %r: %s", schedule, exc)
            return None

    logger.error("Unrecognised schedule format: %r", schedule)
    return None
