"""
SQLAlchemy ORM models for the PLC Backup Platform.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, String, Text, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def _new_uuid() -> str:
    return str(uuid.uuid4())


class BackupJob(Base):
    """Tracks every backup attempt for a PLC controller."""

    __tablename__ = "backup_jobs"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    plc_name = Column(String(255), nullable=False, index=True)
    ip = Column(String(64), nullable=False)
    comm_path = Column(String(512), nullable=True)
    status = Column(
        Enum("pending", "running", "success", "failed", name="backup_status"),
        nullable=False,
        default="pending",
    )
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    acd_path = Column(String(1024), nullable=True)
    l5x_path = Column(String(1024), nullable=True)
    manifest_path = Column(String(1024), nullable=True)
    git_commit_sha = Column(String(64), nullable=True)
    error_detail = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<BackupJob id={self.id!r} plc={self.plc_name!r} status={self.status!r}>"
        )


class CompareJob(Base):
    """Tracks every compare request (git-to-git or upload-based)."""

    __tablename__ = "compare_jobs"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    plc_name = Column(String(255), nullable=True, index=True)
    left_ref = Column(String(256), nullable=True)
    right_ref = Column(String(256), nullable=True)
    compare_mode = Column(String(64), nullable=True)
    status = Column(
        Enum("pending", "running", "success", "failed", name="compare_status"),
        nullable=False,
        default="pending",
    )
    result_json = Column(Text, nullable=True)
    raw_diff = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    finished_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<CompareJob id={self.id!r} plc={self.plc_name!r} status={self.status!r}>"
        )
