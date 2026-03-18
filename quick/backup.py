"""
Quick & dirty PLC backup script.
Hardcode your PLC details in the constants below, then run.

Requires Windows + Rockwell Logix Designer SDK installed.
SDK wheel: pip install path\to\logix_designer_sdk-2.0.1-py3-none-any.whl
"""

import sys
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# ---------------------------------------------------------------------------
# EDIT THESE CONSTANTS
# ---------------------------------------------------------------------------
PLC_NAME = "Line01-CellA-Main"
PLC_COMM_PATH = r"AB_ETHIP-1\10.40.12.15\Backplane\0"
OUTPUT_DIR = r"C:\PLCBackups\quick"
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)
log = logging.getLogger(__name__)


async def backup() -> None:
    try:
        from logix_designer_sdk.logix_project import LogixProject
    except ImportError:
        log.error(
            "logix_designer_sdk is not installed.\n"
            "Install it from the SDK examples folder:\n"
            r"  pip install C:\Users\Public\Documents\Studio 5000"
            r"\Logix Designer SDK\python\Examples\logix_designer_sdk-*.whl"
        )
        sys.exit(1)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    out = Path(OUTPUT_DIR) / PLC_NAME / timestamp
    out.mkdir(parents=True, exist_ok=True)

    acd_path = out / f"{PLC_NAME}.ACD"
    l5x_path = out / f"{PLC_NAME}.L5X"

    log.info("Connecting to %s via %s", PLC_NAME, PLC_COMM_PATH)

    # NOTE: confirm the exact upload-to-new-project call against the installed
    # SDK examples at:
    #   C:\Users\Public\Documents\Studio 5000\Logix Designer SDK\python\Examples
    project = await LogixProject.open_logix_project(str(acd_path), log)
    try:
        await project.set_communications_path(PLC_COMM_PATH)
        log.info("Saving ACD -> %s", acd_path)
        await project.save()
        log.info("Exporting L5X -> %s", l5x_path)
        await project.export_l5x(str(l5x_path))
        log.info("Done. Files written to %s", out)
    finally:
        await project.close()


if __name__ == "__main__":
    asyncio.run(backup())
