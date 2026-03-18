"""
Compare endpoints — git-ref-based and file-upload-based L5X comparison.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.compare.ai_compare import AiCompareAdapter
from app.compare.deterministic_diff import compute_text_diff, compute_xml_sections_diff
from app.compare.xml_normalizer import normalize_l5x
from app.config.loader import get_config
from app.db.models import CompareJob
from app.db.session import get_db
from app.git.repo_browser import RepoBrowser

logger = logging.getLogger(__name__)
router = APIRouter(tags=["compare"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GitCompareRequest(BaseModel):
    plc_name: str
    left_ref: str
    right_ref: str
    compare_mode: str = "full"  # "full" | "sections_only" | "ai_only"
    options: Optional[Dict[str, Any]] = None


class CompareJobResponse(BaseModel):
    job_id: str
    status: str
    message: str


class CompareResultResponse(BaseModel):
    job_id: str
    plc_name: Optional[str]
    status: str
    result: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    finished_at: Optional[str] = None


class RawDiffResponse(BaseModel):
    job_id: str
    raw_diff: Optional[str]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/compare/git", response_model=CompareJobResponse)
async def compare_git_refs(
    request: GitCompareRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> CompareJobResponse:
    """
    Start a git-ref-based comparison job for a named PLC.

    ``left_ref`` and ``right_ref`` are git commit SHAs or branch names.
    """
    cfg = get_config()
    plc_map = {p.name: p for p in cfg.plcs}
    if request.plc_name not in plc_map:
        raise HTTPException(
            status_code=404,
            detail=f"PLC {request.plc_name!r} not found in configuration.",
        )

    job_id = str(uuid.uuid4())
    job = CompareJob(
        id=job_id,
        plc_name=request.plc_name,
        left_ref=request.left_ref,
        right_ref=request.right_ref,
        compare_mode=request.compare_mode,
        status="pending",
    )
    db.add(job)
    db.commit()

    plc_def = plc_map[request.plc_name]

    async def _run() -> None:
        from datetime import datetime, timezone
        _mark(db, job_id, "running")
        try:
            browser = RepoBrowser(local_checkout=cfg.repository.local_checkout)
            l5x_file = f"{request.plc_name}.L5X"
            left_bytes = await browser.get_file_at_commit(
                request.left_ref, f"{plc_def.repo_path}/{l5x_file}"
            )
            right_bytes = await browser.get_file_at_commit(
                request.right_ref, f"{plc_def.repo_path}/{l5x_file}"
            )
            result, raw_diff = await _run_compare(
                left_bytes, right_bytes, request.plc_name, cfg, request.compare_mode
            )
            _mark(db, job_id, "success", result_json=json.dumps(result), raw_diff=raw_diff,
                  finished_at=datetime.now(tz=timezone.utc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Compare job %s failed", job_id)
            _mark(db, job_id, "failed", result_json=json.dumps({"error": str(exc)}),
                  finished_at=datetime.now(tz=timezone.utc))

    background_tasks.add_task(_run)

    return CompareJobResponse(
        job_id=job_id,
        status="pending",
        message="Compare job started. Poll GET /api/compare/jobs/{job_id} for results.",
    )


@router.post("/compare/upload", response_model=CompareJobResponse)
async def compare_upload(
    background_tasks: BackgroundTasks,
    file_a: UploadFile = File(..., description="Left L5X file"),
    file_b: UploadFile = File(..., description="Right L5X file"),
    db: Session = Depends(get_db),
) -> CompareJobResponse:
    """
    Compare two L5X files uploaded directly (no git required).

    Accepts two multipart file uploads.  Returns a job ID for polling.
    """
    cfg = get_config()
    left_bytes = await file_a.read()
    right_bytes = await file_b.read()

    job_id = str(uuid.uuid4())
    job = CompareJob(
        id=job_id,
        plc_name=None,
        left_ref=file_a.filename,
        right_ref=file_b.filename,
        compare_mode="upload",
        status="pending",
    )
    db.add(job)
    db.commit()

    async def _run() -> None:
        from datetime import datetime, timezone
        _mark(db, job_id, "running")
        try:
            plc_name = file_a.filename or "unknown"
            result, raw_diff = await _run_compare(
                left_bytes, right_bytes, plc_name, cfg, "full"
            )
            _mark(db, job_id, "success", result_json=json.dumps(result), raw_diff=raw_diff,
                  finished_at=datetime.now(tz=timezone.utc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Upload compare job %s failed", job_id)
            _mark(db, job_id, "failed", result_json=json.dumps({"error": str(exc)}),
                  finished_at=datetime.now(tz=timezone.utc))

    background_tasks.add_task(_run)
    return CompareJobResponse(
        job_id=job_id,
        status="pending",
        message="Compare job started. Poll GET /api/compare/jobs/{job_id} for results.",
    )


@router.get("/compare/jobs/{job_id}", response_model=CompareResultResponse)
async def get_compare_job(
    job_id: str,
    db: Session = Depends(get_db),
) -> CompareResultResponse:
    """Return the status and result of a compare job."""
    job = db.query(CompareJob).filter(CompareJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Compare job {job_id!r} not found.")

    result = None
    if job.result_json:
        try:
            result = json.loads(job.result_json)
        except json.JSONDecodeError:
            result = {"raw": job.result_json}

    return CompareResultResponse(
        job_id=job.id,
        plc_name=job.plc_name,
        status=job.status,
        result=result,
        created_at=str(job.created_at) if job.created_at else None,
        finished_at=str(job.finished_at) if job.finished_at else None,
    )


@router.get("/compare/jobs/{job_id}/raw-diff", response_model=RawDiffResponse)
async def get_raw_diff(
    job_id: str,
    db: Session = Depends(get_db),
) -> RawDiffResponse:
    """Return the raw unified diff text for a completed compare job."""
    job = db.query(CompareJob).filter(CompareJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Compare job {job_id!r} not found.")
    return RawDiffResponse(job_id=job.id, raw_diff=job.raw_diff)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _run_compare(
    left_bytes: bytes,
    right_bytes: bytes,
    plc_name: str,
    cfg,
    compare_mode: str,
) -> tuple[Dict[str, Any], str]:
    """Run normalise → section diff → AI compare and return (result_dict, raw_diff)."""
    left_norm = normalize_l5x(left_bytes)
    right_norm = normalize_l5x(right_bytes)

    sections_diff = compute_xml_sections_diff(left_norm, right_norm)
    raw_diff = compute_text_diff(
        left_norm.decode("utf-8", errors="replace"),
        right_norm.decode("utf-8", errors="replace"),
    )

    result: Dict[str, Any] = {"sections_diff": sections_diff}

    if compare_mode in ("full", "ai_only"):
        try:
            ai = AiCompareAdapter(config=cfg.ai)
            ai_result = await ai.compare(
                content_a=left_norm.decode("utf-8", errors="replace"),
                content_b=right_norm.decode("utf-8", errors="replace"),
                plc_name=plc_name,
                sections_diff=sections_diff,
            )
            result["ai"] = ai_result
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI compare failed (non-fatal): %s", exc)
            result["ai"] = {"error": str(exc)}

    return result, raw_diff


def _mark(db: Session, job_id: str, status: str, **kwargs) -> None:
    try:
        job = db.query(CompareJob).filter(CompareJob.id == job_id).first()
        if job:
            job.status = status
            for k, v in kwargs.items():
                setattr(job, k, v)
            db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to update compare job %s: %s", job_id, exc)
        db.rollback()
