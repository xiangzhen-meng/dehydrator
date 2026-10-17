import asyncio

from dehydrator.domain.lecture import AudioFile
from dehydrator.pipeline.artifacts import AUDIO, LECTURE
from dehydrator.pipeline.stage import Stage, StageContext
from dehydrator.pipeline.workspace import sha256_of
from dehydrator.ports import AudioExtractor, Fingerprint


class ExtractAudioStage(Stage):
    name = "extract_audio"
    inputs = (LECTURE,)
    outputs = (AUDIO,)

    def __init__(self, extractor: AudioExtractor) -> None:
        self._extractor = extractor

    def fingerprint(self) -> Fingerprint:
        return self._extractor.fingerprint()

    async def run(self, ctx: StageContext) -> None:
        lecture = ctx.read(LECTURE)
        dest = ctx.workspace.audio_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        recording = ctx.workspace.resolve(lecture.recording.path)
        extracted = await asyncio.to_thread(self._extractor.extract, recording, dest)
        ctx.write(
            AUDIO,
            AudioFile(
                path=ctx.workspace.portable_path(dest),
                sha256=sha256_of(dest),
                duration=extracted.duration,
            ),
        )
