# dehydrater 设计

## 定位

dehydrater 是一个非交互式单功能命令：把一个音频或视频文件转换为带时间戳的脱水稿。

```text
输入文件 → 提取音频 → 语音转写 → 脱水改写 → dehydrated.md
```

项目不读取 PDF，不生成课堂笔记，不包含交互式设置流程。

## 命令

```bash
dehydrater -i INPUT -o OUTPUT
dehydrater check
dehydrater status OUTPUT
```

根命令不带 `-i` 和 `-o` 时直接失败，不进入交互流程。

配置只从环境变量和 `.env` 文件读取，处理流程只需要 `TRANSCRIBE` 和 `DEHYDRATE` 两组配置。

## 分层

```text
cli → service → bootstrap → config → pipeline | adapters → ports → domain
```

- `cli/`：参数解析、非交互式输出、日志和状态展示
- `service.py`：输入检查、运行流水线、状态汇总
- `bootstrap.py`：构造 adapters 并组装流水线
- `config.py`：读取两项服务配置
- `pipeline/`：阶段、缓存、产物和调度
- `adapters/`：PyAV、语音识别服务和 OpenAI 兼容模型
- `domain/`：音频、逐字稿等纯数据模型

## 阶段

```text
extract_audio → transcribe → dehydrate → render_dehydrated
```

原始逐字稿和脱水逐字稿是缓存中的结构化产物；最终只渲染 `dehydrated.md`。

时间戳始终由原始转写分句推导，模型只返回原始分句编号和改写文本。

## 工作区

```text
OUTPUT/
├── dehydrated.md
├── lecture.toml
└── cache/
    ├── audio.mp3
    ├── dehydrater.log
    ├── artifacts/
    ├── stages/
    └── dehydrate/
```

`lecture.toml` 只保存输入文件路径。输入文件大小和修改时间参与产物缓存键；同一输出目录不能切换到另一个输入文件。

## 运行原则

- 重新运行自动复用有效缓存。
- 中断后重新运行同一命令即可继续。
- 不提供强制重跑参数；需要完全重做时删除输出目录的 `cache/`。
- 处理错误直接通过非零退出码返回，详细堆栈写入工作区日志。
