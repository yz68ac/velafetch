# VelaFetch

[English](README.md) | [简体中文](README.zh-CN.md)

[![CI](https://github.com/yz68ac/velafetch/actions/workflows/ci.yml/badge.svg)](https://github.com/yz68ac/velafetch/actions/workflows/ci.yml)

VelaFetch 是一个用于查看和下载 Bilibili 公开媒体或用户已获授权媒体的 Python 命令行工具。
它既适合阅读学习，也能用于实际下载：从输入解析、DASH 选轨、断点续传到 FFmpeg 混流，
完整主路径都由普通 Python 模块直接实现，没有引入插件框架。

> 当前版本：`0.2.0`。M0-M7 已完成，M8 增加 Windows 便携包。项目仍处于预发布阶段，
> `1.0` 前 CLI 和 JSON 输出可能发生变化。

## 功能

- 使用 `info` 查看元数据，使用 `formats` 查看经过脱敏的 DASH 轨道。
- 下载普通视频、多 P 视频、公开番剧剧集/季度，以及公开 UGC season/series 合集。
- 使用 `--item`、`--page` 选择单项，或使用 `--all` 顺序下载全部内容。
- 选择分辨率、AVC/HEVC/AV1、SDR/HDR 和纯视频/纯音频输出模式。
- 跨运行保留 `.part` 断点续传，并在失败时轮换 DASH 备用 CDN 地址。
- 使用 FFmpeg 将视频与 AAC 音频无重编码混流为 MP4。
- 默认下载封面和公开字幕，可选下载 XML 弹幕。
- 支持文件名模板，并通过 `--json` 返回适合程序处理的批量结果。
- 通过终端二维码或隐藏 Cookie 输入使用账号本来就有权播放的媒体。
- 每条命令复用一个采用固定 Chrome Profile 的 `curl_cffi.AsyncSession`。

## 支持的来源

| 来源 | 形式示例 | 状态 |
| --- | --- | --- |
| 普通视频 | `BV...`、`av...`、`/video/...` | 支持，包含多 P |
| 番剧 | `ss...`、`ep...`、`/bangumi/play/...` | 支持公开或账号已获授权的播放 |
| UGC 合集 | `space.bilibili.com/<mid>/lists/<id>?type=season` | 支持 |
| UGC 系列 | `space.bilibili.com/<mid>/lists/<id>?type=series` | 支持 |
| 收藏夹 / 稍后再看 | 账号列表 | 尚未实现 |
| 短链 / 付费课程 / 其他站点 | `b23.tv`、cheese、非 Bilibili | 不支持 |

VelaFetch 只使用 Bilibili 返回的普通未加密 DASH。不会绕过试看限制、缺少的账号权益、
地区限制、访问控制或 DRM。

## 环境要求

Windows x64 便携 ZIP 已包含 Python 和 FFmpeg，不需要单独安装运行环境。源码或 wheel
安装方式需要：

- Python 3.12 或更高版本
- 使用 [uv](https://docs.astral.sh/uv/) 管理环境和依赖
- 默认混流输出需要 PATH 中存在 FFmpeg，也可以通过根级 `--ffmpeg` 指定路径

使用 `--video-only`、`--audio-only` 或 `--no-mux` 时不需要 FFmpeg。

## Windows 便携版

从 [GitHub Releases](https://github.com/yz68ac/velafetch/releases) 下载
`VelaFetch-0.2.0-windows-x64.zip` 和 `SHA256SUMS.txt`，校验后解压：

```powershell
Get-FileHash .\VelaFetch-0.2.0-windows-x64.zip -Algorithm SHA256
Expand-Archive .\VelaFetch-0.2.0-windows-x64.zip
.\VelaFetch-0.2.0-windows-x64\velafetch.exe doctor
```

便携包采用 PyInstaller `onedir`，解压后不要拆散 `velafetch.exe`、`_internal` 和 `ffmpeg`
目录。当前产物尚未代码签名，Windows SmartScreen 可能提示未知发布者。内置 FFmpeg 是固定
版本的 Windows x64 LGPL shared 构建，许可证、编译配置、源码位置和校验值均随包提供。

## 快速开始

```powershell
git clone https://github.com/yz68ac/velafetch.git
cd velafetch
uv sync --group dev
uv run velafetch --help
```

`uv run velafetch ...` 会执行包中注册的脚本入口。等效的模块入口是
`uv run python -m velafetch ...`。

所有根级选项都必须写在**子命令之前**：

```powershell
uv run velafetch --timeout 45 --proxy http://127.0.0.1:7890 info "BV..."
uv run velafetch --anonymous formats "ep..."
uv run velafetch --ffmpeg D:\Tools\ffmpeg.exe download "BV..."
```

当前根级选项包括 `--timeout`、`--proxy`、`--ffmpeg`、`--anonymous` 和 `--version`。
VelaFetch 不读取配置文件，也不读取系统代理环境变量。

## 查看媒体信息

下面的 ID 都是占位符，请替换成真实且受支持的来源。

```powershell
# 只获取元数据，不请求播放轨道。
uv run velafetch info "BV..."
uv run velafetch info "BV..." --page 2
uv run velafetch info "ss..." --item 3 --json

# 获取并显示当前播放单元的轨道。
uv run velafetch formats "BV..."
uv run velafetch formats "ep..." --json
uv run velafetch formats "https://space.bilibili.com/<mid>/lists/<id>?type=season" --item 1
```

`--item` 用于选择番剧剧集或合集条目；`--page` 用于选择视频内部的 P。CLI 中的选择会
覆盖来源 URL 自带的 page 或 episode。

## 下载

```powershell
# 默认：最佳受支持 SDR 视频 + AAC 音频、MP4 无重编码混流、封面和全部公开字幕。
uv run velafetch download "BV..." -o downloads

# 限制画质和编码。
uv run velafetch download "BV..." --quality 1080p --codec avc -o downloads

# 选择分 P 或番剧剧集。
uv run velafetch download "BV..." --page 2 --video-only
uv run velafetch download "ss..." --item 2 --danmaku

# 顺序下载完整多 P、季度或合集。
uv run velafetch download "COLLECTION_URL" --all -o downloads

# 机器可读结果；此模式关闭进度条和 ANSI 输出。
uv run velafetch download "COLLECTION_URL" --all --json -o downloads
```

传输期间，进度行会显示实际选中轨道的基础信息，例如：

```text
(1/1) · Video · 1080p · 1920×1080 · AVC · SDR · 30 fps · 5.00 Mbps · 标题
(1/1) · Audio · AAC · 192 kbps · 2 ch · 标题
```

常用选项：

```text
--quality best|HEIGHTp
--codec auto|avc|hevc|av1
--dynamic-range sdr|hdr
--item N / --page N / --all
--video-only | --audio-only | --no-mux
--cover / --no-cover
--subtitles all|off|LANG[,LANG...]
--subtitle-format srt|json
--danmaku
--output-template "{item:02d}-{page:02d}-{title}"
--overwrite
--json
```

`auto` 在同一分辨率下依次优先 AVC、HEVC、AV1。AV1 当前支持 SDR，HDR 当前搭配 HEVC。
显式指定的编码和动态范围不存在时会直接失败，不会静默降级。Dolby Vision、FLAC 和
E-AC-3 轨道可以查看，但不会被自动选择。

默认 sidecar 是封面和所有可用公开字幕。只想下载媒体时可以使用 `--no-cover` 和
`--subtitles off`；弹幕必须显式启用。批量下载会在 `-o` 下创建清理后的来源标题子目录。

## 登录

```powershell
uv run velafetch auth login
uv run velafetch auth status
uv run velafetch auth status --json
uv run velafetch auth logout
```

`auth login` 需要交互式终端，并直接渲染二维码而不生成图片。如果二维码登录不可用，
可以通过隐藏提示导入浏览器 Cookie：

```powershell
uv run velafetch auth import-cookie
```

PowerShell 也可以通过 stdin 传递剪贴板内容，避免 Cookie 出现在命令历史中：

```powershell
Get-Clipboard | uv run velafetch auth import-cookie --stdin
```

程序只保留需要的 Bilibili Cookie 字段，刻意不提供 `--cookie` 参数、Cookie 环境变量或
任意自定义请求头。

凭据以明文 JSON 保存在当前工作目录的 `./.velafetch/credentials.json`。文件已被 Git
忽略并使用原子替换，但它**没有加密**：能读取文件的人就能使用这个登录态。
`auth logout` 只删除本地凭据文件，不会远程退出账号，也不会删除下载 partial。单次命令
可以使用根级 `--anonymous` 完全忽略本地凭据。

Cookie 只匹配 HTTPS `.bilibili.com` 请求，不会发送到媒体 CDN、封面、字幕或合成 fixture
域名。登录态过期后需要重新登录，当前不实现 Cookie 自动刷新。

## 文件和断点续传

- 轨道 partial 位于 `OUTPUT/.velafetch/<source-id>/...`，文件名不包含签名 URL 或请求头。
- 下次运行会探测远端大小，并在可能时使用 HTTP Range 从已有偏移继续。
- 网络中断、取消和 FFmpeg 失败会保留仍可使用的 partial。
- 成功发布后只清理当前条目实际使用的 partial。
- 默认跳过已存在的最终文件；`--overwrite` 也只会在完整新结果准备好后替换旧文件。

## Doctor

```powershell
uv run velafetch doctor
uv run velafetch doctor --network
uv run velafetch doctor --json
```

默认只检查 FFmpeg，不访问网络。`--network` 会额外检查 Bilibili 连通性。`doctor` 还会
说明 FFmpeg 来自 `--ffmpeg`、便携包还是 `PATH`。

## 项目结构

```text
src/velafetch/
├── cli/             Typer 命令和 Rich/JSON 输出
├── application/     下载编排、传输、附加资源和命名
├── extractors/      Bilibili 输入、API 投影、WBI、番剧和合集解析
├── selection/       确定性视频/音频选轨
├── auth/            二维码登录、Cookie 验证和本地凭据存储
├── domain/          不可变媒体与策略模型
└── transport.py     共享 curl_cffi HTTP 客户端
```

主要调用路径保持直接：

```text
CLI → 解析来源 → 获取元数据/格式 → 选轨 → 传输 → 混流/发布
```

## 开发

```powershell
uv sync --group dev
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
uv lock --check
uv build
uv run python scripts/build_portable.py
```

便携构建只会下载 `packaging/ffmpeg-windows-x64.json` 中固定的 FFmpeg 资产；使用
`--offline` 可以要求构建过程仅使用已校验的本地缓存。

普通测试完全离线，使用内存 HTTP fake 和合成 `.invalid` fixtures。项目不强制固定覆盖率；
测试用于解释行为、保护已有契约和复现真实 bug。

实现记录见 [M4](docs/m4-plan.md)、[M5](docs/m5-plan.md)、[M6](docs/m6-plan.md) 和
[M7](docs/m7-plan.md)、[M8](docs/m8-plan.md)。M8 的实际操作过程记录在
[实施日志](docs/m8-implementation-log.md) 中。

## 法律与安全边界

请只使用 VelaFetch 获取你有权访问和保存的内容。项目不实现付费、会员、地区、访问控制或
DRM 绕过。完整边界见 [docs/legal-and-security.md](docs/legal-and-security.md)。

VelaFetch 使用 [MIT License](LICENSE)。内置 FFmpeg 与 Python 依赖保留各自许可证，详见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
