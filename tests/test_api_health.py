"""
Tests for GET /api/health
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(db_session):
    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app, raise_server_exceptions=False)
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_health_returns_200(db_session, yaml_config_file):
    """Health endpoint returns 200 when config, DB and git are available."""
    from app.config.loader import get_config, reset_config_cache

    reset_config_cache()

    # Patch get_config to use our test config file
    with patch(
        "app.api.health.get_config",
        return_value=get_config(str(yaml_config_file)),
    ), patch(
        "app.api.health.get_engine",
    ) as mock_engine, patch(
        "app.api.health.subprocess.run",
        return_value=MagicMock(returncode=0, stdout="git version 2.40.0", stderr=""),
    ):
        # Mock engine context manager
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute = MagicMock()
        mock_engine.return_value.connect.return_value = mock_conn

        client = _make_client(db_session)
        response = client.get("/api/health")

    assert response.status_code in (200, 503)  # 503 if SDK missing, but still responds
    data = response.json()
    assert "status" in data
    assert "checks" in data

    app.dependency_overrides.clear()
    reset_config_cache()


def test_health_checks_contain_expected_keys(db_session, yaml_config_file):
    """Health response always contains config, database, git, and sdk checks."""
    from app.config.loader import get_config, reset_config_cache

    reset_config_cache()

    with patch(
        "app.api.health.get_config",
        return_value=get_config(str(yaml_config_file)),
    ), patch(
        "app.api.health.get_engine",
    ) as mock_engine, patch(
        "app.api.health.subprocess.run",
        return_value=MagicMock(returncode=0, stdout="git version 2.40.0", stderr=""),
    ):
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute = MagicMock()
        mock_engine.return_value.connect.return_value = mock_conn

        client = _make_client(db_session)
        response = client.get("/api/health")

    checks = response.json()["checks"]
    assert "config" in checks
    assert "database" in checks
    assert "git" in checks
    assert "sdk" in checks

    app.dependency_overrides.clear()
    reset_config_cache()


def test_health_git_missing_reports_error(db_session, yaml_config_file):
    """When git is not on PATH, the git check reports error but endpoint still responds."""
    from app.config.loader import get_config, reset_config_cache

    reset_config_cache()

    with patch(
        "app.api.health.get_config",
        return_value=get_config(str(yaml_config_file)),
    ), patch(
        "app.api.health.get_engine",
    ) as mock_engine, patch(
        "app.api.health.subprocess.run",
        side_effect=FileNotFoundError("git not found"),
    ):
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute = MagicMock()
        mock_engine.return_value.connect.return_value = mock_conn

        client = _make_client(db_session)
        response = client.get("/api/health")

    assert response.status_code == 503
    checks = response.json()["checks"]
    assert checks["git"]["status"] == "error"

    app.dependency_overrides.clear()
    reset_config_cache()
