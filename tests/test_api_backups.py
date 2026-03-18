"""
Tests for POST /api/backups/run and GET /api/backups/jobs/{job_id}
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.db.models import BackupJob, Base
from app.db.session import get_db
from app.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(db_session, config):
    from app.config.loader import reset_config_cache

    reset_config_cache()

    def _override_db():
        yield db_session

    with patch("app.config.loader._config_cache", config):
        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, raise_server_exceptions=False)
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_run_backup_returns_job_ids(db_session, app_config):
    """POST /api/backups/run returns job_ids for enabled PLCs."""
    Base.metadata.create_all(bind=db_session.bind)

    def _override_db():
        yield db_session

    with patch("app.config.loader._config_cache", app_config), \
         patch("app.api.backups.get_config", return_value=app_config), \
         patch("app.api.backups.RockwellSdkClient"), \
         patch("app.api.backups.GitPublisher"), \
         patch("app.api.backups.BackupJobRunner"):
        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/api/backups/run", json={})

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert "job_ids" in data
    assert len(data["job_ids"]) >= 1


def test_run_backup_with_specific_plc(db_session, app_config):
    """POST /api/backups/run with plc_names filters to the specified PLC."""
    Base.metadata.create_all(bind=db_session.bind)

    def _override_db():
        yield db_session

    with patch("app.config.loader._config_cache", app_config), \
         patch("app.api.backups.get_config", return_value=app_config), \
         patch("app.api.backups.RockwellSdkClient"), \
         patch("app.api.backups.GitPublisher"), \
         patch("app.api.backups.BackupJobRunner"):
        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/backups/run", json={"plc_names": ["TestPLC"]}
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert len(data["job_ids"]) == 1


def test_run_backup_unknown_plc_returns_404(db_session, app_config):
    """POST with unknown PLC name returns 404."""
    Base.metadata.create_all(bind=db_session.bind)

    def _override_db():
        yield db_session

    with patch("app.config.loader._config_cache", app_config), \
         patch("app.api.backups.get_config", return_value=app_config), \
         patch("app.api.backups.RockwellSdkClient"), \
         patch("app.api.backups.GitPublisher"), \
         patch("app.api.backups.BackupJobRunner"):
        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/backups/run", json={"plc_names": ["NonExistentPLC"]}
        )

    app.dependency_overrides.clear()
    assert response.status_code == 404


def test_get_job_status(db_session, app_config):
    """GET /api/backups/jobs/{job_id} returns job data for an existing job."""
    Base.metadata.create_all(bind=db_session.bind)

    # Pre-insert a job
    job_id = str(uuid.uuid4())
    job = BackupJob(
        id=job_id,
        plc_name="TestPLC",
        ip="10.0.0.1",
        comm_path="AB_ETHIP-1\\10.0.0.1\\Backplane\\0",
        status="success",
    )
    db_session.add(job)
    db_session.commit()

    def _override_db():
        yield db_session

    with patch("app.config.loader._config_cache", app_config), \
         patch("app.api.backups.get_config", return_value=app_config):
        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(f"/api/backups/jobs/{job_id}")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == job_id
    assert data["status"] == "success"
    assert data["plc_name"] == "TestPLC"


def test_get_job_status_not_found(db_session, app_config):
    """GET /api/backups/jobs/{unknown_id} returns 404."""
    Base.metadata.create_all(bind=db_session.bind)

    def _override_db():
        yield db_session

    with patch("app.config.loader._config_cache", app_config), \
         patch("app.api.backups.get_config", return_value=app_config):
        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/backups/jobs/00000000-0000-0000-0000-000000000000")

    app.dependency_overrides.clear()
    assert response.status_code == 404
