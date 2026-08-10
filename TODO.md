# VelaFetch TODO

VelaFetch 从可阅读、可学习的实现逐步走向实际使用。路线图保留清晰阶段，但不为尚未
发生的问题提前搭建框架；先完成可运行主路径，再把真实使用中的问题变成改进和测试。

## M0：项目可以运行（已完成）

- [x] 建立 Python 3.12+ 包结构、`pyproject.toml` 和 `uv.lock`。
- [x] 提供 `velafetch` 与 `python -m velafetch` 两种入口。
- [x] 配置 Ruff、标准级 Pyright、pytest 和一个简单 CI。
- [x] 使用合成 fixtures，普通测试不依赖公网。
- [x] 保留 BBDown 与 N_m3u8DL-RE 作为本地阅读材料，不参与构建和运行。

## M1：CLI 和媒体模型（已完成）

- [x] 注册 `info`、`formats`、`download`、`doctor`。
- [x] 保留少量全局选项：超时、代理、FFmpeg 路径和版本。
- [x] 定义站点、媒体、页面、视频/音频轨道和选轨策略。
- [x] 支持人类表格与简单 JSON，不维护版本化 JSON Schema。
- [x] 统一显示可预期错误，参数错误仍由 Typer 处理。

## M2：直接的 HTTP 与诊断（已完成）

- [x] 每条命令创建和关闭一个 `curl_cffi.AsyncSession`，固定使用 Chrome Profile。
- [x] 支持显式超时和代理，不建立配置文件合并系统。
- [x] 默认忽略系统代理环境变量，不做指纹或代理轮换。
- [x] `doctor` 检查 FFmpeg，并可通过 `--network` 检查 Bilibili。
- [x] FFmpeg 检查使用参数数组，不经过 shell。
- [x] 删除未被真实功能使用的重试、状态、存储和通用进程框架。

## M3：普通 Bilibili 视频解析（已完成）

- [x] 解析 BV、av 和标准 `/video/...` URL。
- [x] 读取公开单 P 视频标题、时长、BV/av/cid。
- [x] 完成匿名 WBI 签名并读取 DASH 播放信息。
- [x] 投影 AVC、HEVC、AV1、AAC、E-AC-3、FLAC 和动态范围信息。
- [x] `formats` 标出当前可下载和暂不支持的轨道。
- [x] 实现画质上限、编码优先级与 AAC 音频选择。
- [x] 明确拒绝短链、登录或受限内容；多 P、番剧与公开合集在 M6 扩展。

## M4：第一个可下载版本（已完成）

- [x] 接通 `download`：提取 → 选轨 → 下载 → 混流 → 输出。
- [x] 顺序下载一条视频和一条音频，不做并行分块。
- [x] 使用输出目录内的临时目录，失败时不留下最终半成品。
- [x] 显示基础字节数、速度和总大小进度。
- [x] 使用 FFmpeg `-c copy` 混流，不经过 shell。
- [x] 支持默认混流、video-only、audio-only 和 no-mux。
- [x] 已有文件默认跳过；只有 `--overwrite` 才替换完整的新结果。
- [x] 使用假 API、假 CDN 和假 FFmpeg 完成一条离线集成测试。
- [x] 更新 README，并删除 `download` 的占位错误。

详细实现顺序见 [docs/m4-plan.md](docs/m4-plan.md)。

## M5：轻量下载可靠性（已完成）

- [x] 主地址失败时按顺序尝试 DASH 备用地址，每条轨道最多传输三次。
- [x] 将轨道保存为稳定路径下的 `.part`，再次运行时通过 Range 探测并续传。
- [x] 处理 Range 被忽略，以及合法或异常的 200、206、416 响应。
- [x] 校验可用的远端长度，保留可续传的短文件并丢弃矛盾或过长的 partial。
- [x] 下载、网络、FFmpeg 失败和 Ctrl+C 保留 partial；成功发布后清理已用 partial。
- [x] 用可编排的内存 HTTP fake 覆盖备用地址、断流、续传和长度变化。

具体行为和刻意保留的限制见 [docs/m5-plan.md](docs/m5-plan.md)。

## 按真实问题追加的可靠性 backlog

- [ ] 根据大文件体验决定是否需要限速或并行下载。
- [ ] Windows 文件占用、只读目录和磁盘不足出现后增加针对性处理。
- [ ] 遇到实际播放地址过期后，再设计 URL 刷新策略。
- [ ] 遇到 no-mux 第二个文件发布失败后，再决定是否需要多文件回滚。

## M6：Bilibili 常用功能（已完成）

- [x] 多 P 列表、`--page` 选择及递归 `--all`。
- [x] 公开番剧 season/episode 解析、`--item` 选择和整季顺序下载。
- [x] 公开 UGC season/series 完整分页、去重和合集批量；收藏夹与稍后再看继续留在后续需求。
- [x] 默认封面和公开字幕、可选 XML 弹幕，以及 sidecar 的安全发布。
- [x] 文件名模板、批量子目录和逐项 `saved|skipped|partial|failed` JSON 结果。
- [x] AV1 SDR 与 HEVC HDR 严格选轨；Dolby、FLAC、E-AC-3 保持可见但不自动混流。
- [x] 离线 fixtures 覆盖资源、命名、sidecar、批量和格式选择，并完成匿名公开接口验收。

详细行为与真实验收记录见 [docs/m6-plan.md](docs/m6-plan.md)。

## M7：登录与用户授权内容

- [x] Cookie 只通过隐藏提示或 stdin 输入，不进入参数、环境变量和日志。
- [x] 在当前目录明文保存一个账号，支持验证、替换、状态查看和本地清除。
- [x] 实现终端二维码生成、轮询、超时、取消和成功后 nav 验证。
- [x] 现有视频、番剧与 UGC 合集自动使用登录态，并提供根级 `--anonymous`。
- [x] 只使用账号获权的普通 DASH；会员/付费拒绝、地区限制和 DRM 不做绕过。
- [ ] 使用真实账号完成一次扫码、状态、登录/匿名格式对比和下载验收。

详细行为见 [docs/m7-plan.md](docs/m7-plan.md)。收藏夹、稍后再看和 Cookie 自动刷新只有在
出现明确使用需求后再设计，不阻塞现有来源的登录能力。

## M8：方便分发

- [ ] 先提供 wheel 和清晰的 uv 安装说明。
- [ ] 有真实分发需求后再尝试 PyInstaller。
- [ ] 决定 FFmpeg 由用户安装还是随包分发。
- [ ] 分发前检查项目许可证、依赖许可证和 FFmpeg 构建许可。
- [ ] 为发布产物生成版本号和校验值。

## M9：其他站点和协议

- [ ] 有明确需求后再评估 yt-dlp 可选集成。
- [ ] 从真实输入出发学习 M3U8/HLS 或 MPD/DASH 下载。
- [ ] 不为了“通用”提前建立插件系统。

## 每个里程碑的完成条件

- 功能可以通过 CLI 手动运行。
- 至少有一个主路径测试，以及真实修复过的 bug 对应测试。
- Ruff、Pyright 和 pytest 通过；不要求固定覆盖率数字。
- README/TODO 与实际行为一致。
- 不输出私有媒体 URL 或凭据，不通过 shell 调用外部程序。
- 写文件的功能不得在未指定 `--overwrite` 时覆盖已有文件。
