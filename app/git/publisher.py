"""
Git-based artifact publisher.

Uses the subprocess git CLI (not GitPython) so that SSH keys, credential
helpers, and environment variables configured on the host are respected
without any extra configuration inside the process.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


class GitPublisherError(RuntimeError):
    """Raised when a git CLI command fails."""


class GitPublisher:
    """
    Publishes PLC backup artifacts to a remote git repository.

    Parameters
    ----------
    local_checkout:
        Absolute path to the local working copy of the backup repository.
    remote_url:
        Remote URL (used for the initial clone if the checkout does not exist).
    branch:
        Branch to push to (e.g. ``main``).
    username:
        Git author name to use in commits.
    """

    def __init__(
        self,
        local_checkout: str,
        remote_url: str,
        branch: str,
        username: str,
    ) -> None:
        self._checkout = Path(local_checkout)
        self._remote_url = remote_url
        self._branch = branch
        self._username = username

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def publish(
        self,
        artifacts: List[Path],
        repo_path: str,
        commit_message: str,
    ) -> str:
        """
        Copy *artifacts* into the repository under *repo_path*, commit, push,
        and return the new commit SHA.

        Parameters
        ----------
        artifacts:
            List of local file Paths to copy into the repository.
        repo_path:
            Relative path inside the repository root where files will be
            placed (e.g. ``line01/cella/main``).
        commit_message:
            Commit message for the git commit.

        Returns
        -------
        str
            The full commit SHA of the newly created commit.
        """
        await self._ensure_checkout()
        await self._pull()

        # Copy artifacts into the repo
        dest_dir = self._checkout / repo_path / _timestamp_folder()
        dest_dir.mkdir(parents=True, exist_ok=True)

        for artifact in artifacts:
            if artifact.exists():
                shutil.copy2(artifact, dest_dir / artifact.name)
                logger.debug("Copied %s -> %s", artifact, dest_dir)
            else:
                logger.warning("Artifact not found, skipping: %s", artifact)

        # Stage, commit, push
        await self._git("add", str(dest_dir.relative_to(self._checkout)))
        await self._git(
            "commit",
            "--allow-empty",
            "-m", commit_message,
            "--author", f"{self._username} <{self._username}@plc-backup>",
        )
        await self._git("push", "origin", self._branch)

        sha = await self._get_head_sha()
        logger.info("Published backup artifacts to git, commit=%s", sha)
        return sha

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_checkout(self) -> None:
        """Clone the repository if the local checkout does not exist."""
        if not (self._checkout / ".git").exists():
            logger.info(
                "Local checkout not found at %s, cloning %s",
                self._checkout,
                self._remote_url,
            )
            self._checkout.mkdir(parents=True, exist_ok=True)
            await self._git_bare(
                "clone",
                "--branch", self._branch,
                self._remote_url,
                str(self._checkout),
            )

    async def _pull(self) -> None:
        """Pull latest changes from the remote."""
        await self._git("pull", "--ff-only", "origin", self._branch)

    async def _get_head_sha(self) -> str:
        """Return the current HEAD commit SHA."""
        stdout, _ = await self._git_output("rev-parse", "HEAD")
        return stdout.strip()

    async def _git(self, *args: str) -> None:
        """Run a git command in the local checkout; raise on failure."""
        await self._run_git(self._checkout, *args)

    async def _git_bare(self, *args: str) -> None:
        """Run a git command outside any specific working directory."""
        await self._run_git(None, *args)

    async def _git_output(self, *args: str) -> tuple[str, str]:
        """Run a git command and return (stdout, stderr)."""
        cmd = ["git", *args]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(self._checkout),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise GitPublisherError(
                f"git {' '.join(args)} failed (rc={proc.returncode}): "
                f"{stderr.decode(errors='replace').strip()}"
            )
        return stdout.decode(errors="replace"), stderr.decode(errors="replace")

    @staticmethod
    async def _run_git(cwd, *args: str) -> None:
        cmd = ["git", *args]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd) if cwd else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise GitPublisherError(
                f"git {' '.join(args)} failed (rc={proc.returncode}): "
                f"{stderr.decode(errors='replace').strip()}"
            )


def _timestamp_folder() -> str:
    """ISO-8601-ish folder name safe for Windows filesystems."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
