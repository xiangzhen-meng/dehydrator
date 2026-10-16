import asyncio
from pathlib import Path

import pytest

from dehydrater.config import Settings
from dehydrater.mcp_jobs import JobManager
from dehydrater.service import LectureReport, ProcessResult


def _settings() -> Settings:
    return Settings(
        {
            "DEHYDRATER_TRANSCRIBE_KEY": "test-transcribe-key",
            "DEHYDRATER_DEHYDRATE_KEY": "test-dehydrate-key",
        },
        [],
    )


def _result(output: Path) -> ProcessResult:
    return ProcessResult(outputs=[("脱水稿", output / "dehydrated.md")], report=LectureReport([]))


async def test_submit_returns_immediately_and_watch_reaches_completion(tmp_path: Path) -> None:
    started = asyncio.Event()

    async def runner(
        input_path: Path, output: Path, settings: object, on_event: object
    ) -> ProcessResult:
        assert input_path.name == "input.mp4"
        assert output.name == "out"
        started.set()
        await asyncio.sleep(0)
        (output / "dehydrated.md").write_text("done", encoding="utf-8")
        return _result(output)

    manager = JobManager(tmp_path / "state", runner=runner, settings_loader=_settings)
    output = tmp_path / "out"
    output.mkdir()
    state = await manager.submit(tmp_path / "input.mp4", output)
    assert state.status == "queued"
    await started.wait()
    result = await manager.watch(state.job_id, after_cursor=state.cursor, wait_seconds=1)
    assert result["status"] == "completed"
    assert result["events"]


async def test_watch_uses_cursor_and_rejects_long_wait(tmp_path: Path) -> None:
    async def runner(*args: object, **kwargs: object) -> ProcessResult:
        await asyncio.sleep(10)
        raise AssertionError("should be cancelled by test")

    manager = JobManager(tmp_path / "state", runner=runner, settings_loader=_settings)
    state = await manager.submit(tmp_path / "input.mp4", tmp_path / "out")
    result = await manager.watch(state.job_id, wait_seconds=0)
    next_cursor = result["next_cursor"]
    assert isinstance(next_cursor, int)
    assert next_cursor >= 1
    with pytest.raises(ValueError, match="20"):
        await manager.watch(state.job_id, wait_seconds=21)
    await manager.cancel(state.job_id)


async def test_cancel_stops_background_task(tmp_path: Path) -> None:
    started = asyncio.Event()

    async def runner(*args: object, **kwargs: object) -> ProcessResult:
        started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    manager = JobManager(tmp_path / "state", runner=runner, settings_loader=_settings)
    state = await manager.submit(tmp_path / "input.mp4", tmp_path / "out")
    await started.wait()
    cancelled = await manager.cancel(state.job_id)
    assert cancelled["status"] == "cancelled"


async def test_same_input_and_output_returns_existing_active_job(tmp_path: Path) -> None:
    gate = asyncio.Event()

    async def runner(*args: object, **kwargs: object) -> ProcessResult:
        await gate.wait()
        raise AssertionError("unreachable")

    manager = JobManager(tmp_path / "state", runner=runner, settings_loader=_settings)
    first = await manager.submit(tmp_path / "input.mp4", tmp_path / "out")
    second = await manager.submit(tmp_path / "input.mp4", tmp_path / "out")
    assert second.job_id == first.job_id
    await manager.cancel(first.job_id)
