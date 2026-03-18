"""
PLC Backup Platform — FastAPI application entry point.

NOTE: The Rockwell Logix Designer SDK is Windows-only.  The backup runner
(scripts/run_backup.py) must be executed on a Windows host.  The API server
(this file / scripts/run_api.py) can run on any platform for development
and integration testing — SDK operations will raise SdkNotAvailableError on
non-Windows hosts.
"""
import sys
import asyncio

# Windows-only: use ProactorEventLoop for subprocess support with asyncio.
# This MUST be set before any other asyncio usage.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import logging

from fastapi import FastAPI
from pythonjsonlogger import jsonlogger

from app.api import backups, compare, health, plcs
from app.config.loader import get_config
from app.db.session import init_db
from app.jobs.backup_job import BackupJobRunner
from app.jobs.scheduler import BackupScheduler
from app.git.publisher import GitPublisher
from app.plc.rockwell_sdk_client import RockwellSdkClient

# ---------------------------------------------------------------------------
# Structured JSON logging setup
# ---------------------------------------------------------------------------

def _setup_logging() -> None:
    try:
        cfg = get_config()
        log_level = getattr(logging, cfg.logging.level.upper(), logging.INFO)
    except Exception:
        log_level = logging.INFO

    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(log_level)
    root.addHandler(handler)


_setup_logging()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="PLC Backup Platform",
    version="1.0.0",
    description=(
        "Automated backup, versioning, and AI-powered comparison of "
        "Rockwell Automation PLC projects."
    ),
)

app.include_router(backups.router, prefix="/api")
app.include_router(compare.router, prefix="/api")
app.include_router(plcs.router, prefix="/api")
app.include_router(health.router, prefix="/api")

# Module-level scheduler so startup/shutdown can reference it
_scheduler: BackupScheduler | None = None


@app.on_event("startup")
async def startup() -> None:
    global _scheduler

    logger.info("PLC Backup Platform starting up")

    # Initialise the database (create tables if needed)
    init_db()
    logger.info("Database initialised")

    # Set up and start the backup scheduler
    try:
        cfg = get_config()
        sdk_client = RockwellSdkClient(
            upload_timeout_minutes=cfg.service.upload_timeout_minutes
        )
        git_publisher = GitPublisher(
            local_checkout=cfg.repository.local_checkout,
            remote_url=cfg.repository.url,
            branch=cfg.repository.branch,
            username=cfg.repository.username,
        )

        from app.db.session import SessionLocal
        db = SessionLocal()
        runner = BackupJobRunner(
            config=cfg,
            db=db,
            sdk_client=sdk_client,
            git_publisher=git_publisher,
        )

        _scheduler = BackupScheduler()
        _scheduler.setup_schedules(cfg.plcs, runner)
        _scheduler.start()
        logger.info("Backup scheduler started")
    except Exception as exc:
        logger.error("Failed to start scheduler: %s", exc)


@app.on_event("shutdown")
async def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.stop()
        logger.info("Backup scheduler stopped")
    logger.info("PLC Backup Platform shutting down")
