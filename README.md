# dehydrator

把一个音频或视频文件提取为音频，转成带时间戳的逐字稿，再改写成简洁的脱水稿。

## 使用

```bash
dehydrator -i lecture.mp4 -o ./lecture-output
```

正常处理只接受两个参数：

- `-i, --input`：一个音频或视频文件
- `-o, --output`：输出目录

命令完全非交互，不读取 stdin。输入文件名不参与内容生成；程序只处理文件内容。

保留两个辅助命令：

```bash
dehydrator check
dehydrator status ./lecture-output
```

`check` 检查转写服务和脱水模型的配置与连通性。`status` 显示指定输出目录中三个阶段的完成状态、耗时和 token 用量。

## 配置

配置来自当前目录或父目录中的第一个 `.env` 文件，以及环境变量；环境变量优先。没有配置文件写入命令。

```env
DEHYDRATOR_TRANSCRIBE_URL=https://openspeech.bytedance.com/api/v3/auc/bigmodel
DEHYDRATOR_TRANSCRIBE_MODEL=volc.seedasr.auc
DEHYDRATOR_TRANSCRIBE_KEY=...

DEHYDRATOR_DEHYDRATE_URL=https://ark.cn-beijing.volces.com/api/v3
DEHYDRATOR_DEHYDRATE_MODEL=doubao-seed-2-1-lite-260915
DEHYDRATOR_DEHYDRATE_KEY=...
```

地址和模型有默认值，两个 API Key 必须配置。

## 流程和输出

```text
输入音频/视频
  → 提取音频
  → 语音转写
  → 脱水改写
  → dehydrated.md
```

输出目录结构：

```text
lecture-output/
├── dehydrated.md
├── lecture.toml
└── cache/
    ├── audio.mp3
    ├── dehydrator.log
    ├── artifacts/
    ├── stages/
    └── dehydrate/
```

原始逐字稿保存在 `cache/artifacts/raw_transcript.json`，只作为脱水阶段的中间产物，不生成 `raw.md`。

同一输出目录再次运行同一输入时会复用缓存；中断后重新运行同一命令即可继续。输出目录已经对应其他输入文件时会报错。

## 开发

```bash
uv sync
uv run dehydrator --help
uv run ruff format
uv run ruff check
uv run basedpyright
uv run lint-imports
uv run pytest
```

## MCP

项目同时提供本地 stdio MCP server，CLI 仍然可用：

```bash
uv run dehydrator-mcp
```

MCP 暴露五个工具：

- `process_media`：提交一个音频或视频处理任务，立即返回 `job_id`。
- `watch_process`：按 `after_cursor` 长轮询任务事件，单次最多等待 20 秒；客户端可以重复调用以接收进度、阶段和最终结果。
- `get_process_status`：立即查询任务当前状态。
- `cancel_process`：取消正在执行的任务，并保留已经生成的缓存。
- `check_services`：检查语音转写和脱水模型服务。

MCP server 使用输出目录中的 `.dehydrator-mcp` 目录保护同一工作区，避免两个调用同时写入；中断后再次调用会继续利用已有阶段缓存。

长任务通过任务接口运行，不受单次 MCP 调用的 300 秒限制：

- `process_media`：提交任务并立即返回 `job_id`
- `watch_process`：按 `after_cursor` 长轮询事件，单次最多等待 20 秒
- `get_process_status`：立即查询状态
- `cancel_process`：取消后台任务

任务记录默认保存在系统应用数据目录，也可以配置：

```env
DEHYDRATOR_MCP_STATE_DIR=/Users/me/Developer/dehydrator/.mcp-state
```

可选的路径白名单配置：

```env
DEHYDRATOR_MCP_INPUT_ROOTS=/Users/me/media
DEHYDRATOR_MCP_OUTPUT_ROOTS=/Users/me/outputs
```

未配置时，输入和输出路径必须位于 MCP 进程的当前工作目录内。输出结果返回绝对路径、MIME 类型和文件大小。

许可证：AGPL-3.0-or-later。
