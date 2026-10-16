from pathlib import Path

from dehydrater.domain.lecture import Lecture, SourceFile
from dehydrater.domain.transcript import Transcript, TranscriptSegment
from dehydrater.pipeline.templating import TemplateSet


def test_dehydrated_template_renders_timecodes() -> None:
    lecture = Lecture(recording=SourceFile(path=Path("r.mp3"), size=1, mtime_ns=1))
    transcript = Transcript(segments=[TranscriptSegment(start=754, end=760, text="讲 TLB。")])

    text = TemplateSet("templates").render(
        "dehydrated.md.j2", lecture=lecture, transcript=transcript
    )

    assert text.startswith("# 脱水稿")
    assert "`12:34` 讲 TLB。" in text


def test_prompt_digest_is_stable() -> None:
    prompts = TemplateSet("prompts")
    assert prompts.digest("dehydrate.system.j2")
