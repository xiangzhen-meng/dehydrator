"""dehydrator 的本地 stdio MCP 入口。"""

import logging

from mcp.server.fastmcp import FastMCP

from dehydrator.bootstrap import load_settings
from dehydrator.config import Task
from dehydrator.mcp_jobs import JobManager, JobNotFoundError
from dehydrator.mcp_security import validate_input_path, validate_output_path
from dehydrator.service import verify_task

logger = logging.getLogger(__name__)
mcp = FastMCP("dehydrator")
jobs = JobManager()


@mcp.tool()
async def process_media(input_path: str, output_dir: str) -> dict[str, object]:
    """提交音频或视频处理任务，立即返回任务标识。"""
    input_file = validate_input_path(input_path)
    output = validate_output_path(output_dir)
    settings = load_settings()
    if missing := settings.missing():
        raise ValueError("缺少配置：" + ", ".join(missing))
    state = await jobs.submit(input_file, output)
    return {"job_id": state.job_id, "status": state.status, "cursor": state.cursor}


@mcp.tool()
async def watch_process(
    job_id: str,
    after_cursor: int = 0,
    wait_seconds: float = 20,
) -> dict[str, object]:
    """长轮询任务事件；最多等待 20 秒，支持用 cursor 断线续读。"""
    try:
        return await jobs.watch(job_id, after_cursor=after_cursor, wait_seconds=wait_seconds)
    except JobNotFoundError as error:
        raise ValueError(f"找不到任务：{job_id}") from error


@mcp.tool()
async def get_process_status(job_id: str) -> dict[str, object]:
    """立即返回任务当前状态，不等待新事件。"""
    try:
        return await jobs.get_status(job_id)
    except JobNotFoundError as error:
        raise ValueError(f"找不到任务：{job_id}") from error


@mcp.tool()
async def cancel_process(job_id: str) -> dict[str, object]:
    """取消正在运行的任务，并保留已经生成的缓存。"""
    try:
        return await jobs.cancel(job_id)
    except JobNotFoundError as error:
        raise ValueError(f"找不到任务：{job_id}") from error


@mcp.tool()
async def check_services() -> dict[str, object]:
    """检查语音转写和脱水模型服务是否可用。"""
    settings = load_settings()
    if missing := settings.missing():
        return {"status": "invalid_config", "missing": missing}

    results: dict[str, object] = {}
    healthy = True
    for task in Task:
        try:
            await verify_task(settings, task)
        except Exception as error:  # 服务检查需要把单项失败作为数据返回
            healthy = False
            logger.exception("MCP 服务检查失败：%s", task.value)
            results[task.value] = {"healthy": False, "message": str(error)}
        else:
            results[task.value] = {"healthy": True}
    return {"status": "healthy" if healthy else "unhealthy", "tasks": results}


def main() -> None:
    """启动 stdio MCP server。"""
    logging.basicConfig(level=logging.INFO)
    mcp.run(transport="stdio")
