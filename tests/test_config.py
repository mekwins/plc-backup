"""
Tests for config loader and schema validation.
"""
import textwrap
from pathlib import Path

import pytest

from app.config.loader import load_config, reset_config_cache
from app.config.schema import AppConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "app.yaml"
    p.write_text(textwrap.dedent(content))
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_load_valid_config(yaml_config_file: Path):
    """Loading a valid YAML file returns a fully populated AppConfig."""
    reset_config_cache()
    cfg = load_config(str(yaml_config_file))
    assert isinstance(cfg, AppConfig)
    assert cfg.service.environment == "test"
    assert len(cfg.plcs) == 1
    assert cfg.plcs[0].name == "TestPLC"
    assert cfg.plcs[0].ip == "10.0.0.1"
    assert cfg.plcs[0].tags == ["test"]


def test_load_missing_file_raises(tmp_path: Path):
    """FileNotFoundError is raised if the config file does not exist."""
    reset_config_cache()
    with pytest.raises(FileNotFoundError, match="not found"):
        load_config(str(tmp_path / "nonexistent.yaml"))


def test_empty_yaml_raises(tmp_path: Path):
    """An empty YAML file raises ValueError."""
    reset_config_cache()
    empty = tmp_path / "empty.yaml"
    empty.write_text("")
    with pytest.raises(ValueError):
        load_config(str(empty))


def test_missing_required_field_raises(tmp_path: Path):
    """Omitting a required field (e.g. storage.backup_root) raises ValueError."""
    reset_config_cache()
    # storage section is missing entirely
    yaml = _write_yaml(
        tmp_path,
        """\
        service:
          environment: test
          scan_timeout_seconds: 2
          upload_timeout_minutes: 5
          max_parallel_backups: 1
        repository:
          provider: github
          url: git@github.com:test/repo.git
          branch: main
          local_checkout: /tmp/repo
          username: bot
        ai:
          provider: azure_openai
          endpoint: https://example.com/
          api_key_env: KEY
          model: gpt-4.1
          prompt_profile: controls-engineering
          max_input_chars: 1000
          max_tokens: 100
        logging:
          level: INFO
          file_path: /tmp/out.log
        database:
          url: sqlite:///:memory:
        plcs: []
        """,
    )
    with pytest.raises(ValueError):
        load_config(str(yaml))


def test_plc_defaults(tmp_path: Path):
    """PlcDefinition optional fields default correctly."""
    reset_config_cache()
    yaml = _write_yaml(
        tmp_path,
        """\
        service:
          environment: dev
          scan_timeout_seconds: 5
          upload_timeout_minutes: 15
          max_parallel_backups: 2
        storage:
          backup_root: /backups
          temp_root: /tmp
        repository:
          provider: github
          url: git@github.com:org/repo.git
          branch: main
          local_checkout: /repo
          username: bot
        ai:
          provider: azure_openai
          endpoint: https://example.com/
          api_key_env: KEY
          model: gpt-4.1
          prompt_profile: controls-engineering
          max_input_chars: 100000
          max_tokens: 4000
        logging:
          level: INFO
          file_path: /tmp/log.log
        database:
          url: sqlite:///./test.db
        plcs:
          - name: MyPLC
            ip: 192.168.1.1
            path: AB_ETHIP-1\\192.168.1.1\\Backplane\\0
            schedule: daily
            repo_path: factory/plc1
        """,
    )
    cfg = load_config(str(yaml))
    plc = cfg.plcs[0]
    assert plc.slot == 0
    assert plc.enabled is True
    assert plc.tags == []
    assert plc.line is None
    assert plc.area is None


def test_multiple_plcs(yaml_config_file: Path, tmp_path: Path):
    """Multiple PLCs can be defined and all are returned."""
    reset_config_cache()
    content = (yaml_config_file.read_text()
               .replace(
        "plcs:\n  - name: TestPLC",
        "plcs:\n  - name: PLC1\n    ip: 10.0.0.1\n    path: p1\n    schedule: daily\n    repo_path: r1\n  - name: PLC2\n    ip: 10.0.0.2\n    path: p2\n    schedule: hourly\n    repo_path: r2",
    ))
    alt = tmp_path / "multi.yaml"
    alt.write_text(content)
    cfg = load_config(str(alt))
    names = [p.name for p in cfg.plcs]
    assert "PLC1" in names
    assert "PLC2" in names
