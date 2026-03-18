"""
Tests for app.storage.file_layout
"""
from datetime import datetime, timezone
from pathlib import Path

from app.storage.file_layout import get_backup_dir, get_latest_dir


def test_backup_dir_path_format():
    """Path uses ISO-like format with dashes instead of colons (Windows-safe)."""
    ts = datetime(2025, 3, 18, 10, 30, 45, tzinfo=timezone.utc)
    result = get_backup_dir("/backups", "Line01-CellA", ts)
    assert result == Path("/backups/Line01-CellA/2025-03-18T10-30-45Z")


def test_backup_dir_uses_backup_root():
    ts = datetime(2024, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    result = get_backup_dir("C:\\PLCBackups", "MyPLC", ts)
    # Use parts to avoid OS path separator issues in assertions
    assert result.parts[-1] == "2024-06-01T00-00-00Z"
    assert result.parts[-2] == "MyPLC"


def test_latest_dir_path():
    """latest dir is <backup_root>/<plc_name>/latest."""
    result = get_latest_dir("/backups", "Line02-CellB")
    assert result == Path("/backups/Line02-CellB/latest")


def test_backup_dir_different_timestamps_are_different():
    ts1 = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    ts2 = datetime(2025, 1, 1, 0, 1, 0, tzinfo=timezone.utc)
    assert get_backup_dir("/root", "PLC", ts1) != get_backup_dir("/root", "PLC", ts2)


def test_backup_dir_different_plcs_are_different():
    ts = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert get_backup_dir("/root", "PLC1", ts) != get_backup_dir("/root", "PLC2", ts)
