"""
Read-only git repository browser for PLC backup history.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


class RepoBrowser:
    """
    Browse the git history of the backup repository without modifying it.

    Parameters
    ----------
    local_checkout:
        Absolute path to the local working copy.
    """

    def __init__(self, local_checkout: str) -> None:
        self._checkout = Path(local_checkout)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_history(
        self,
        repo_path: str,
        limit: int = 50,
    ) -> List[Dict[str, str]]:
        """
        Return the git log for *repo_path* as a list of commit dicts.

        Each entry contains: ``sha``, ``message``, ``author``, ``timestamp``.

        Parameters
        ----------
        repo_path:
            Relative path inside the repository (e.g. ``line01/cella/main``).
        limit:
            Maximum number of commits to return.
        """
        fmt = "%H%x1f%s%x1f%an%x1f%aI"  # sha, subject, author, ISO timestamp
        output = await self._git_output(
            "log",
            f"--max-count={limit}",
            f"--format={fmt}",
            "--",
            repo_path,
        )

        commits = []
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\x1f")
            if len(parts) == 4:
                commits.append(
                    {
                        "sha": parts[0],
                        "message": parts[1],
                        "author": parts[2],
                        "timestamp": parts[3],
                    }
                )
            else:
                logger.warning("Unexpected git log line: %r", line)
        return commits

    async def get_file_at_commit(
        self,
        commit_sha: str,
        file_path: str,
    ) -> bytes:
        """
        Retrieve the raw bytes of *file_path* at the given *commit_sha*.

        Parameters
        ----------
        commit_sha:
            Full or abbreviated git commit SHA.
        file_path:
            Path relative to the repository root.

        Returns
        -------
        bytes
            Raw file contents at that commit.
        """
        ref = f"{commit_sha}:{file_path}"
        return await self._git_bytes("show", ref)

    async def list_versions(self, repo_path: str) -> List[str]:
        """
        List all version timestamp folders that exist in the repository under
        *repo_path*.

        Queries the most recent commit's tree so it reflects the current HEAD.
        """
        output = await self._git_output(
            "ls-tree",
            "--name-only",
            "HEAD",
            repo_path + "/",
        )
        versions = [
            line.strip()
            for line in output.splitlines()
            if line.strip()
        ]
        return versions

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _git_output(self, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=str(self._checkout),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"git {' '.join(args)} failed: "
                f"{stderr.decode(errors='replace').strip()}"
            )
        return stdout.decode(errors="replace")

    async def _git_bytes(self, *args: str) -> bytes:
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=str(self._checkout),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"git {' '.join(args)} failed: "
                f"{stderr.decode(errors='replace').strip()}"
            )
        return stdout
