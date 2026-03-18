"""
Tests for app.storage.manifests
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.storage.manifests import (
    build_manifest,
    compute_sha256,
    write_checksums,
    write_manifest,
    write_run_log,
)
from app.config.schema import PlcDefinition
from app.plc.models import BackupResult


# ---------------------------------------------------------------------------
# compute_sha256
# ---------------------------------------------------------------------------

def test_sha256_known_value(tmp_path: Path):
    """SHA-256 of a known string matches expected digest."""
    # echo -n "hello" | sha256sum => 2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824
    f = tmp_path / "test.txt"
    f.write_bytes(b"hello")
    assert compute_sha256(f) == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def test_sha256_different_content_differs(tmp_path: Path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_bytes(b"content_a")
    b.write_bytes(b"content_b")
    assert compute_sha256(a) != compute_sha256(b)


# ---------------------------------------------------------------------------
# write_manifest
# ---------------------------------------------------------------------------

def test_write_manifest_creates_file(tmp_path: Path):
    data = {"key": "value", "number": 42}
    path = write_manifest(tmp_path, data)
    assert path.exists()
    assert path.name == "manifest.json"
    loaded = json.loads(path.read_text())
    assert loaded["key"] == "value"
    assert loaded["number"] == 42


def test_write_manifest_creates_parent_dir(tmp_path: Path):
    dest = tmp_path / "a" / "b" / "c"
    write_manifest(dest, {"x": 1})
    assert (dest / "manifest.json").exists()


# ---------------------------------------------------------------------------
# write_checksums
# ---------------------------------------------------------------------------

def test_write_checksums_hashes_files(tmp_path: Path):
    f1 = tmp_path / "file1.txt"
    f2 = tmp_path / "file2.txt"
    f1.write_bytes(b"abc")
    f2.write_bytes(b"xyz")
    path = write_checksums(tmp_path, [f1, f2])
    loaded = json.loads(path.read_text())
    assert "file1.txt" in loaded
    assert "file2.txt" in loaded
    assert loaded["file1.txt"] == compute_sha256(f1)


def test_write_checksums_missing_file_is_null(tmp_path: Path):
    missing = tmp_path / "missing.bin"
    path = write_checksums(tmp_path, [missing])
    loaded = json.loads(path.read_text())
    assert loaded["missing.bin"] is None


# ---------------------------------------------------------------------------
# write_run_log
# ---------------------------------------------------------------------------

def test_write_run_log(tmp_path: Path):
    lines = ["Starting backup", "Reachability OK", "Upload complete"]
    path = write_run_log(tmp_path, lines)
    text = path.read_text()
    for line in lines:
        assert line in text


def test_write_run_log_ensures_newlines(tmp_path: Path):
    path = write_run_log(tmp_path, ["no newline"])
    text = path.read_text()
    assert text.endswith("\n")


# ---------------------------------------------------------------------------
# build_manifest
# ---------------------------------------------------------------------------

def _make_plc_def():
    return PlcDefinition(
        name="TestPLC",
        ip="10.0.0.1",
        slot=0,
        path="AB_ETHIP-1\\10.0.0.1\\Backplane\\0",
        line="TestLine",
        area="TestArea",
        enabled=True,
        schedule="hourly",
        repo_path="test/plc",
        tags=["production"],
    )


def _make_backup_result():
    return BackupResult(
        plc_name="TestPLC",
        acd_path="/backups/TestPLC.ACD",
        l5x_path="/backups/TestPLC.L5X",
        project_name="TestProject",
        comm_path="AB_ETHIP-1\\10.0.0.1\\Backplane\\0",
        status="success",
        firmware_revision="32.11",
        catalog_number="1756-L83E",
    )


def test_build_manifest_structure():
    plc = _make_plc_def()
    result = _make_backup_result()
    ts = datetime(2025, 3, 18, 10, 0, 0, tzinfo=timezone.utc)
    manifest = build_manifest(plc, result, job_id="abc-123", timestamp=ts)

    assert manifest["job_id"] == "abc-123"
    assert manifest["status"] == "success"
    assert manifest["plc"]["name"] == "TestPLC"
    assert manifest["plc"]["ip"] == "10.0.0.1"
    assert manifest["project"]["firmware_revision"] == "32.11"
    assert manifest["artifacts"]["acd"] == "/backups/TestPLC.ACD"
    assert manifest["git_commit_sha"] is None


def test_build_manifest_with_git_sha():
    plc = _make_plc_def()
    result = _make_backup_result()
    ts = datetime(2025, 3, 18, 10, 0, 0, tzinfo=timezone.utc)
    manifest = build_manifest(plc, result, job_id="x", timestamp=ts, git_commit_sha="deadbeef")
    assert manifest["git_commit_sha"] == "deadbeef"


def test_build_manifest_timestamp_format():
    plc = _make_plc_def()
    result = _make_backup_result()
    ts = datetime(2025, 3, 18, 10, 0, 0, tzinfo=timezone.utc)
    manifest = build_manifest(plc, result, job_id="x", timestamp=ts)
    assert "2025-03-18" in manifest["timestamp"]
