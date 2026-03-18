"""
Configuration loader for the PLC Backup Platform.
Reads YAML file, validates with Pydantic, and caches the result as a singleton.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from app.config.schema import AppConfig

# ---------------------------------------------------------------------------
# Module-level singleton cache
# ---------------------------------------------------------------------------
_config_cache: Optional[AppConfig] = None

# Default path is relative to the project root (i.e., config/app.yaml)
_DEFAULT_CONFIG_PATH = str(
    Path(__file__).resolve().parents[2] / "config" / "app.yaml"
)


def load_config(path: str) -> AppConfig:
    """
    Load and validate the application configuration from a YAML file.

    Parameters
    ----------
    path:
        Absolute or relative path to the YAML configuration file.

    Returns
    -------
    AppConfig
        Fully-validated configuration object.

    Raises
    ------
    FileNotFoundError
        If the given *path* does not exist.
    ValueError
        If the YAML is malformed or fails Pydantic validation.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path.resolve()}"
        )

    with config_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if raw is None:
        raise ValueError(f"Configuration file is empty: {config_path.resolve()}")

    try:
        return AppConfig.model_validate(raw)
    except ValidationError as exc:
        # Re-raise with a more user-friendly message that includes field names.
        friendly = "\n".join(
            f"  [{' -> '.join(str(loc) for loc in e['loc'])}] {e['msg']}"
            for e in exc.errors()
        )
        raise ValueError(
            f"Invalid configuration in {config_path.resolve()}:\n{friendly}"
        ) from exc


def get_config(path: Optional[str] = None) -> AppConfig:
    """
    Return the cached AppConfig singleton, loading it on first call.

    Parameters
    ----------
    path:
        Optional override path. Defaults to ``config/app.yaml`` next to the
        project root. Can also be set via the ``PLC_BACKUP_CONFIG`` environment
        variable.

    Returns
    -------
    AppConfig
    """
    global _config_cache

    if _config_cache is not None:
        return _config_cache

    resolved_path = (
        path
        or os.environ.get("PLC_BACKUP_CONFIG")
        or _DEFAULT_CONFIG_PATH
    )

    _config_cache = load_config(resolved_path)
    return _config_cache


def reset_config_cache() -> None:
    """Reset the config singleton — useful in tests."""
    global _config_cache
    _config_cache = None
