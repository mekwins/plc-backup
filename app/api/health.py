"""
Health check endpoint.

Reports the status of each platform dependency so that monitoring tools
(load balancers, Kubernetes probes, etc.) can determine if the service is
ready to receive traffic.
"""
from __future__ import annotations

import shutil
import subprocess
from typing import Any, Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config.loader import get_config
from app.db.session import get_engine
from app.plc.rockwell_sdk_client import SDK_AVAILABLE

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> JSONResponse:
    """
    Return a structured JSON health report.

    Checks:
    - config: whether the YAML config can be loaded
    - database: whether the DB engine can connect
    - git: whether the git CLI is on PATH
    - sdk: whether the Rockwell SDK wheel is installed
    """
    checks: Dict[str, Any] = {}
    overall_ok = True

    # --- Config ---
    try:
        cfg = get_config()
        checks["config"] = {
            "status": "ok",
            "environment": cfg.service.environment,
            "plc_count": len(cfg.plcs),
        }
    except Exception as exc:  # noqa: BLE001
        checks["config"] = {"status": "error", "detail": str(exc)}
        overall_ok = False

    # --- Database ---
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        checks["database"] = {"status": "error", "detail": str(exc)}
        overall_ok = False

    # --- Git CLI ---
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            checks["git"] = {"status": "ok", "version": result.stdout.strip()}
        else:
            checks["git"] = {"status": "error", "detail": result.stderr.strip()}
            overall_ok = False
    except FileNotFoundError:
        checks["git"] = {"status": "error", "detail": "git not found on PATH"}
        overall_ok = False
    except Exception as exc:  # noqa: BLE001
        checks["git"] = {"status": "error", "detail": str(exc)}
        overall_ok = False

    # --- Rockwell SDK ---
    checks["sdk"] = {
        "status": "ok" if SDK_AVAILABLE else "unavailable",
        "detail": (
            "logix_designer_sdk installed"
            if SDK_AVAILABLE
            else "logix_designer_sdk not installed — backup operations require Windows + SDK"
        ),
    }
    # SDK unavailable is a warning, not a hard failure (app still serves API)

    status_code = 200 if overall_ok else 503
    return JSONResponse(
        content={
            "status": "ok" if overall_ok else "degraded",
            "checks": checks,
        },
        status_code=status_code,
    )
