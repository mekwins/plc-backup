"""
Pydantic configuration schemas for the PLC Backup Platform.
All settings are validated at load time; missing required fields raise a clear ValidationError.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class PlcDefinition(BaseModel):
    name: str
    ip: str
    slot: int = 0
    path: str
    line: Optional[str] = None
    area: Optional[str] = None
    enabled: bool = True
    schedule: str = "daily"
    repo_path: str
    tags: List[str] = Field(default_factory=list)


class ServiceConfig(BaseModel):
    environment: str = "dev"
    scan_timeout_seconds: int = 5
    upload_timeout_minutes: int = 15
    max_parallel_backups: int = 2


class StorageConfig(BaseModel):
    backup_root: str
    temp_root: str


class RepositoryConfig(BaseModel):
    provider: str = "github"
    url: str
    branch: str = "main"
    local_checkout: str
    username: str


class AiConfig(BaseModel):
    provider: str = "azure_openai"
    endpoint: str
    api_key_env: str
    model: str = "gpt-4.1"
    prompt_profile: str = "controls-engineering"
    max_input_chars: int = 500_000
    max_tokens: int = 4000


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file_path: str


class DatabaseConfig(BaseModel):
    url: str = "sqlite:///./plc_backup.db"


class AppConfig(BaseModel):
    service: ServiceConfig
    storage: StorageConfig
    repository: RepositoryConfig
    ai: AiConfig
    logging: LoggingConfig
    database: DatabaseConfig
    plcs: List[PlcDefinition] = Field(default_factory=list)
