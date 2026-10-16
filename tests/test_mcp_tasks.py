import asyncio
import json
from pathlib import Path

import pytest

from dehydrater.mcp_tasks import WorkspaceBusyError, WorkspaceRun, mark_interrupted


async def test_workspace_run_writes_completed_state_and_removes_lock(tmp_path: Path) -> None:
    output = tmp_path / "output"
    async with WorkspaceRun(output, tmp_path / "input.mp4"):
        assert (output / ".dehydrater-mcp" / "run.lock").exists()
        assert (
            json.loads((output / ".dehydrater-mcp" / "run.json").read_text())["status"] == "running"
        )

    assert not (output / ".dehydrater-mcp" / "run.lock").exists()
    assert (
        json.loads((output / ".dehydrater-mcp" / "run.json").read_text())["status"] == "completed"
    )


async def test_workspace_run_marks_cancelled(tmp_path: Path) -> None:
    output = tmp_path / "output"
    with pytest.raises(asyncio.CancelledError):
        async with WorkspaceRun(output, tmp_path / "input.mp4"):
            raise asyncio.CancelledError

    assert (
        json.loads((output / ".dehydrater-mcp" / "run.json").read_text())["status"] == "cancelled"
    )


async def test_workspace_run_rejects_live_lock(tmp_path: Path) -> None:
    output = tmp_path / "output"
    first = WorkspaceRun(output, tmp_path / "input.mp4")
    await first.__aenter__()
    try:
        with pytest.raises(WorkspaceBusyError):
            async with WorkspaceRun(output, tmp_path / "input.mp4"):
                pass
    finally:
        await first.__aexit__(None, None, None)


def test_mark_interrupted(tmp_path: Path) -> None:
    output = tmp_path / "output" / ".dehydrater-mcp"
    output.mkdir(parents=True)
    (output / "run.json").write_text(json.dumps({"status": "running"}))

    mark_interrupted(output.parent)

    assert json.loads((output / "run.json").read_text())["status"] == "interrupted"
