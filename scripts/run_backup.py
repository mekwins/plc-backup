"""
CLI script to run PLC backups outside of the API server.

WINDOWS ONLY: The Rockwell Logix Designer SDK is a Windows-only component.
This script must be executed on a Windows host with Studio 5000 Logix Designer
and the SDK Python wheel installed.

Usage:
    python scripts/run_backup.py                  # back up all enabled PLCs
    python scripts/run_backup.py --plc Line01-CellA-Main Line01-CellB-Main
    python scripts/run_backup.py --config path/to/custom.yaml
"""
import sys
import asyncio

# MUST be set before any other asyncio usage — required for subprocess support
# in the Windows event loop (Proactor) when using asyncio.create_subprocess_exec.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import argparse
import logging
from pathlib import Path

# Allow running from the project root without installing the package
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from pythonjsonlogger import jsonlogger

from app.config.loader import get_config, reset_config_cache
from app.db.session import init_db, SessionLocal
from app.git.publisher import GitPublisher
from app.jobs.backup_job import BackupJobRunner
from app.plc.rockwell_sdk_client import RockwellSdkClient


def _setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(handler)


async def main(plc_names: list[str] | None, config_path: str | None) -> None:
    if config_path:
        reset_config_cache()
        cfg = get_config(config_path)
    else:
        cfg = get_config()

    _setup_logging(cfg.logging.level)
    logger = logging.getLogger(__name__)

    logger.info("PLC Backup Runner starting", extra={"platform": sys.platform})

    if sys.platform != "win32":
        logger.warning(
            "Running on non-Windows platform (%s). SDK operations will fail. "
            "The Rockwell Logix Designer SDK is Windows-only.",
            sys.platform,
        )

    init_db()

    sdk_client = RockwellSdkClient(
        upload_timeout_minutes=cfg.service.upload_timeout_minutes
    )
    git_publisher = GitPublisher(
        local_checkout=cfg.repository.local_checkout,
        remote_url=cfg.repository.url,
        branch=cfg.repository.branch,
        username=cfg.repository.username,
    )

    db = SessionLocal()
    try:
        runner = BackupJobRunner(
            config=cfg,
            db=db,
            sdk_client=sdk_client,
            git_publisher=git_publisher,
        )

        results = await runner.run_all_enabled(filter_names=plc_names or None)

        success_count = sum(1 for r in results if r.succeeded)
        fail_count = len(results) - success_count

        logger.info(
            "Backup run complete",
            extra={
                "total": len(results),
                "success": success_count,
                "failed": fail_count,
            },
        )

        for r in results:
            if not r.succeeded:
                logger.error(
                    "Backup failed for %s: %s", r.plc_name, r.error
                )

        sys.exit(0 if fail_count == 0 else 1)
    finally:
        db.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run PLC backups (Windows + Rockwell SDK required for real PLCs)"
    )
    parser.add_argument(
        "--plc",
        dest="plc_names",
        nargs="+",
        metavar="PLC_NAME",
        help="Names of specific PLCs to back up. Defaults to all enabled PLCs.",
    )
    parser.add_argument(
        "--config",
        dest="config_path",
        default=None,
        metavar="PATH",
        help="Path to config YAML. Defaults to config/app.yaml.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(main(args.plc_names, args.config_path))
