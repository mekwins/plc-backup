"""
Backup trigger and status endpoints.
"""
from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config.loader import get_config
from app.db.models import BackupJob
from app.db.session import get_db
from app.git.publisher import GitPublisher
from app.jobs.backup_job import BackupJobRunner
from app.plc.rockwell_sdk_client import RockwellSdkClient

logger = logging.getLogger(__name__)
router = APIRouter(tags=["backups"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class BackupRunRequest(BaseModel):
    plc_names: Optional[List[str]] = None


class BackupRunResponse(BaseModel):
    job_ids: List[str]
    message: str


class BackupJobResponse(BaseModel):
    id: str
    plc_name: str
    ip: str
    status: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    acd_path: Optional[str] = None
    l5x_path: Optional[str] = None
    manifest_path: Optional[str] = None
    git_commit_sha: Optional[str] = None
    error_detail: Optional[str] = None
    created_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/backups/run", response_model=BackupRunResponse)
async def run_backups(
    request: BackupRunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> BackupRunResponse:
    """
    Trigger a backup run for the specified PLCs (or all enabled PLCs if
    ``plc_names`` is omitted).

    The backup executes asynchronously in the background.  Use
    ``GET /api/backups/jobs/{job_id}`` to poll the status.
    """
    cfg = get_config()

    # Determine which PLCs to back up
    if request.plc_names:
        plc_map = {p.name: p for p in cfg.plcs}
        unknown = [n for n in request.plc_names if n not in plc_map]
        if unknown:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown PLC names: {unknown}",
            )
        target_plcs = [plc_map[n] for n in request.plc_names]
    else:
        target_plcs = [p for p in cfg.plcs if p.enabled]

    if not target_plcs:
        raise HTTPException(status_code=400, detail="No enabled PLCs to back up.")

    # Pre-create job records so we can return IDs immediately
    job_ids = []
    for plc in target_plcs:
        job_id = str(uuid.uuid4())
        job = BackupJob(
            id=job_id,
            plc_name=plc.name,
            ip=plc.ip,
            comm_path=plc.path,
            status="pending",
        )
        db.add(job)
        job_ids.append((plc, job_id))
    db.commit()

    # Build infrastructure objects
    sdk_client = RockwellSdkClient(
        upload_timeout_minutes=cfg.service.upload_timeout_minutes
    )
    git_publisher = GitPublisher(
        local_checkout=cfg.repository.local_checkout,
        remote_url=cfg.repository.url,
        branch=cfg.repository.branch,
        username=cfg.repository.username,
    )
    runner = BackupJobRunner(
        config=cfg,
        db=db,
        sdk_client=sdk_client,
        git_publisher=git_publisher,
    )

    # Schedule all jobs in the background
    async def _run_all() -> None:
        import asyncio
        tasks = [
            asyncio.create_task(runner.run_backup_for_plc(plc, jid))
            for plc, jid in job_ids
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    background_tasks.add_task(_run_all)

    return BackupRunResponse(
        job_ids=[jid for _, jid in job_ids],
        message=f"Backup triggered for {len(job_ids)} PLC(s). Poll job IDs for status.",
    )


@router.get("/backups/jobs/{job_id}", response_model=BackupJobResponse)
async def get_job_status(
    job_id: str,
    db: Session = Depends(get_db),
) -> BackupJobResponse:
    """Return the current status of a backup job."""
    job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found.")

    return BackupJobResponse(
        id=job.id,
        plc_name=job.plc_name,
        ip=job.ip,
        status=job.status,
        started_at=str(job.started_at) if job.started_at else None,
        finished_at=str(job.finished_at) if job.finished_at else None,
        acd_path=job.acd_path,
        l5x_path=job.l5x_path,
        manifest_path=job.manifest_path,
        git_commit_sha=job.git_commit_sha,
        error_detail=job.error_detail,
        created_at=str(job.created_at) if job.created_at else None,
    )
