"""
Start the PLC Backup Platform API server with uvicorn.

The API server can run on any platform (Windows, macOS, Linux).
SDK-backed backup operations will raise SdkNotAvailableError on non-Windows
hosts, but all other endpoints (health, compare, PLC inventory) work normally.

Usage:
    python scripts/run_api.py
    python scripts/run_api.py --host 127.0.0.1 --port 8080
    python scripts/run_api.py --reload   # development hot-reload
"""
import sys
import asyncio

# Windows ProactorEventLoop is required for asyncio subprocess support on Windows.
# Must be set before importing uvicorn or any asyncio-using module.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import argparse
from pathlib import Path

# Allow running from the project root without installing the package
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import uvicorn


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the PLC Backup Platform API server"
    )
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument(
        "--reload",
        action="store_true",
        default=False,
        help="Enable auto-reload (development only)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes (default: 1; use 1 when running with APScheduler)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers if not args.reload else 1,
        log_config=None,  # We configure logging via python-json-logger in app.main
    )
