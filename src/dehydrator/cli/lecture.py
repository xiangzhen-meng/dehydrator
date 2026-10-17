"""非交互式处理命令的展示逻辑。"""

import asyncio
import logging
import time
from pathlib import Path

import typer
from rich.table import Table

from dehydrator.bootstrap import load_settings
from dehydrator.cli.console import console, fail
from dehydrator.cli.display import ProgressDisplay
from dehydrator.cli.logs import log_settings, workspace_log
from dehydrator.cli.report import report_table
from dehydrator.config import Settings
from dehydrator.pipeline.workspace import Workspace, WorkspaceError
from dehydrator.service import LectureReport, PlanError, lecture_report, run_process

logger = logging.getLogger(__name__)


def process(input_path: Path, output: Path) -> None:
    settings = load_settings()
    if missing := settings.missing():
        fail("缺少配置：\n  " + "\n  ".join(missing))
    try:
        run(input_path, output, settings)
    except PlanError as error:
        fail(str(error))


def run(input_path: Path, output: Path, settings: Settings) -> None:
    log_path = Workspace(output).log_path
    with workspace_log(log_path):
        logger.info("===== 开始处理：%s → %s =====", input_path, output)
        log_settings(settings)
        outputs = _run_with_progress(input_path, output, settings, log_path)
        report = lecture_report(output, settings)
        logger.info("===== 处理完成：%s =====", report.total)
    _show_outputs(outputs, report)


def _run_with_progress(
    input_path: Path, output: Path, settings: Settings, log_path: Path
) -> list[tuple[str, Path]]:
    started = time.monotonic()
    try:
        with ProgressDisplay(console) as display:
            outputs = asyncio.run(run_process(input_path, output, settings, display.handle))
    except KeyboardInterrupt:
        logger.warning("用户中断")
        raise typer.Exit(130) from None
    except WorkspaceError as error:
        logger.exception("工作区错误")
        fail(str(error))
    except Exception:
        logger.exception("处理失败")
        fail(f"处理未完成，详细日志：{log_path}")
    logger.info("总耗时 %.0f 秒", time.monotonic() - started)
    return outputs


def _show_outputs(outputs: list[tuple[str, Path]], report: LectureReport) -> None:
    console.print("\n[green]✓ 完成[/green]\n")
    console.print(report_table(report, show_state=False))
    console.print()
    files = Table.grid(padding=(0, 4))
    files.add_column()
    files.add_column(overflow="fold")
    for label, path in outputs:
        files.add_row(f"  {label}", str(path))
    console.print(files)
