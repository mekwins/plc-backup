"""
Deterministic file system layout helpers for PLC backup artifacts.

Layout convention
-----------------
<backup_root>/
  <plc_name>/
    <YYYY-MM-DDTHH-MM-SSZ>/    ← timestamped snapshot
      <plc_name>.ACD
      <plc_name>.L5X
      manifest.json
      checksums.json
      run.log
    latest/                    ← symlink-like "latest" folder (populated by job runner)
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path


def get_backup_dir(backup_root: str, plc_name: str, timestamp: datetime) -> Path:
    """
    Return the Path for a timestamped backup snapshot directory.

    The directory is **not** created by this function; callers are responsible
    for calling ``.mkdir(parents=True, exist_ok=True)`` before writing files.

    Parameters
    ----------
    backup_root:
        Root directory for all PLC backups (e.g. ``C:\\PLCBackups``).
    plc_name:
        Logical PLC name used as the second path component.
    timestamp:
        UTC timestamp of the backup run.  The folder name is formatted as
        ``YYYY-MM-DDTHH-MM-SSZ`` (colons replaced with dashes for Windows
        filesystem compatibility).

    Returns
    -------
    Path
    """
    folder_name = timestamp.strftime("%Y-%m-%dT%H-%M-%SZ")
    return Path(backup_root) / plc_name / folder_name


def get_latest_dir(backup_root: str, plc_name: str) -> Path:
    """
    Return the Path for the ``latest`` symlink-style directory.

    The job runner copies (or replaces) this directory after every successful
    backup so that downstream consumers always find the most recent artifacts
    at a stable path.

    Parameters
    ----------
    backup_root:
        Root directory for all PLC backups.
    plc_name:
        Logical PLC name.

    Returns
    -------
    Path
    """
    return Path(backup_root) / plc_name / "latest"
