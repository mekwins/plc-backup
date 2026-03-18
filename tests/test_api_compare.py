"""
Tests for POST /api/compare/upload and related compare endpoints.
"""
import io
import json
import textwrap
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.db.models import CompareJob, Base
from app.db.session import get_db
from app.main import app


# ---------------------------------------------------------------------------
# Sample L5X files
# ---------------------------------------------------------------------------

L5X_A = textwrap.dedent(
    """\
    <?xml version="1.0" encoding="UTF-8"?>
    <RSLogix5000Content SchemaRevision="1.0">
      <Controller Name="PLC_A">
        <Tag Name="Speed" DataType="REAL" Value="100.0" />
      </Controller>
    </RSLogix5000Content>
    """
).encode()

L5X_B = textwrap.dedent(
    """\
    <?xml version="1.0" encoding="UTF-8"?>
    <RSLogix5000Content SchemaRevision="1.0">
      <Controller Name="PLC_A">
        <Tag Name="Speed" DataType="REAL" Value="120.0" />
      </Controller>
    </RSLogix5000Content>
    """
).encode()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(db_session, app_config):
    from app.config.loader import reset_config_cache

    reset_config_cache()

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_compare_upload_returns_job_id(db_session, app_config):
    """POST /api/compare/upload returns a job_id."""
    Base.metadata.create_all(bind=db_session.bind)

    def _override_db():
        yield db_session

    with patch("app.config.loader._config_cache", app_config), \
         patch("app.api.compare.get_config", return_value=app_config), \
         patch("app.api.compare.AiCompareAdapter"):
        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/compare/upload",
            files={
                "file_a": ("left.L5X", io.BytesIO(L5X_A), "application/xml"),
                "file_b": ("right.L5X", io.BytesIO(L5X_B), "application/xml"),
            },
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data


def test_compare_upload_creates_db_record(db_session, app_config):
    """Upload compare creates a CompareJob record in the database."""
    Base.metadata.create_all(bind=db_session.bind)

    def _override_db():
        yield db_session

    with patch("app.config.loader._config_cache", app_config), \
         patch("app.api.compare.get_config", return_value=app_config), \
         patch("app.api.compare.AiCompareAdapter"):
        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/compare/upload",
            files={
                "file_a": ("left.L5X", io.BytesIO(L5X_A), "application/xml"),
                "file_b": ("right.L5X", io.BytesIO(L5X_B), "application/xml"),
            },
        )

    app.dependency_overrides.clear()

    job_id = response.json()["job_id"]
    job = db_session.query(CompareJob).filter(CompareJob.id == job_id).first()
    assert job is not None
    assert job.compare_mode == "upload"


def test_get_compare_job_not_found(db_session, app_config):
    """GET /api/compare/jobs/{unknown_id} returns 404."""
    Base.metadata.create_all(bind=db_session.bind)

    def _override_db():
        yield db_session

    with patch("app.config.loader._config_cache", app_config), \
         patch("app.api.compare.get_config", return_value=app_config):
        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/api/compare/jobs/00000000-0000-0000-0000-000000000000"
        )

    app.dependency_overrides.clear()
    assert response.status_code == 404


def test_get_compare_job_result(db_session, app_config):
    """GET /api/compare/jobs/{job_id} returns status and result for a completed job."""
    Base.metadata.create_all(bind=db_session.bind)

    job_id = str(uuid.uuid4())
    result_data = {"summary": "Minor change", "riskLevel": "low", "highlights": [], "sections": {}}
    job = CompareJob(
        id=job_id,
        plc_name="TestPLC",
        status="success",
        result_json=json.dumps(result_data),
    )
    db_session.add(job)
    db_session.commit()

    def _override_db():
        yield db_session

    with patch("app.config.loader._config_cache", app_config), \
         patch("app.api.compare.get_config", return_value=app_config):
        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(f"/api/compare/jobs/{job_id}")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["result"]["summary"] == "Minor change"


def test_get_raw_diff(db_session, app_config):
    """GET /api/compare/jobs/{job_id}/raw-diff returns the raw diff text."""
    Base.metadata.create_all(bind=db_session.bind)

    job_id = str(uuid.uuid4())
    job = CompareJob(
        id=job_id,
        plc_name="TestPLC",
        status="success",
        raw_diff="--- a\n+++ b\n+new line\n",
    )
    db_session.add(job)
    db_session.commit()

    def _override_db():
        yield db_session

    with patch("app.config.loader._config_cache", app_config):
        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(f"/api/compare/jobs/{job_id}/raw-diff")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert "+new line" in data["raw_diff"]
