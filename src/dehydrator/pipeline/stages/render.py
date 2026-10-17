"""把结构化产物渲染成用户可见的 Markdown，每份输出一个阶段，产出后立即可读。"""

from dehydrator.pipeline.artifacts import DEHYDRATED_TRANSCRIPT, LECTURE
from dehydrator.pipeline.stage import Stage, StageContext
from dehydrator.pipeline.templating import TemplateSet


class _RenderStage(Stage):
    always_run = True
    outputs = ()

    def __init__(self, templates: TemplateSet) -> None:
        self._templates = templates

    def _write(self, ctx: StageContext, template: str, output: str, **variables: object) -> None:
        text = self._templates.render(template, lecture=ctx.read(LECTURE), **variables)
        (ctx.workspace.root / output).write_text(text, encoding="utf-8")


class RenderDehydratedStage(_RenderStage):
    name = "render_dehydrated"
    inputs = (LECTURE, DEHYDRATED_TRANSCRIPT)

    async def run(self, ctx: StageContext) -> None:
        transcript = ctx.read(DEHYDRATED_TRANSCRIPT)
        self._write(ctx, "dehydrated.md.j2", "dehydrated.md", transcript=transcript)
