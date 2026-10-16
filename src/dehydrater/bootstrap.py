"""组合根：根据用户配置构造 adapters，注入到各阶段，组装成流水线。

这是唯一同时认识 pipeline 和 adapters 的模块。
"""

import os
from collections.abc import Callable
from pathlib import Path

from dotenv import find_dotenv

from dehydrater.adapters.asr_volcengine import VolcengineTranscriber
from dehydrater.adapters.audio_pyav import PyAVAudioExtractor
from dehydrater.adapters.llm_openai_compat import OpenAICompatibleChatModel
from dehydrater.config import Settings, Task
from dehydrater.pipeline.events import PipelineEvent
from dehydrater.pipeline.lecture import LecturePipeline
from dehydrater.pipeline.stage import Stage
from dehydrater.pipeline.stages.dehydrate import DehydrateStage
from dehydrater.pipeline.stages.extract_audio import ExtractAudioStage
from dehydrater.pipeline.stages.render import RenderDehydratedStage
from dehydrater.pipeline.stages.transcribe import TranscribeStage
from dehydrater.pipeline.templating import TemplateSet
from dehydrater.pipeline.workspace import Workspace
from dehydrater.ports import AudioExtractor, ChatModel, Transcriber

# Qwen 的思考模式会增加不必要的延迟和 token 消耗；脱水只需要直接返回 JSON。
_DEHYDRATE_EXTRA_BODY = {"enable_thinking": False}
_LLM_CONCURRENCY = 4


def load_settings() -> Settings:
    """环境变量 → 当前目录向上找到的 .env 文件。"""
    env_files = [Path(found)] if (found := find_dotenv(usecwd=True)) else []
    return Settings(os.environ, env_files)


def build_transcriber(settings: Settings) -> VolcengineTranscriber:
    task = settings.task(Task.TRANSCRIBE)
    return VolcengineTranscriber(base_url=task.url, api_key=task.key, resource_id=task.model)


def build_chat_model(settings: Settings, task_name: Task) -> OpenAICompatibleChatModel:
    task = settings.task(task_name)
    return OpenAICompatibleChatModel(
        base_url=task.url,
        api_key=task.key,
        model=task.model,
        temperature=None,
        max_tokens=None,
        extra_body=_DEHYDRATE_EXTRA_BODY if task_name == Task.DEHYDRATE else {},
        max_concurrency=_LLM_CONCURRENCY,
    )


def build_media_probe() -> AudioExtractor:
    return PyAVAudioExtractor()


def build_verifier(settings: Settings, task: Task) -> Transcriber | ChatModel:
    if task == Task.TRANSCRIBE:
        return build_transcriber(settings)
    return build_chat_model(settings, task)


def build_stages(settings: Settings) -> list[Stage]:
    """按依赖顺序排列的全部阶段。"""
    prompts = TemplateSet("prompts")
    templates = TemplateSet("templates")
    return [
        ExtractAudioStage(PyAVAudioExtractor()),
        TranscribeStage(build_transcriber(settings)),
        DehydrateStage(build_chat_model(settings, Task.DEHYDRATE), prompts),
        RenderDehydratedStage(templates),
    ]


def build_pipeline(
    workspace: Workspace,
    settings: Settings,
    on_event: Callable[[PipelineEvent], None] = lambda _: None,
) -> LecturePipeline:
    return LecturePipeline(workspace, build_stages(settings), on_event)
