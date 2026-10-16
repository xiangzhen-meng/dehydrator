# dehydrater

把一个音频或视频文件提取为音频，转成带时间戳的逐字稿，再改写成简洁的脱水稿。

## 使用

```bash
dehydrater -i lecture.mp4 -o ./lecture-output
```

正常处理只接受两个参数：

- `-i, --input`：一个音频或视频文件
- `-o, --output`：输出目录

命令完全非交互，不读取 stdin。输入文件名不参与内容生成；程序只处理文件内容。

保留两个辅助命令：

```bash
dehydrater check
dehydrater status ./lecture-output
```

`check` 检查转写服务和脱水模型的配置与连通性。`status` 显示指定输出目录中三个阶段的完成状态、耗时和 token 用量。

## 配置

配置来自当前目录或父目录中的第一个 `.env` 文件，以及环境变量；环境变量优先。没有配置文件写入命令。

```env
DEHYDRATER_TRANSCRIBE_URL=https://openspeech.bytedance.com/api/v3/auc/bigmodel
DEHYDRATER_TRANSCRIBE_MODEL=volc.seedasr.auc
DEHYDRATER_TRANSCRIBE_KEY=...

DEHYDRATER_DEHYDRATE_URL=https://ark.cn-beijing.volces.com/api/v3
DEHYDRATER_DEHYDRATE_MODEL=doubao-seed-2-1-lite-260915
DEHYDRATER_DEHYDRATE_KEY=...
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
    ├── dehydrater.log
    ├── artifacts/
    ├── stages/
    └── dehydrate/
```

原始逐字稿保存在 `cache/artifacts/raw_transcript.json`，只作为脱水阶段的中间产物，不生成 `raw.md`。

同一输出目录再次运行同一输入时会复用缓存；中断后重新运行同一命令即可继续。输出目录已经对应其他输入文件时会报错。

## 开发

```bash
uv sync
uv run dehydrater --help
uv run ruff format
uv run ruff check
uv run basedpyright
uv run lint-imports
uv run pytest
```

许可证：AGPL-3.0-or-later。
