# PLC Backup Platform — Package Contents

## Overview

This is the PLC Backup Platform: a Python application that automatically connects to Rockwell Logix PLCs, backs up controller projects, publishes artifacts to GitHub, and provides a web API for browsing history and running AI-powered comparisons of PLC versions.

---

## Platform Requirement

**The backup runner is Windows-only.**

The Rockwell Logix Designer SDK runs exclusively on Windows. The following must be installed on the backup host before running backups:

- Windows 10 Pro/Enterprise, Windows 11 Enterprise, or Windows Server 2022
- Studio 5000 Logix Designer version 33 or later
- Logix Designer SDK version 2.01 or later
- FactoryTalk Linx
- FactoryTalk Services Platform
- FactoryTalk Activation 4.04 or later
- Python 3.12 or later

The API server (`app/main.py`) can run on any platform for development and testing. SDK operations will raise `SdkNotAvailableError` on non-Windows hosts or when the SDK wheel is not installed.

---

## Package Contents

### `config/app.yaml`
Main configuration file. Edit this before running the platform.

Key sections:
- `service` — scan timeout, upload timeout, parallelism limit
- `storage` — local backup root and temp paths (Windows paths)
- `repository` — GitHub repository URL, branch, local checkout path
- `ai` — Azure OpenAI or compatible endpoint, model, API key env var name
- `logging` — log level and file path
- `database` — SQLAlchemy connection URL (defaults to SQLite)
- `plcs` — list of controller definitions (name, IP, communication path, schedule, repo path)

### `requirements.txt`
All Python dependencies. Install with:
```
pip install -r requirements.txt
```

Also install the Rockwell SDK wheel from the SDK examples folder:
```
pip install path\to\logix_designer_sdk-2.0.1-py3-none-any.whl
```
The wheel is located at:
```
C:\Users\Public\Documents\Studio 5000\Logix Designer SDK\python\Examples
```

---

### `app/main.py`
FastAPI application entry point. Sets `WindowsProactorEventLoopPolicy` on Windows, configures structured JSON logging, registers all API routers, initialises the database, and starts the backup scheduler on startup.

### `app/config/schema.py`
Pydantic v2 models for the full configuration schema: `AppConfig`, `PlcDefinition`, `ServiceConfig`, `StorageConfig`, `RepositoryConfig`, `AiConfig`, `LoggingConfig`, `DatabaseConfig`.

### `app/config/loader.py`
Loads and validates `config/app.yaml` (or the path in env var `PLC_BACKUP_CONFIG`). Exposes a `get_config()` singleton.

---

### `app/plc/rockwell_sdk_client.py`
Adapter wrapping the Rockwell Logix Designer SDK. Imports `logix_designer_sdk` with a try/except guard — if the SDK is not installed the module loads but raises `SdkNotAvailableError` at call time.

Exposes:
- `RockwellSdkClient.upload_backup(plc_name, comm_path, output_dir)` — uploads controller project to a new local ACD, exports L5X, returns paths and metadata.

**Note:** The exact upload-to-new-project method signature must be validated against the installed SDK examples at `C:\Users\Public\Documents\Studio 5000\Logix Designer SDK\python\Examples`. The current implementation follows the documented interaction pattern.

### `app/plc/reachability.py`
`is_reachable(ip, timeout)` — async ICMP ping using subprocess. Uses Windows flags (`ping -n 1 -w`) on Windows and POSIX flags (`ping -c 1 -W`) elsewhere.

### `app/plc/models.py`
`BackupResult` dataclass — internal result type returned by the SDK adapter.

---

### `app/storage/file_layout.py`
Generates deterministic local folder paths:
- `get_backup_dir(backup_root, plc_name, timestamp)` → `<backup_root>/<plc_name>/2026-03-18T21-15-00Z/`
- `get_latest_dir(backup_root, plc_name)` → `<backup_root>/<plc_name>/latest/`

### `app/storage/manifests.py`
Creates backup artifacts:
- `build_manifest(...)` — assembles the full manifest dict per spec
- `write_manifest(dir, data)` — writes `manifest.json`
- `write_checksums(dir, files)` — writes `checksums.json` with SHA-256 hashes
- `write_run_log(dir, log_lines)` — writes `run.log`
- `compute_sha256(path)` — returns hex SHA-256 of a file

---

### `app/git/publisher.py`
`GitPublisher` — publishes backup artifacts to GitHub using subprocess git CLI.

Operations: clone (if not present), pull, copy files to timestamped subfolder, `git add`, `git commit`, `git push`. Returns commit SHA.

Commit message format:
```
backup(plc): <PLC name> <IP> at <timestamp>
```

### `app/git/repo_browser.py`
`RepoBrowser` — reads history from the local Git working copy.

- `get_history(repo_path, limit)` — returns list of commits (SHA, message, author, timestamp)
- `get_file_at_commit(commit_sha, file_path)` — returns file content bytes at a specific revision
- `list_versions(repo_path)` — lists version directories tracked in Git

---

### `app/compare/xml_normalizer.py`
`normalize_l5x(content: bytes) -> bytes` — normalises L5X XML before comparison:
- Sorts element attributes alphabetically
- Strips insignificant whitespace
- Removes known noisy fields: `ExportDate`, `ExportOptions`, `Owner`, `SFC`

### `app/compare/deterministic_diff.py`
- `compute_text_diff(a, b)` — unified text diff
- `extract_section(xml_bytes, tag)` — extracts named elements with content hash
- `compute_xml_sections_diff(xml_a, xml_b)` — compares per section (controller, tasks, programs, routines, AOIs, UDTs, tags, modules) and returns added/removed/modified counts

### `app/compare/prompts.py`
- `CONTROLS_ENGINEERING_PROMPT` — system prompt instructing the AI to summarise functional PLC changes, identify safety and operational risks, and separate cosmetic XML noise from logic changes
- `build_user_prompt(plc_name, sections_diff, diff_excerpt)` — builds the user message including structured diff summary and L5X excerpt

### `app/compare/ai_compare.py`
`AiCompareAdapter` — calls Azure OpenAI or OpenAI-compatible endpoint via httpx with tenacity retries.

- Truncates input to `max_input_chars`
- Returns `{summary, riskLevel, highlights, sections}`
- API key read from env var specified in `ai.api_key_env`

---

### `app/jobs/backup_job.py`
`BackupJobRunner` — orchestrates the full backup pipeline per PLC:

1. Test reachability
2. Call SDK adapter
3. Write manifest, checksums, run log
4. Publish to Git
5. Update database job record

`run_all_enabled(filter_names)` — runs all enabled PLCs with concurrency limited by `max_parallel_backups` using `asyncio.Semaphore`. Each PLC failure is isolated.

### `app/jobs/scheduler.py`
`BackupScheduler` — APScheduler `AsyncIOScheduler` wrapper.

Schedule names: `hourly` (interval 1h), `daily` (interval 24h), `weekly` (interval 7d). Arbitrary cron strings (e.g. `0 2 * * *`) are also supported.

---

### `app/api/backups.py`
REST router:
- `POST /api/backups/run` — trigger backup for one or more PLCs (or all enabled); returns job ID
- `GET /api/backups/jobs/{job_id}` — return job status and artifact paths

### `app/api/compare.py`
REST router:
- `POST /api/compare/git` — compare two Git-backed L5X versions by commit reference
- `POST /api/compare/upload` — compare two uploaded L5X files (multipart form)
- `GET /api/compare/jobs/{job_id}` — return compare status and AI summary
- `GET /api/compare/jobs/{job_id}/raw-diff` — return raw unified diff text

### `app/api/plcs.py`
REST router:
- `GET /api/plcs` — list configured PLC inventory from config
- `GET /api/plcs/{plc_name}/history` — list Git backup history for a PLC

### `app/api/health.py`
REST router:
- `GET /api/health` — structured health check: config loaded, database accessible, git CLI available, SDK installed

---

### `app/db/models.py`
SQLAlchemy ORM:
- `BackupJob` — tracks backup runs (PLC name, IP, status, artifact paths, Git SHA, error detail)
- `CompareJob` — tracks compare requests (references, mode, status, result JSON, raw diff)

### `app/db/session.py`
`engine`, `SessionLocal`, `get_db()` FastAPI dependency, `init_db()` table creator.

---

### `scripts/run_backup.py`
CLI entry point for running backups directly (without the API server):

```
python scripts/run_backup.py                    # back up all enabled PLCs
python scripts/run_backup.py --plc Line01-CellA-Main
python scripts/run_backup.py --config path\to\app.yaml
```

Sets `WindowsProactorEventLoopPolicy` at the top.

### `scripts/run_api.py`
Starts the FastAPI server with uvicorn:

```
python scripts/run_api.py
python scripts/run_api.py --host 0.0.0.0 --port 8000
```

Sets `WindowsProactorEventLoopPolicy` at the top.

---

### `tests/`
Pytest test suite — 13 test files covering every module.

- `conftest.py` — shared fixtures: in-memory SQLite DB, test config YAML, FastAPI `TestClient` with dependency injection overrides. Also sets `WindowsProactorEventLoopPolicy` on Windows.
- `test_config.py` — config load/validate, missing field errors
- `test_xml_normalizer.py` — attribute sorting, noise removal, round-trip
- `test_deterministic_diff.py` — text diff output, XML section extraction, diff counts
- `test_file_layout.py` — path generation
- `test_manifests.py` — SHA-256, manifest build, file write/read
- `test_git_publisher.py` — mocked subprocess, commit message format
- `test_ai_compare.py` — mocked httpx, prompt building, truncation
- `test_backup_job.py` — mocked SDK and git, full run pipeline, failure isolation
- `test_api_health.py`, `test_api_backups.py`, `test_api_compare.py`, `test_api_plcs.py` — API endpoint tests

Run with:
```
pytest tests/
```

---

## Quick Start

1. Install dependencies:
   ```
   pip install -r requirements.txt
   pip install path\to\logix_designer_sdk-2.0.1-py3-none-any.whl
   ```

2. Edit `config/app.yaml` with your PLC IPs, communication paths, GitHub repo, and AI endpoint.

3. Set environment variable for the AI key:
   ```
   set AZURE_OPENAI_KEY=your-key-here
   ```

4. Start the API server:
   ```
   python scripts/run_api.py
   ```

5. Trigger a manual backup via API:
   ```
   POST http://localhost:8000/api/backups/run
   {"plc_names": ["Line01-CellA-Main"]}
   ```

6. Or run backup directly from CLI:
   ```
   python scripts/run_backup.py --plc Line01-CellA-Main
   ```

7. Check health:
   ```
   GET http://localhost:8000/api/health
   ```

---

## asyncio Windows Note

All entry points (`app/main.py`, `scripts/run_backup.py`, `scripts/run_api.py`, `tests/conftest.py`) call:

```python
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
```

This is required on Windows for asyncio subprocess support (used by git CLI calls and ping reachability checks). It is guarded by `sys.platform == "win32"` so the code is harmless on other platforms.
