"""MCP 请求使用的工作区锁和运行状态。"""

import asyncio
import json
import os
import socket
import time
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from types import TracebackType
from typing import Self


class WorkspaceBusyError(RuntimeError):
    """同一个输出工作区已有另一个处理请求。"""


class WorkspaceRun(AbstractAsyncContextManager["WorkspaceRun"]):
    """用原子锁保护一个输出工作区，并持久化最近一次运行状态。"""

    def __init__(self, output: Path, input_path: Path) -> None:
        self.output = output
        self.input_path = input_path
        self.control_dir = output / ".dehydrater-mcp"
        self.lock_path = self.control_dir / "run.lock"
        self.state_path = self.control_dir / "run.json"
        self._owned = False

    async def __aenter__(self) -> Self:
        self.control_dir.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if _stale_lock(self.lock_path):
                mark_interrupted(self.output)
                self.lock_path.unlink(missing_ok=True)
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            else:
                raise WorkspaceBusyError(
                    f"输出目录正在被另一个处理请求使用：{self.output}"
                ) from None
        with os.fdopen(fd, "w", encoding="utf-8") as lock:
            json.dump(
                {
                    "pid": os.getpid(),
                    "host": socket.gethostname(),
                    "input_path": str(self.input_path),
                    "started_at": time.time(),
                },
                lock,
            )
        self._owned = True
        self._write_state("running")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if not self._owned:
            return
        status = (
            "cancelled"
            if isinstance(exc_value, BaseException) and _is_cancelled(exc_value)
            else ("failed" if exc_value is not None else "completed")
        )
        self._write_state(status)
        self.lock_path.unlink(missing_ok=True)
        self._owned = False

    def _write_state(self, status: str) -> None:
        self.state_path.write_text(
            json.dumps(
                {
                    "status": status,
                    "input_path": str(self.input_path),
                    "updated_at": time.time(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def mark_interrupted(output: Path) -> None:
    """把遗留的 running 状态标记为 interrupted。"""
    state_path = output / ".dehydrater-mcp" / "run.json"
    if not state_path.exists():
        return
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if data.get("status") == "running":
        data["status"] = "interrupted"
        data["updated_at"] = time.time()
        state_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _stale_lock(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        pid = int(data["pid"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return True
    if pid == os.getpid():
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def _is_cancelled(error: BaseException) -> bool:
    return isinstance(error, asyncio.CancelledError)
