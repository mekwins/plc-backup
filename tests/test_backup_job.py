"""
Tests for app.jobs.backup_job — SDK client and git publisher are mocked.
"""
import asyncio
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.config.schema import AppConfig, PlcDefinition, ServiceConfig, StorageConfig, RepositoryConfig, AiConfig, LoggingConfig, DatabaseConfig
from app.db.models import BackupJob, Base
from app.jobs.backup_job import BackupJobRunner, _create_job_record
from app.plc.models import BackupResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        service=ServiceConfig(
            environment="test",
            scan_timeout_seconds=2,
            upload_timeout_minutes=5,
            max_parallel_backups=2,
        ),
        storage=StorageConfig(backup_root=str(tmp_path / "backups"), temp_root=str(tmp_path / "temp")),
        repository=RepositoryConfig(
            provider="github",
            url="git@github.com:test/repo.git",
            branch="main",
            local_checkout=str(tmp_path / "repo"),
            username="bot",
        ),
        ai=AiConfig(
            provider="azure_openai",
            endpoint="https://example.com/",
            api_key_env="KEY",
            model="gpt-4.1",
            prompt_profile="controls-engineering",
            max_input_chars=5000,
            max_tokens=100,
        ),
        logging=LoggingConfig(level="DEBUG", file_path=str(tmp_path / "out.log")),
        database=DatabaseConfig(url="sqlite:///:memory:"),
        plcs=[
            PlcDefinition(
                name="TestPLC",
                ip="10.0.0.1",
                slot=0,
                path="AB_ETHIP-1\\10.0.0.1\\Backplane\\0",
                enabled=True,
                schedule="hourly",
                repo_path="test/plc",
            ),
            PlcDefinition(
                name="DisabledPLC",
                ip="10.0.0.2",
                slot=0,
                path="AB_ETHIP-1\\10.0.0.2\\Backplane\\0",
                enabled=False,
                schedule="daily",
                repo_path="test/plc2",
            ),
        ],
    )


@pytest.fixture
def mock_sdk(tmp_path: Path):
    sdk = AsyncMock()
    sdk.upload_backup = AsyncMock(
        return_value={
            "acd_path": str(tmp_path / "backups" / "TestPLC" / "ts" / "TestPLC.ACD"),
            "l5x_path": str(tmp_path / "backups" / "TestPLC" / "ts" / "TestPLC.L5X"),
            "project_name": "TestProject",
            "comm_path": "AB_ETHIP-1\\10.0.0.1\\Backplane\\0",
            "status": "success",
            "firmware_revision": "32.11",
            "catalog_number": "1756-L83E",
        }
    )
    return sdk


@pytest.fixture
def mock_git():
    git = AsyncMock()
    git.publish = AsyncMock(return_value="abc123deadbeef")
    return git


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_backup_success(minimal_config, db_session, mock_sdk, mock_git, tmp_path):
    """Full successful backup pipeline updates DB to success and returns result."""
    Base.metadata.create_all(bind=db_session.bind)

    plc = minimal_config.plcs[0]
    job_id = _create_job_record(db_session, plc)

    # Create fake artifact files so checksums don't fail
    backup_dir = tmp_path / "backups" / "TestPLC"
    backup_dir.mkdir(parents=True)

    with (
        patch("app.jobs.backup_job.is_reachable", new=AsyncMock(return_value=True)),
        patch(
            "app.storage.manifests.compute_sha256",
            return_value="aabbcc",
        ),
    ):
        runner = BackupJobRunner(
            config=minimal_config,
            db=db_session,
            sdk_client=mock_sdk,
            git_publisher=mock_git,
        )
        result = await runner.run_backup_for_plc(plc, job_id)

    assert result.status == "success"
    assert result.plc_name == "TestPLC"

    job = db_session.query(BackupJob).filter(BackupJob.id == job_id).first()
    assert job.status == "success"
    assert job.git_commit_sha == "abc123deadbeef"


@pytest.mark.asyncio
async def test_run_backup_unreachable(minimal_config, db_session, mock_sdk, mock_git):
    """Unreachable PLC causes backup to fail gracefully."""
    Base.metadata.create_all(bind=db_session.bind)

    plc = minimal_config.plcs[0]
    job_id = _create_job_record(db_session, plc)

    with patch("app.jobs.backup_job.is_reachable", new=AsyncMock(return_value=False)):
        runner = BackupJobRunner(
            config=minimal_config,
            db=db_session,
            sdk_client=mock_sdk,
            git_publisher=mock_git,
        )
        result = await runner.run_backup_for_plc(plc, job_id)

    assert result.status == "failed"
    assert "not reachable" in (result.error or "")

    job = db_session.query(BackupJob).filter(BackupJob.id == job_id).first()
    assert job.status == "failed"


@pytest.mark.asyncio
async def test_run_backup_sdk_failure_isolated(minimal_config, db_session, mock_git):
    """SDK error for one PLC is isolated — doesn't propagate as exception."""
    Base.metadata.create_all(bind=db_session.bind)

    failing_sdk = AsyncMock()
    failing_sdk.upload_backup = AsyncMock(side_effect=RuntimeError("SDK failure"))

    plc = minimal_config.plcs[0]
    job_id = _create_job_record(db_session, plc)

    with patch("app.jobs.backup_job.is_reachable", new=AsyncMock(return_value=True)):
        runner = BackupJobRunner(
            config=minimal_config,
            db=db_session,
            sdk_client=failing_sdk,
            git_publisher=mock_git,
        )
        result = await runner.run_backup_for_plc(plc, job_id)

    assert result.status == "failed"
    assert "SDK failure" in (result.error or "")


@pytest.mark.asyncio
async def test_run_all_enabled_skips_disabled(minimal_config, db_session, mock_sdk, mock_git):
    """run_all_enabled only processes enabled PLCs."""
    Base.metadata.create_all(bind=db_session.bind)

    with (
        patch("app.jobs.backup_job.is_reachable", new=AsyncMock(return_value=True)),
        patch(
            "app.storage.manifests.compute_sha256",
            return_value="aabbcc",
        ),
    ):
        runner = BackupJobRunner(
            config=minimal_config,
            db=db_session,
            sdk_client=mock_sdk,
            git_publisher=mock_git,
        )
        results = await runner.run_all_enabled()

    # Only TestPLC is enabled; DisabledPLC must not appear
    names = [r.plc_name for r in results]
    assert "TestPLC" in names
    assert "DisabledPLC" not in names


@pytest.mark.asyncio
async def test_run_all_enabled_filter_by_name(minimal_config, db_session, mock_sdk, mock_git):
    """filter_names restricts to the requested PLC only."""
    Base.metadata.create_all(bind=db_session.bind)

    # Add a second enabled PLC to config
    minimal_config.plcs.append(
        PlcDefinition(
            name="SecondPLC",
            ip="10.0.0.3",
            slot=0,
            path="path3",
            enabled=True,
            schedule="daily",
            repo_path="test/plc3",
        )
    )
    mock_sdk.upload_backup.return_value = {
        "acd_path": "/tmp/x.ACD",
        "l5x_path": "/tmp/x.L5X",
        "project_name": "X",
        "comm_path": "path",
        "status": "success",
        "firmware_revision": None,
        "catalog_number": None,
    }

    with (
        patch("app.jobs.backup_job.is_reachable", new=AsyncMock(return_value=True)),
        patch("app.storage.manifests.compute_sha256", return_value="aa"),
    ):
        runner = BackupJobRunner(
            config=minimal_config,
            db=db_session,
            sdk_client=mock_sdk,
            git_publisher=mock_git,
        )
        results = await runner.run_all_enabled(filter_names=["TestPLC"])

    names = [r.plc_name for r in results]
    assert "TestPLC" in names
    assert "SecondPLC" not in names
