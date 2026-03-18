"""
Backup job runner.

Orchestrates the full backup pipeline for one or more PLCs:
  1. Reachability check
  2. SDK upload (ACD + L5X)
  3. Manifest, checksums, run log
  4. Git publish
  5. DB record update
"""
from __future__ import annotations

import asyncio
import logging
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from sqlalchemy.orm import Session

from app.config.schema import AppConfig, PlcDefinition
from app.db.models import BackupJob
from app.git.publisher import GitPublisher
from app.plc.models import BackupResult
from app.plc.reachability import is_reachable
from app.plc.rockwell_sdk_client import RockwellSdkClient
from app.storage.file_layout import get_backup_dir, get_latest_dir
from app.storage.manifests import (
    build_manifest,
    write_checksums,
    write_manifest,
    write_run_log,
)

logger = logging.getLogger(__name__)


class BackupJobRunner:
    """
    Runs backup jobs for PLC controllers.

    Parameters
    ----------
    config:
        Loaded application configuration.
    db:
        SQLAlchemy session.  The caller is responsible for lifecycle management.
    sdk_client:
        Rockwell SDK adapter.
    git_publisher:
        Git publisher for artifact upload.
    """

    def __init__(
        self,
        config: AppConfig,
        db: Session,
        sdk_client: RockwellSdkClient,
        git_publisher: GitPublisher,
    ) -> None:
        self._config = config
        self._db = db
        self._sdk = sdk_client
        self._git = git_publisher

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_backup_for_plc(
        self,
        plc_def: PlcDefinition,
        job_id: str,
    ) -> BackupResult:
        """
        Execute the full backup pipeline for a single PLC.

        Parameters
        ----------
        plc_def:
            PLC definition from config.
        job_id:
            Pre-created DB job UUID string.

        Returns
        -------
        BackupResult
            Outcome of the backup (succeeded or failed).
        """
        log_lines: List[str] = []
        timestamp = datetime.now(tz=timezone.utc)
        backup_dir = get_backup_dir(
            self._config.storage.backup_root, plc_def.name, timestamp
        )

        def _log(msg: str) -> None:
            logger.info(msg)
            log_lines.append(f"[{datetime.now(tz=timezone.utc).isoformat()}] {msg}")

        # Mark job as running
        self._update_job(job_id, status="running", started_at=timestamp)

        try:
            # 1. Reachability check
            _log(f"Checking reachability for {plc_def.name} ({plc_def.ip})")
            reachable = await is_reachable(
                plc_def.ip,
                timeout=float(self._config.service.scan_timeout_seconds),
            )
            if not reachable:
                raise RuntimeError(
                    f"PLC {plc_def.name} ({plc_def.ip}) is not reachable"
                )
            _log(f"Reachability OK for {plc_def.name}")

            # 2. SDK upload
            _log(f"Starting SDK upload for {plc_def.name} via {plc_def.path}")
            raw = await self._sdk.upload_backup(
                plc_name=plc_def.name,
                comm_path=plc_def.path,
                output_dir=str(backup_dir),
            )
            result = BackupResult(
                plc_name=raw["plc_name"] if "plc_name" in raw else plc_def.name,
                acd_path=raw["acd_path"],
                l5x_path=raw["l5x_path"],
                project_name=raw["project_name"],
                comm_path=raw["comm_path"],
                status=raw["status"],
                firmware_revision=raw.get("firmware_revision"),
                catalog_number=raw.get("catalog_number"),
            )
            _log(f"SDK upload complete: ACD={result.acd_path} L5X={result.l5x_path}")

            # 3. Write manifest, checksums, run log
            backup_dir.mkdir(parents=True, exist_ok=True)
            manifest_data = build_manifest(plc_def, result, job_id, timestamp)
            manifest_path = write_manifest(backup_dir, manifest_data)
            acd_path = Path(result.acd_path)
            l5x_path = Path(result.l5x_path)
            write_checksums(backup_dir, [acd_path, l5x_path, manifest_path])
            _log("Manifest and checksums written")

            # 4. Git publish
            commit_message = (
                f"backup: {plc_def.name} {timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            )
            artifacts = [acd_path, l5x_path, manifest_path]
            git_sha = await self._git.publish(
                artifacts=artifacts,
                repo_path=plc_def.repo_path,
                commit_message=commit_message,
            )
            _log(f"Git publish complete: sha={git_sha}")

            # Write run log with git SHA
            _log("Run complete.")
            write_run_log(backup_dir, log_lines)

            # 5. Update latest dir reference (informational, not critical)
            _copy_to_latest(backup_dir, self._config.storage.backup_root, plc_def.name)

            # 6. Update DB job record
            self._update_job(
                job_id,
                status="success",
                finished_at=datetime.now(tz=timezone.utc),
                acd_path=result.acd_path,
                l5x_path=result.l5x_path,
                manifest_path=str(manifest_path),
                git_commit_sha=git_sha,
            )
            return result

        except Exception as exc:
            error_detail = traceback.format_exc()
            logger.error("Backup failed for %s: %s", plc_def.name, exc)
            log_lines.append(f"ERROR: {exc}")
            try:
                backup_dir.mkdir(parents=True, exist_ok=True)
                write_run_log(backup_dir, log_lines)
            except Exception:  # noqa: BLE001
                pass
            self._update_job(
                job_id,
                status="failed",
                finished_at=datetime.now(tz=timezone.utc),
                error_detail=error_detail,
            )
            return BackupResult(
                plc_name=plc_def.name,
                acd_path="",
                l5x_path="",
                project_name="",
                comm_path=plc_def.path,
                status="failed",
                error=str(exc),
            )

    async def run_all_enabled(
        self,
        filter_names: Optional[List[str]] = None,
    ) -> List[BackupResult]:
        """
        Run backups for all enabled PLCs (or a filtered subset) concurrently.

        Each PLC backup runs in isolation — a failure for one does not stop
        the others.  Concurrency is limited by ``max_parallel_backups``.

        Parameters
        ----------
        filter_names:
            Optional list of PLC names to restrict the run.  If None, all
            enabled PLCs are processed.

        Returns
        -------
        list[BackupResult]
            One result per PLC that was attempted.
        """
        plcs = [
            p for p in self._config.plcs
            if p.enabled and (filter_names is None or p.name in filter_names)
        ]

        if not plcs:
            logger.warning("No enabled PLCs match the requested filter.")
            return []

        semaphore = asyncio.Semaphore(self._config.service.max_parallel_backups)

        async def _bounded(plc_def: PlcDefinition) -> BackupResult:
            async with semaphore:
                job_id = _create_job_record(self._db, plc_def)
                return await self.run_backup_for_plc(plc_def, job_id)

        tasks = [asyncio.create_task(_bounded(p)) for p in plcs]
        return list(await asyncio.gather(*tasks, return_exceptions=False))

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _update_job(self, job_id: str, **kwargs) -> None:
        try:
            job = self._db.query(BackupJob).filter(BackupJob.id == job_id).first()
            if job:
                for k, v in kwargs.items():
                    setattr(job, k, v)
                self._db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to update DB job %s: %s", job_id, exc)
            self._db.rollback()


def _create_job_record(db: Session, plc_def: PlcDefinition) -> str:
    """Insert a pending BackupJob record and return its UUID."""
    job_id = str(uuid.uuid4())
    job = BackupJob(
        id=job_id,
        plc_name=plc_def.name,
        ip=plc_def.ip,
        comm_path=plc_def.path,
        status="pending",
    )
    db.add(job)
    db.commit()
    return job_id


def _copy_to_latest(source_dir: Path, backup_root: str, plc_name: str) -> None:
    """
    Copy the contents of *source_dir* to the ``latest`` directory.
    Non-critical — exceptions are logged and swallowed.
    """
    import shutil

    try:
        latest = get_latest_dir(backup_root, plc_name)
        if latest.exists():
            shutil.rmtree(latest)
        shutil.copytree(source_dir, latest)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not update latest dir for %s: %s", plc_name, exc)
