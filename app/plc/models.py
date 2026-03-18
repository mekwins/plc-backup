"""
Internal dataclass models for PLC operation results.
These are lightweight data-transfer objects used between the SDK client,
backup job runner, and storage layers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BackupResult:
    """Outcome of a single PLC backup operation."""

    plc_name: str
    acd_path: str
    l5x_path: str
    project_name: str
    comm_path: str
    status: str  # "success" | "failed" | "skipped"
    firmware_revision: Optional[str] = None
    catalog_number: Optional[str] = None
    error: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.status == "success"
