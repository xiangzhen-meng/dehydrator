"""MCP 后台任务、状态快照和可重连事件流。"""

import asyncio
import contextlib
import json
import logging
import mimetypes
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal, cast

from dotenv import dotenv_values, find_dotenv
from platformdirs import user_data_path
from pydantic import BaseModel, ConfigDict

from dehydrater.bootstrap import load_settings
from dehydrater.config import Settings
from dehydrater.mcp_tasks import WorkspaceBusyError, WorkspaceRun, mark_interrupted
from dehydrater.pipeline.events import (
    PipelineEvent,
    StageFinished,
    StageProgress,
    StageSkipped,
    StageStarted,
    StageWarning,
)
from dehydrater.service import ProcessResult, run_process_result

logger = logging.getLogger(__name__)

JobStatus = Literal[
    "queued",
    "running",
    "cancelling",
    "completed",
    "failed",
    "cancelled",
    "interrupted",
]
TerminalStatus = frozenset({"completed", "failed", "cancelled", "interrupted"})
ActiveStatus = frozenset({"queued", "running", "cancelling"})
Runner = Callable[..., Awaitable[ProcessResult]]
SettingsLoader = Callable[[], Settings]


class JobState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    input_path: str
    output_dir: str
    status: JobStatus
    stage: str | None = None
    progress_done: int | None = None
    progress_total: int | None = None
    cursor: int = 0
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: float
    updated_at: float


class JobNotFoundError(KeyError):
    """请求的任务不存在。"""


class JobManager:
    """管理 MCP 进程内的后台任务，并把状态和事件持久化到磁盘。"""

    def __init__(
        self,
        root: Path | None = None,
        *,
        runner: Runner = run_process_result,
        settings_loader: SettingsLoader = load_settings,
    ) -> None:
        self.root = (root or _default_state_dir()).resolve()
        self.jobs_dir = self.root / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._runner = runner
        self._settings_loader = settings_loader
        self._states: dict[str, JobState] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._signals: dict[str, asyncio.Event] = {}
        self._load_states()

    async def submit(self, input_path: Path, output_dir: Path) -> JobState:
        existing = self._find_existing(input_path, output_dir)
        if existing is not None:
            return existing

        now = time.time()
        state = JobState(
            job_id=f"job_{uuid.uuid4().hex}",
            input_path=str(input_path),
            output_dir=str(output_dir),
            status="queued",
            created_at=now,
            updated_at=now,
        )
        self._states[state.job_id] = state
        self._signal(state.job_id)
        self._append_event(state, {"type": "queued"})
        self._tasks[state.job_id] = asyncio.create_task(self._run(state.job_id))
        return state

    async def get_status(self, job_id: str) -> dict[str, object]:
        return self._snapshot(self._state(job_id), events=[])

    async def watch(
        self, job_id: str, *, after_cursor: int = 0, wait_seconds: float = 20.0
    ) -> dict[str, object]:
        if after_cursor < 0:
            raise ValueError("after_cursor 不能小于 0")
        if not 0 <= wait_seconds <= 20:
            raise ValueError("wait_seconds 必须在 0 到 20 秒之间")

        state = self._state(job_id)
        signal = self._signal(job_id)
        deadline = time.monotonic() + wait_seconds
        while True:
            signal.clear()
            state = self._state(job_id)
            events = self._events_after(job_id, after_cursor)
            if events or state.status in TerminalStatus or wait_seconds == 0:
                return self._snapshot(state, events=events)

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return self._snapshot(state, events=[])
            try:
                await asyncio.wait_for(signal.wait(), timeout=remaining)
            except TimeoutError:
                return self._snapshot(self._state(job_id), events=[])

    async def cancel(self, job_id: str) -> dict[str, object]:
        state = self._state(job_id)
        if state.status in TerminalStatus:
            return self._snapshot(state, events=[])

        self._update(state, status="cancelling")
        self._append_event(state, {"type": "cancelling"})
        task = self._tasks.get(job_id)
        if task is None:
            self._update(state, status="interrupted")
            self._append_event(state, {"type": "interrupted"})
        else:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        return self._snapshot(self._state(job_id), events=[])

    def _load_states(self) -> None:
        for path in sorted(self.jobs_dir.glob("*/job.json")):
            try:
                state = JobState.model_validate_json(path.read_bytes())
            except (OSError, ValueError):
                logger.warning("忽略损坏的 MCP 任务记录：%s", path, exc_info=True)
                continue
            self._states[state.job_id] = state
            self._signal(state.job_id)
            if state.status in {"running", "cancelling"}:
                mark_interrupted(Path(state.output_dir))
                self._update(state, status="interrupted")
                self._append_event(state, {"type": "interrupted"})

    def _find_existing(self, input_path: Path, output_dir: Path) -> JobState | None:
        key = (str(input_path), str(output_dir))
        matches = [
            state for state in self._states.values() if (state.input_path, state.output_dir) == key
        ]
        for state in sorted(matches, key=lambda item: item.created_at, reverse=True):
            if state.status in ActiveStatus or state.status == "completed":
                return state
        return None

    async def _run(self, job_id: str) -> None:
        state = self._state(job_id)
        try:
            self._update(state, status="running")
            self._append_event(state, {"type": "started"})
            settings = self._settings_loader()
            if missing := settings.missing():
                raise ValueError("缺少配置：" + ", ".join(missing))
            async with WorkspaceRun(Path(state.output_dir), Path(state.input_path)):
                result = await self._runner(
                    Path(state.input_path),
                    Path(state.output_dir),
                    settings,
                    on_event=self._event_callback(state),
                )
            state.result = serialize_process_result(result)
            self._update(state, status="completed", stage=None, error=None)
            self._append_event(state, {"type": "completed", "result": state.result})
        except asyncio.CancelledError:
            self._update(state, status="cancelled", error=None)
            self._append_event(state, {"type": "cancelled"})
            raise
        except WorkspaceBusyError as error:
            self._update(state, status="failed", error=str(error))
            self._append_event(state, {"type": "failed", "error": str(error)})
        except Exception as error:
            logger.exception("MCP 任务失败：%s", job_id)
            self._update(state, status="failed", error=str(error))
            self._append_event(state, {"type": "failed", "error": str(error)})
        finally:
            self._tasks.pop(job_id, None)

    def _pipeline_event(self, state: JobState, event: PipelineEvent) -> None:
        payload: dict[str, Any]
        if isinstance(event, StageStarted):
            self._update(state, stage=event.stage, progress_done=0, progress_total=1)
            payload = {"type": "stage_started", "stage": event.stage}
        elif isinstance(event, StageSkipped):
            self._update(state, stage=event.stage, progress_done=1, progress_total=1)
            payload = {"type": "stage_skipped", "stage": event.stage}
        elif isinstance(event, StageProgress):
            self._update(
                state,
                stage=event.stage,
                progress_done=event.done,
                progress_total=event.total,
            )
            payload = {
                "type": "progress",
                "stage": event.stage,
                "done": event.done,
                "total": event.total,
            }
        elif isinstance(event, StageFinished):
            self._update(state, stage=event.stage, progress_done=1, progress_total=1)
            payload = {
                "type": "stage_finished",
                "stage": event.stage,
                "elapsed_seconds": event.elapsed_seconds,
            }
        elif isinstance(event, StageWarning):
            payload = {"type": "warning", "stage": event.stage, "message": event.message}
        else:
            return
        self._append_event(state, payload)

    def _state(self, job_id: str) -> JobState:
        try:
            return self._states[job_id]
        except KeyError:
            raise JobNotFoundError(job_id) from None

    def _signal(self, job_id: str) -> asyncio.Event:
        return self._signals.setdefault(job_id, asyncio.Event())

    def _update(self, state: JobState, **changes: object) -> None:
        for key, value in changes.items():
            setattr(state, key, value)
        state.updated_at = time.time()
        self._write_state(state)
        self._signal(state.job_id).set()

    def _append_event(self, state: JobState, payload: dict[str, Any]) -> None:
        state.cursor += 1
        event = {"cursor": state.cursor, "at": time.time(), **payload}
        path = self._events_path(state.job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        state.updated_at = time.time()
        self._write_state(state)
        self._signal(state.job_id).set()

    def _events_after(self, job_id: str, cursor: int) -> list[dict[str, Any]]:
        path = self._events_path(job_id)
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                decoded = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(decoded, dict):
                continue
            event = cast(dict[str, object], decoded)
            raw_cursor = event.get("cursor")
            if isinstance(raw_cursor, int) and raw_cursor > cursor:
                events.append(event)
        return events

    def _event_callback(self, state: JobState) -> Callable[[PipelineEvent], None]:
        return lambda event: self._pipeline_event(state, event)

    def _snapshot(self, state: JobState, *, events: list[dict[str, Any]]) -> dict[str, object]:
        progress = None
        if state.progress_done is not None:
            progress = {"done": state.progress_done, "total": state.progress_total}
        return {
            "job_id": state.job_id,
            "status": state.status,
            "stage": state.stage,
            "progress": progress,
            "next_cursor": state.cursor,
            "events": events,
            "result": state.result,
            "error": state.error,
        }

    def _write_state(self, state: JobState) -> None:
        path = self._job_path(state.job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(state.model_dump_json(indent=2).encode())
        temporary.replace(path)

    def _job_path(self, job_id: str) -> Path:
        return self.jobs_dir / job_id / "job.json"

    def _events_path(self, job_id: str) -> Path:
        return self.jobs_dir / job_id / "events.jsonl"


def serialize_process_result(result: ProcessResult) -> dict[str, Any]:
    total = result.report.total
    outputs = [
        {
            "label": label,
            "path": str(path.resolve()),
            "mime_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            "size": path.stat().st_size,
        }
        for label, path in result.outputs
    ]
    return {
        "status": "completed",
        "outputs": outputs,
        "usage": {
            "elapsed_seconds": total.elapsed_seconds,
            "audio_seconds": total.audio_seconds,
            "prompt_tokens": total.prompt_tokens,
            "completion_tokens": total.completion_tokens,
        },
    }


def _default_state_dir() -> Path:
    values: dict[str, str | None] = {}
    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        values.update(dotenv_values(dotenv_path))
    values.update(os.environ)
    configured = values.get("DEHYDRATER_MCP_STATE_DIR")
    if configured:
        return Path(configured).expanduser()
    return user_data_path("dehydrater") / "mcp"
