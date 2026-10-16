"""面向用户的"步骤"：一个步骤由若干内部阶段组成。进度显示和 --redo 都以步骤为单位。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    name: str
    label: str
    stages: tuple[str, ...]


STEPS = (
    Step("audio", "提取音频", ("extract_audio",)),
    Step("transcribe", "语音转写", ("transcribe",)),
    Step("dehydrate", "逐字稿脱水", ("dehydrate", "render_dehydrated")),
)


def step_of(stage: str) -> Step:
    return next(step for step in STEPS if stage in step.stages)
