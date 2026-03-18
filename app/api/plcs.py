"""
PLC inventory and history endpoints.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config.loader import get_config
from app.git.repo_browser import RepoBrowser

logger = logging.getLogger(__name__)
router = APIRouter(tags=["plcs"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class PlcResponse(BaseModel):
    name: str
    ip: str
    slot: int
    path: str
    line: Optional[str]
    area: Optional[str]
    enabled: bool
    schedule: str
    repo_path: str
    tags: List[str]


class CommitEntry(BaseModel):
    sha: str
    message: str
    author: str
    timestamp: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/plcs", response_model=List[PlcResponse])
async def list_plcs() -> List[PlcResponse]:
    """Return the configured PLC inventory from the YAML config."""
    cfg = get_config()
    return [
        PlcResponse(
            name=p.name,
            ip=p.ip,
            slot=p.slot,
            path=p.path,
            line=p.line,
            area=p.area,
            enabled=p.enabled,
            schedule=p.schedule,
            repo_path=p.repo_path,
            tags=p.tags,
        )
        for p in cfg.plcs
    ]


@router.get("/plcs/{plc_name}/history", response_model=List[CommitEntry])
async def get_plc_history(
    plc_name: str,
    limit: int = 50,
) -> List[CommitEntry]:
    """
    Return the git commit history for a specific PLC's backup artifacts.

    Parameters
    ----------
    plc_name:
        Name of the PLC as defined in ``config/app.yaml``.
    limit:
        Maximum number of commits to return (default 50, max 500).
    """
    cfg = get_config()
    plc_map = {p.name: p for p in cfg.plcs}
    if plc_name not in plc_map:
        raise HTTPException(
            status_code=404,
            detail=f"PLC {plc_name!r} not found in configuration.",
        )

    plc = plc_map[plc_name]
    limit = min(limit, 500)

    try:
        browser = RepoBrowser(local_checkout=cfg.repository.local_checkout)
        history = await browser.get_history(repo_path=plc.repo_path, limit=limit)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to retrieve git history for %s: %s", plc_name, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve git history: {exc}",
        )

    return [
        CommitEntry(
            sha=entry["sha"],
            message=entry["message"],
            author=entry["author"],
            timestamp=entry["timestamp"],
        )
        for entry in history
    ]
