"""
Manifest and checksum helpers for PLC backup artifacts.

Every backup snapshot directory contains three metadata files:
  manifest.json   — structured metadata about the backup run
  checksums.json  — SHA-256 hashes of every artifact file
  run.log         — human-readable log lines from the backup run
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def compute_sha256(path: Path) -> str:
    """
    Compute the SHA-256 hex digest of *path*.

    Reads in 64 KB chunks to avoid loading large ACD files entirely into RAM.
    """
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Writer helpers
# ---------------------------------------------------------------------------

def write_manifest(directory: Path, data: Dict[str, Any]) -> Path:
    """
    Write *data* as pretty-printed JSON to ``<directory>/manifest.json``.

    Returns
    -------
    Path
        Absolute path of the written file.
    """
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(
        json.dumps(data, indent=2, default=str), encoding="utf-8"
    )
    return manifest_path


def write_checksums(directory: Path, files: List[Path]) -> Path:
    """
    Compute SHA-256 checksums for each file in *files* and write them to
    ``<directory>/checksums.json``.

    Parameters
    ----------
    directory:
        Destination directory (must already exist or will be created).
    files:
        List of artifact Paths to hash.  Paths that do not exist are skipped
        with a ``null`` digest so the file is still represented in the record.

    Returns
    -------
    Path
        Absolute path of the written checksums file.
    """
    directory.mkdir(parents=True, exist_ok=True)
    checksums: Dict[str, Optional[str]] = {}
    for f in files:
        if f.exists():
            checksums[f.name] = compute_sha256(f)
        else:
            checksums[f.name] = None

    checksum_path = directory / "checksums.json"
    checksum_path.write_text(
        json.dumps(checksums, indent=2), encoding="utf-8"
    )
    return checksum_path


def write_run_log(directory: Path, log_lines: List[str]) -> Path:
    """
    Write human-readable *log_lines* to ``<directory>/run.log``.

    Each line is written as-is; a newline is appended if the line does not
    already end with one.

    Returns
    -------
    Path
        Absolute path of the written log file.
    """
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / "run.log"
    with log_path.open("w", encoding="utf-8") as fh:
        for line in log_lines:
            fh.write(line if line.endswith("\n") else line + "\n")
    return log_path


# ---------------------------------------------------------------------------
# Manifest builder
# ---------------------------------------------------------------------------

def build_manifest(
    plc_def,          # PlcDefinition (avoid circular import — use duck typing)
    backup_result,    # BackupResult
    job_id: str,
    timestamp: datetime,
    git_commit_sha: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build the full manifest dictionary for a completed backup run.

    Parameters
    ----------
    plc_def:
        ``PlcDefinition`` instance from the app config.
    backup_result:
        ``BackupResult`` dataclass returned by the SDK client.
    job_id:
        UUID string for the backup job record.
    timestamp:
        UTC datetime of the backup snapshot.
    git_commit_sha:
        Commit SHA produced by the git publisher (may be None if git push
        has not yet happened or failed).

    Returns
    -------
    dict
        Structured manifest suitable for serialisation to JSON.
    """
    return {
        "schema_version": "1.0",
        "job_id": job_id,
        "timestamp": timestamp.isoformat() + "Z",
        "plc": {
            "name": plc_def.name,
            "ip": plc_def.ip,
            "slot": plc_def.slot,
            "comm_path": plc_def.path,
            "line": plc_def.line,
            "area": plc_def.area,
            "repo_path": plc_def.repo_path,
            "tags": plc_def.tags,
        },
        "project": {
            "name": backup_result.project_name,
            "firmware_revision": backup_result.firmware_revision,
            "catalog_number": backup_result.catalog_number,
        },
        "artifacts": {
            "acd": backup_result.acd_path,
            "l5x": backup_result.l5x_path,
        },
        "status": backup_result.status,
        "error": backup_result.error,
        "git_commit_sha": git_commit_sha,
    }
