"""
Shared pytest fixtures and configuration.
"""
import sys
import asyncio

# Windows ProactorEventLoop is required for subprocess support.
# On other platforms this guard is a no-op so CI passes on macOS/Linux.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import os
import tempfile
import textwrap
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path when running tests directly
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Minimal valid YAML config used across multiple test modules
# ---------------------------------------------------------------------------
MINIMAL_YAML = textwrap.dedent(
    """\
    service:
      environment: test
      scan_timeout_seconds: 2
      upload_timeout_minutes: 5
      max_parallel_backups: 1

    storage:
      backup_root: /tmp/plc_backups
      temp_root: /tmp/plc_backups/temp

    repository:
      provider: github
      url: git@github.com:test/plc-backups.git
      branch: main
      local_checkout: /tmp/plc-repo
      username: test-user

    ai:
      provider: azure_openai
      endpoint: https://test.openai.azure.com/
      api_key_env: TEST_AI_KEY
      model: gpt-4.1
      prompt_profile: controls-engineering
      max_input_chars: 10000
      max_tokens: 500

    logging:
      level: DEBUG
      file_path: /tmp/plc_backups/test.log

    database:
      url: sqlite:///:memory:

    plcs:
      - name: TestPLC
        ip: 10.0.0.1
        slot: 0
        path: AB_ETHIP-1\\10.0.0.1\\Backplane\\0
        line: TestLine
        area: TestArea
        enabled: true
        schedule: hourly
        repo_path: testline/testarea/main
        tags:
          - test
    """
)


@pytest.fixture
def yaml_config_file(tmp_path: Path) -> Path:
    """Write MINIMAL_YAML to a temp file and return the Path."""
    cfg_file = tmp_path / "app.yaml"
    cfg_file.write_text(MINIMAL_YAML)
    return cfg_file


@pytest.fixture
def app_config(yaml_config_file: Path):
    """Return a validated AppConfig loaded from MINIMAL_YAML."""
    from app.config.loader import load_config, reset_config_cache

    reset_config_cache()
    cfg = load_config(str(yaml_config_file))
    yield cfg
    reset_config_cache()


# ---------------------------------------------------------------------------
# In-memory SQLite engine / session for API tests
# ---------------------------------------------------------------------------

@pytest.fixture
def db_engine():
    from app.db.models import Base

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


# ---------------------------------------------------------------------------
# FastAPI test client with overridden DB and config
# ---------------------------------------------------------------------------

@pytest.fixture
def test_client(app_config, db_engine):
    """TestClient wired to in-memory DB and test config."""
    from app.main import app
    from app.db.session import get_db
    from app.config.loader import get_config, reset_config_cache
    from sqlalchemy.orm import sessionmaker

    reset_config_cache()

    # Patch get_config to return test config
    TestSession = sessionmaker(bind=db_engine)

    def _override_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db

    with TestClient(app, raise_server_exceptions=True) as client:
        yield client

    app.dependency_overrides.clear()
    reset_config_cache()
