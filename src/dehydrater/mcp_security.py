"""MCP 入口的本地文件系统访问限制。"""

import os
from collections.abc import Mapping
from pathlib import Path

from dotenv import dotenv_values, find_dotenv


class MCPPathError(ValueError):
    """MCP 请求访问了不允许的路径。"""


def validate_input_path(path: str | Path, *, env: Mapping[str, str] | None = None) -> Path:
    """返回规范化的输入文件路径，并确保它在允许的输入根目录中。"""
    resolved = _resolve_path(path)
    if not resolved.is_file():
        raise MCPPathError(f"输入文件不存在或不是普通文件：{resolved}")
    _ensure_allowed(resolved, _roots("DEHYDRATER_MCP_INPUT_ROOTS", env), "输入")
    return resolved


def validate_output_path(path: str | Path, *, env: Mapping[str, str] | None = None) -> Path:
    """返回规范化的输出目录路径，并确保它在允许的输出根目录中。"""
    resolved = _resolve_path(path)
    if resolved.exists() and not resolved.is_dir():
        raise MCPPathError(f"输出路径不是目录：{resolved}")
    _ensure_allowed(resolved, _roots("DEHYDRATER_MCP_OUTPUT_ROOTS", env), "输出")
    return resolved


def _roots(name: str, env: Mapping[str, str] | None) -> tuple[Path, ...]:
    values = _settings(env)
    configured = values.get(name, "")
    if configured:
        roots = tuple(_resolve_path(item) for item in configured.split(os.pathsep) if item)
    else:
        roots = (Path.cwd().resolve(),)
    if not roots:
        raise MCPPathError(f"{name} 没有配置有效目录")
    for root in roots:
        if not root.is_dir():
            raise MCPPathError(f"{name} 中的目录不存在：{root}")
    return roots


def _settings(env: Mapping[str, str] | None) -> dict[str, str]:
    values = dict(dotenv_values(find_dotenv(usecwd=True))) if find_dotenv(usecwd=True) else {}
    values.update(env or os.environ)
    return {key: value for key, value in values.items() if isinstance(value, str)}


def _resolve_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate.resolve()


def _ensure_allowed(path: Path, roots: tuple[Path, ...], label: str) -> None:
    if not any(path.is_relative_to(root) for root in roots):
        allowed = ", ".join(str(root) for root in roots)
        raise MCPPathError(f"{label}路径不在允许目录内：{path}（允许：{allowed}）")
