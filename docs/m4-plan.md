# M4：第一个可下载版本

M4 的目标不是一次做出“生产级下载器”，而是首次打通一条容易阅读和调试的完整路径：

```text
download 命令
  → 获取 DASH 轨道
  → 选择视频和音频
  → 顺序下载到临时目录
  → FFmpeg 无重编码混流
  → 移动到最终文件
```

## 用户行为

沿用当前命令：

```text
velafetch download SOURCE [-o DIR] [--quality best|HEIGHTp]
                          [--codec auto|avc|hevc]
                          [--video-only|--audio-only|--no-mux]
                          [--overwrite]
```

- 输入范围与 `info/formats` 相同：BV、av、标准 Bilibili 单 P 视频 URL。
- 默认选择一条视频和一条 AAC 音频，输出 `<title>.mp4`。
- `video-only` 输出 `<title>.video.<container>`。
- `audio-only` 输出 `<title>.audio.<container>`。
- `no-mux` 同时输出独立视频和音频文件。
- 三种模式选项互斥；画质和编码继续使用已有选轨代码。
- 目标已存在且没有 `--overwrite` 时跳过整个任务并返回成功。
- `--overwrite` 仍先生成完整临时结果，再用 `os.replace` 替换目标。

## 实现顺序

### 1. 下载服务

- 新增一个小型 `DownloadService`，先放在 `application/download.py`。
- CLI 只负责参数和输出；服务负责提取、选轨、临时文件、FFmpeg 和最终路径。
- 文件接近 200 行且出现第二个独立职责时再拆分，不预先建立 planner、publisher 或 engine
  层。

### 2. 输出名称和临时目录

- 输出目录不存在时创建。
- 标题中的控制字符以及 `< > : " / \\ | ? *` 替换为 `_`，去掉首尾空白和结尾点；
  清理后为空则使用 BV 号。
- 使用 `tempfile.TemporaryDirectory(prefix=".velafetch-", dir=output_dir)`，保证临时文件和
  最终文件在同一文件系统。
- 下载或混流失败时由临时目录自动清理；不实现 task ID、状态 JSON 或跨运行续传。

### 3. 顺序传输

- 复用同一个 `httpx.AsyncClient` 完成提取和媒体下载。
- 使用 `client.stream("GET", primary_url, headers=required_headers)`，每次读取 256 KiB
  并写入临时文件。
- 检查 HTTP 成功状态；`Content-Length` 只用于显示进度，不建立完整性状态机。
- M4 只请求每条轨道的第一个 URL。备用 URL、重试、Range 和 `.part` 续传留到 M5，在
  实际失败后实现。
- 媒体 URL 和请求头不得进入进度、错误或测试快照。

### 4. 进度

- 下载视频和音频时向 stderr 显示轨道类型、已下载字节、可用总大小和平均速度。
- 使用简单的 Rich 进度展示；不建立可注入事件总线或日志框架。
- stdout 只在成功或跳过后打印最终路径。

### 5. FFmpeg

- 只有默认混流模式需要 FFmpeg；其他模式直接发布下载完成的轨道。
- 优先使用根选项 `--ffmpeg`，否则通过 `shutil.which("ffmpeg")` 查找。
- 使用 `asyncio.create_subprocess_exec`，固定参数包含 `-nostdin`、显式视频/音频映射、
  `-c copy` 和临时输出路径；绝不使用 shell 或用户提供的附加参数。
- 非零退出返回普通 CLI 错误。取消时 terminate 并等待进程退出，避免留下后台 FFmpeg。

### 6. 发布和清理

- 所需临时结果全部完成后才写最终路径。
- 无 `--overwrite` 时在下载前检查所有目标；任意目标存在则整任务跳过。
- 有 `--overwrite` 时使用 `os.replace`。M4 不实现多文件回滚框架，实际遇到 no-mux
  第二个文件发布失败后再为该问题设计修复。
- 成功后打印绝对输出路径；临时目录离开作用域后删除。

## 测试

- 选轨和四种输出模式生成正确的所需轨道与文件名。
- `httpx.MockTransport` 提供假媒体字节，验证顺序流式写入。
- HTTP 错误不会产生最终文件，临时目录被清理。
- 已有文件默认跳过，`--overwrite` 只替换完整结果。
- monkeypatch `asyncio.create_subprocess_exec` 验证 FFmpeg 参数数组、非零退出和取消。
- 增加一条离线集成测试：假 API → 选轨 → 假 CDN → 假 FFmpeg → 最终文件。
- 保留一个手动真实公开视频测试步骤，但不放入普通 pytest。

## M4 完成标准

- 一个公开单 P 视频能完成默认下载和无重编码 MP4 混流。
- video-only、audio-only、no-mux 和 overwrite 能按帮助说明工作。
- 失败不会留下最终半成品，也不会无条件覆盖旧文件。
- Ruff、标准级 Pyright 和 pytest 通过。
- README 和 TODO 不再把 `download` 描述为占位命令。

## 明确留给 M5

- 备用 URL、自动重试、Range、续传状态和并行分块。
- 严格长度/Range 完整性验证与复杂 HTTP 状态恢复。
- 事务式多文件回滚、跨运行任务身份和状态清理策略。
- 带宽限制、URL 刷新和生产级进度/日志系统。
