"""命令行入口。"""

import asyncio
import logging
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer

from dehydrator.bootstrap import load_settings
from dehydrator.cli import lecture
from dehydrator.cli.console import console, fail
from dehydrator.cli.display import describe
from dehydrator.cli.logs import configure_logging, global_log_path, log_settings
from dehydrator.cli.report import report_table
from dehydrator.config import Field, Task, env_name
from dehydrator.service import lecture_report, verify_task

USAGE = """\
[bold]dehydrator[/bold] —— 把音频或视频转成脱水稿

  dehydrator -i INPUT -o OUTPUT   处理输入文件
  dehydrator check                检查配置和服务连通性
  dehydrator status OUTPUT        查看处理状态
"""

_SUBCOMMAND = {"help_option_names": ["--help", "-h"]}
logger = logging.getLogger(__name__)

app = typer.Typer(
    add_completion=False,
    rich_markup_mode="rich",
    context_settings={"help_option_names": []},
)


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    input_path: Annotated[Path | None, typer.Option("--input", "-i")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    show_help: Annotated[bool, typer.Option("--help", "-h", is_eager=True)] = False,
    show_version: Annotated[bool, typer.Option("--version", "-V", is_eager=True)] = False,
) -> None:
    if show_help:
        console.print(USAGE)
        raise typer.Exit()
    if show_version:
        console.print(f"dehydrator {version('dehydrator')}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        if input_path is None or output is None:
            fail("处理文件需要同时提供 -i/--input 和 -o/--output")
        lecture.process(input_path, output)
    elif input_path is not None or output is not None:
        fail("-i/--input 和 -o/--output 只能用于直接处理文件")


@app.command(context_settings=_SUBCOMMAND)
def status(output: Annotated[Path, typer.Argument(help="输出目录。")]) -> None:
    """查看处理状态、耗时和 token 用量。"""
    if not (output / "lecture.toml").exists():
        fail(f"{output} 中没有整理记录")
    console.print(report_table(lecture_report(output, load_settings()), show_state=True))


@app.command(context_settings=_SUBCOMMAND)
def check() -> None:
    """检查配置是否完整，并测试服务连通性。"""
    settings = load_settings()
    log_settings(settings)
    if missing := settings.missing():
        fail("以下设置缺失：\n  " + "\n  ".join(missing))
    healthy = True
    for task in Task:
        try:
            asyncio.run(verify_task(settings, task))
            console.print(f"  [green]✓[/green] {task.label}")
        except Exception as error:
            healthy = False
            logger.exception("检查 %s 失败", task)
            console.print(f"  [red]✗[/red] {task.label}：{describe(error)}")
            names = "、".join(
                env_name(task, field) for field in (Field.URL, Field.MODEL, Field.KEY)
            )
            console.print(f"    [dim]相关设置：{names}[/dim]")
    if not healthy:
        console.print(f"\n详细日志：{global_log_path()}")
        raise typer.Exit(1)


def main() -> None:
    configure_logging()
    app()
