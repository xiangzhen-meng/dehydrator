"""处理一个音频或视频文件。"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from dehydrater.bootstrap import build_media_probe, build_pipeline, build_verifier
from dehydrater.config import Settings, Task
from dehydrater.domain.base import Seconds
from dehydrater.pipeline.cache import StageMeta
from dehydrater.pipeline.events import PipelineEvent
from dehydrater.pipeline.runner import StageState
from dehydrater.pipeline.steps import STEPS, Step
from dehydrater.pipeline.workspace import Workspace
from dehydrater.ports import NotAMediaFileError

OUTPUT_FILES = (("脱水稿", "dehydrated.md"),)


class PlanError(ValueError):
    """输入参数有误。"""


def inspect_input(path: Path) -> Seconds:
    probe = build_media_probe()
    if not path.is_file():
        raise PlanError(f"找不到输入文件：{path}")
    try:
        return probe.probe(path).duration
    except NotAMediaFileError as error:
        raise PlanError(f"{error}。输入必须是音频或视频文件") from error


def check_output(output: Path) -> None:
    if output.exists() and not output.is_dir():
        raise PlanError(f"输出路径 {output} 是一个文件，请提供目录")


async def run_process(
    input_path: Path,
    output: Path,
    settings: Settings,
    on_event: Callable[[PipelineEvent], None] = lambda _: None,
) -> list[tuple[str, Path]]:
    inspect_input(input_path)
    check_output(output)
    workspace = Workspace.prepare(output, recording=input_path.resolve())
    pipeline = build_pipeline(workspace, settings, on_event)
    await pipeline.run()
    return [(label, workspace.root / name) for label, name in OUTPUT_FILES]


@dataclass(frozen=True)
class Usage:
    elapsed_seconds: float = 0.0
    audio_seconds: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            elapsed_seconds=self.elapsed_seconds + other.elapsed_seconds,
            audio_seconds=self.audio_seconds + other.audio_seconds,
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
        )


@dataclass(frozen=True)
class StepReport:
    step: Step
    done: bool
    usage: Usage


@dataclass(frozen=True)
class LectureReport:
    steps: list[StepReport]

    @property
    def total(self) -> Usage:
        return sum((report.usage for report in self.steps), Usage())


def lecture_report(output: Path, settings: Settings) -> LectureReport:
    statuses = {s.stage: s for s in build_pipeline(Workspace(output), settings).status()}
    return LectureReport(
        steps=[
            StepReport(
                step=step,
                done=all(statuses[stage].state == StageState.FRESH for stage in step.stages),
                usage=sum(
                    (_stage_usage(statuses[stage].meta) for stage in step.stages if statuses[stage].meta),
                    Usage(),
                ),
            )
            for step in STEPS
        ]
    )


def _stage_usage(meta: StageMeta) -> Usage:
    return Usage(
        elapsed_seconds=meta.elapsed_seconds,
        audio_seconds=meta.audio_seconds,
        prompt_tokens=meta.prompt_tokens,
        completion_tokens=meta.completion_tokens,
    )


async def verify_task(settings: Settings, task: Task) -> None:
    await build_verifier(settings, task).verify()
