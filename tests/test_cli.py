"""命令行参数测试。"""

from pathlib import Path

from typer.testing import CliRunner

from dehydrater.cli.app import app

runner = CliRunner()


def test_root_requires_input_and_output() -> None:
    result = runner.invoke(app, [])

    assert result.exit_code == 1
    assert "-i/--input" in result.output


def test_help_is_non_interactive() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "dehydrater -i INPUT -o OUTPUT" in result.output
    assert "setup" not in result.output
    assert "process" not in result.output


def test_status_is_a_subcommand() -> None:
    result = runner.invoke(app, ["status", str(Path("missing"))])

    assert result.exit_code == 1
    assert "没有整理记录" in result.output
