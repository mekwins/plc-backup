"""
Tests for GET /api/plcs and GET /api/plcs/{plc_name}/history
"""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_list_plcs_returns_plc_inventory(db_session, app_config):
    """GET /api/plcs returns the list of PLCs from the config."""

    def _override_db():
        yield db_session

    with patch("app.config.loader._config_cache", app_config), \
         patch("app.api.plcs.get_config", return_value=app_config):
        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/plcs")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    names = [p["name"] for p in data]
    assert "TestPLC" in names


def test_list_plcs_includes_required_fields(db_session, app_config):
    """Each PLC entry contains the required fields."""

    def _override_db():
        yield db_session

    with patch("app.config.loader._config_cache", app_config), \
         patch("app.api.plcs.get_config", return_value=app_config):
        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/plcs")

    app.dependency_overrides.clear()

    plc = next(p for p in response.json() if p["name"] == "TestPLC")
    for field in ("name", "ip", "slot", "path", "enabled", "schedule", "repo_path", "tags"):
        assert field in plc, f"Field {field!r} missing from PLC response"


def test_get_plc_history(db_session, app_config):
    """GET /api/plcs/{plc_name}/history returns commit history list."""
    mock_history = [
        {
            "sha": "abc123",
            "message": "backup: TestPLC 2025-03-18",
            "author": "bot",
            "timestamp": "2025-03-18T10:00:00+00:00",
        }
    ]

    def _override_db():
        yield db_session

    with patch("app.config.loader._config_cache", app_config), \
         patch("app.api.plcs.get_config", return_value=app_config), \
         patch(
             "app.api.plcs.RepoBrowser.get_history",
             new=AsyncMock(return_value=mock_history),
         ):
        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/plcs/TestPLC/history")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["sha"] == "abc123"
    assert data[0]["author"] == "bot"


def test_get_plc_history_unknown_plc(db_session, app_config):
    """GET /api/plcs/{unknown}/history returns 404."""

    def _override_db():
        yield db_session

    with patch("app.config.loader._config_cache", app_config), \
         patch("app.api.plcs.get_config", return_value=app_config):
        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/plcs/NonExistentPLC/history")

    app.dependency_overrides.clear()
    assert response.status_code == 404


def test_list_plcs_empty_config(tmp_path, db_session):
    """When config has no PLCs, GET /api/plcs returns an empty list."""
    import textwrap
    from app.config.loader import load_config, reset_config_cache

    reset_config_cache()
    cfg_file = tmp_path / "empty_plcs.yaml"
    cfg_file.write_text(
        textwrap.dedent(
            """\
            service:
              environment: test
              scan_timeout_seconds: 2
              upload_timeout_minutes: 5
              max_parallel_backups: 1
            storage:
              backup_root: /tmp
              temp_root: /tmp/t
            repository:
              provider: github
              url: git@github.com:x/y.git
              branch: main
              local_checkout: /tmp/r
              username: bot
            ai:
              provider: azure_openai
              endpoint: https://x.com/
              api_key_env: K
              model: gpt-4.1
              prompt_profile: controls-engineering
              max_input_chars: 1000
              max_tokens: 100
            logging:
              level: INFO
              file_path: /tmp/log.log
            database:
              url: sqlite:///:memory:
            plcs: []
            """
        )
    )
    empty_cfg = load_config(str(cfg_file))

    def _override_db():
        yield db_session

    with patch("app.config.loader._config_cache", empty_cfg), \
         patch("app.api.plcs.get_config", return_value=empty_cfg):
        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/plcs")

    app.dependency_overrides.clear()
    reset_config_cache()

    assert response.status_code == 200
    assert response.json() == []
