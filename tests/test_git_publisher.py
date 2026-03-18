"""
Tests for app.git.publisher — git CLI calls are mocked via asyncio subprocess.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
import pytest_asyncio

from app.git.publisher import GitPublisher, GitPublisherError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_proc(returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""):
    """Create a mock asyncio Process."""
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.wait = AsyncMock(return_value=returncode)
    return proc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_publish_calls_git_commands(tmp_path: Path):
    """publish() runs pull, add, commit, push in order."""
    # Simulate an existing .git directory
    (tmp_path / ".git").mkdir()

    # Create a dummy artifact
    artifact = tmp_path / "TestPLC.L5X"
    artifact.write_bytes(b"<xml/>")

    sha_bytes = b"deadbeef1234567890abcdef1234567890abcdef\n"

    call_count = {"n": 0}

    async def fake_create_subprocess_exec(*args, **kwargs):
        call_count["n"] += 1
        # Last call is rev-parse HEAD → return sha
        if "rev-parse" in args:
            return _make_proc(stdout=sha_bytes)
        return _make_proc()

    with patch(
        "app.git.publisher.asyncio.create_subprocess_exec",
        side_effect=fake_create_subprocess_exec,
    ), patch("app.git.publisher.shutil.copy2"):
        publisher = GitPublisher(
            local_checkout=str(tmp_path),
            remote_url="git@github.com:test/repo.git",
            branch="main",
            username="bot",
        )
        sha = await publisher.publish(
            artifacts=[artifact],
            repo_path="line01/plc1",
            commit_message="backup: TestPLC 2025-01-01T00-00-00Z",
        )

    assert sha == "deadbeef1234567890abcdef1234567890abcdef"
    # At minimum: pull, add, commit, push, rev-parse = 5 calls
    assert call_count["n"] >= 5


@pytest.mark.asyncio
async def test_publish_raises_on_git_failure(tmp_path: Path):
    """GitPublisherError is raised when a git command exits non-zero."""
    (tmp_path / ".git").mkdir()

    async def fake_failing_proc(*args, **kwargs):
        return _make_proc(returncode=1, stderr=b"not a git repo")

    with patch(
        "app.git.publisher.asyncio.create_subprocess_exec",
        side_effect=fake_failing_proc,
    ):
        publisher = GitPublisher(
            local_checkout=str(tmp_path),
            remote_url="git@github.com:test/repo.git",
            branch="main",
            username="bot",
        )
        with pytest.raises(GitPublisherError):
            await publisher.publish(
                artifacts=[],
                repo_path="line01/plc1",
                commit_message="test",
            )


@pytest.mark.asyncio
async def test_commit_message_format(tmp_path: Path):
    """Commit message is passed verbatim to git commit -m."""
    (tmp_path / ".git").mkdir()
    commit_messages = []

    async def fake_proc(*args, **kwargs):
        if "-m" in args:
            idx = list(args).index("-m")
            commit_messages.append(args[idx + 1])
        if "rev-parse" in args:
            return _make_proc(stdout=b"abc123\n")
        return _make_proc()

    expected_message = "backup: Line01-CellA-Main 2025-03-18T10-00-00Z"

    with patch(
        "app.git.publisher.asyncio.create_subprocess_exec",
        side_effect=fake_proc,
    ), patch("app.git.publisher.shutil.copy2"):
        publisher = GitPublisher(
            local_checkout=str(tmp_path),
            remote_url="git@github.com:test/repo.git",
            branch="main",
            username="bot",
        )
        await publisher.publish(
            artifacts=[],
            repo_path="line01/cella/main",
            commit_message=expected_message,
        )

    assert expected_message in commit_messages
