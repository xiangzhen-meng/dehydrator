"""脱水阶段测试。"""

import json
from pathlib import Path

import pytest

from dehydrater.domain.lecture import Lecture, SourceFile
from dehydrater.domain.transcript import Transcript, TranscriptSegment
from dehydrater.pipeline.artifacts import DEHYDRATED_TRANSCRIPT, LECTURE, RAW_TRANSCRIPT
from dehydrater.pipeline.cache import load_meta
from dehydrater.pipeline.runner import Runner
from dehydrater.pipeline.stages.dehydrate import DehydrateStage
from dehydrater.pipeline.templating import TemplateSet
from dehydrater.pipeline.workspace import ArtifactStore, Workspace

from ..fakes import ScriptedChat

_RAW = Transcript(
    segments=[
        TranscriptSegment(start=0.0, end=2.0, text="嗯，大家好。"),
        TranscriptSegment(start=2.0, end=5.0, text="今天讲进程调度。"),
        TranscriptSegment(start=5.0, end=9.0, text="那个，先讲 FCFS。"),
    ]
)
_REPLY = json.dumps(
    {"paragraphs": [{"first": 1, "last": 2, "text": "今天讲进程调度，先讲 FCFS。"}]},
    ensure_ascii=False,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    workspace = Workspace(tmp_path)
    store = ArtifactStore(workspace)
    recording = SourceFile(path=Path("r.mp3"), size=1, mtime_ns=1)
    store.write(LECTURE, Lecture(recording=recording))
    store.write(RAW_TRANSCRIPT, _RAW)
    return workspace


async def test_dehydrate_takes_timestamps_from_source_segments(workspace: Workspace) -> None:
    chat = ScriptedChat(_REPLY)

    await Runner(
        [DehydrateStage(chat, TemplateSet("prompts"))],
        workspace,
        sources=[LECTURE, RAW_TRANSCRIPT],
    ).run()

    result = ArtifactStore(workspace).read(DEHYDRATED_TRANSCRIPT)
    assert result.segments == [
        TranscriptSegment(start=2.0, end=9.0, text="今天讲进程调度，先讲 FCFS。")
    ]
    assert "[2] 那个，先讲 FCFS。" in chat.calls[0][1].content


async def test_dehydrate_reuses_chunk_results_when_forced(workspace: Workspace) -> None:
    chat = ScriptedChat(_REPLY)
    runner = Runner(
        [DehydrateStage(chat, TemplateSet("prompts"))],
        workspace,
        sources=[LECTURE, RAW_TRANSCRIPT],
    )
    await runner.run()
    await runner.run(force_from="dehydrate")

    assert len(chat.calls) == 1
    meta = load_meta(workspace.stage_meta_path("dehydrate"))
    assert meta is not None
    assert (meta.prompt_tokens, meta.completion_tokens) == (10, 5)
