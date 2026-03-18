"""
ICMP reachability check for PLC hosts.

NOTE: The backup runner is explicitly Windows-only due to the Rockwell Logix
Designer SDK constraint. The ping command below uses Windows-specific flags.
On other platforms the check will gracefully return False rather than crash.
"""
from __future__ import annotations

import asyncio
import logging
import sys

logger = logging.getLogger(__name__)


async def is_reachable(ip: str, timeout: float = 3.0) -> bool:
    """
    Asynchronously ping *ip* once and return True if the host responds.

    Parameters
    ----------
    ip:
        IPv4 address (or hostname) to probe.
    timeout:
        How many seconds to wait for a reply (default 3.0).

    Returns
    -------
    bool
        True if the host replies to ICMP echo within *timeout* seconds.
    """
    try:
        if sys.platform == "win32":
            # -n 1: send 1 packet; -w: wait in milliseconds
            cmd = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), ip]
        else:
            # Fallback for development on macOS/Linux
            cmd = ["ping", "-c", "1", "-W", str(int(timeout)), ip]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=timeout + 1)
        reachable = proc.returncode == 0
        logger.debug("Reachability check %s -> %s", ip, reachable)
        return reachable

    except asyncio.TimeoutError:
        logger.warning("Reachability check timed out for %s", ip)
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("Reachability check failed for %s: %s", ip, exc)
        return False
