# VelaFetch

[English](README.md) | [简体中文](README.zh-CN.md)

[![CI](https://github.com/yz68ac/velafetch/actions/workflows/ci.yml/badge.svg)](https://github.com/yz68ac/velafetch/actions/workflows/ci.yml)

## Beginner guide (Windows, no setup required)

1. Open [GitHub Releases](https://github.com/yz68ac/velafetch/releases) and download
   `VelaFetch-0.2.0-windows-x64.zip`. Do not download the automatically generated "Source code"
   archives.
2. Right-click the ZIP and select **Extract All**. Open the extracted
   `VelaFetch-0.2.0-windows-x64` folder. Do not run the program from inside the ZIP, and do not move
   `velafetch.exe` away from the `_internal` and `ffmpeg` folders.
3. Click the File Explorer address bar, type `powershell`, and press Enter. A blue terminal window
   will open in the correct folder.
4. Replace the example address below with a Bilibili video URL or BV ID, then paste the command and
   press Enter:

   ```powershell
   .\velafetch.exe download "https://www.bilibili.com/video/BV..." -o downloads
   ```

5. When it finishes, the video is in the newly created `downloads` folder. No Python, uv, or FFmpeg
   installation is needed.

For a multi-part video, season, or collection, add `--all` to download everything. If playback
requires your account, run `.\velafetch.exe auth login` first and scan the QR code. The executable is
currently unsigned, so Windows may display an unknown-publisher warning; only continue when the ZIP
came from the official Releases page above.

VelaFetch is a Python CLI for inspecting and downloading public or user-authorized Bilibili media.
It is built to be readable enough for learning and useful enough for real downloads: the complete
path from input parsing and DASH track selection to resumable transfer and FFmpeg muxing lives in
ordinary Python modules without a plugin framework.

> Current version: `0.2.0`. M0-M7 are complete and M8 adds Windows portable packaging. The project
> is still pre-release software; CLI and JSON output may change before `1.0`.

## Features

- Inspect metadata with `info` and list sanitized DASH tracks with `formats`.
- Download ordinary videos, multi-P videos, public Bangumi episodes/seasons, and public UGC
  season/series collections.
- Select a single episode/page or download every item sequentially with `--all`.
- Choose resolution, AVC/HEVC/AV1, SDR/HDR, and video/audio output modes.
- Resume persistent `.part` files across runs and rotate through backup CDN URLs.
- Copy-mux video and AAC audio into MP4 with FFmpeg; no media re-encoding.
- Download covers and public subtitles by default, with optional XML danmaku.
- Use filename templates and receive machine-readable batch results with `--json`.
- Log in through a terminal QR code or a hidden Cookie prompt for media the account is already
  authorized to play.
- Use one `curl_cffi.AsyncSession` with a fixed Chrome profile for each command.

## Supported sources

| Source | Example shape | Status |
| --- | --- | --- |
| Ordinary video | `BV...`, `av...`, `/video/...` | Supported, including multi-P |
| Bangumi | `ss...`, `ep...`, `/bangumi/play/...` | Public or account-authorized playback |
| UGC collection | `space.bilibili.com/<mid>/lists/<id>?type=season` | Supported |
| UGC series | `space.bilibili.com/<mid>/lists/<id>?type=series` | Supported |
| Favorites / Watch later | Account lists | Not implemented |
| Short links / Paid courses / Other sites | `b23.tv`, cheese, non-Bilibili | Not supported |

Only ordinary, unencrypted DASH returned by Bilibili is used. Preview-only playback, missing
entitlements, region restrictions, access controls, and DRM are not bypassed.

## Requirements

The Windows x64 portable ZIP includes Python and FFmpeg and has no separate runtime requirement.
For source or wheel installations:

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/) for environment and package management
- FFmpeg available on `PATH`, or supplied with the root `--ffmpeg` option, when using the default
  muxed output

FFmpeg is not needed for `--video-only`, `--audio-only`, or `--no-mux`.

## Windows portable release

Download `VelaFetch-0.2.0-windows-x64.zip` and `SHA256SUMS.txt` from the
[GitHub Releases page](https://github.com/yz68ac/velafetch/releases), then verify and extract it:

```powershell
Get-FileHash .\VelaFetch-0.2.0-windows-x64.zip -Algorithm SHA256
Expand-Archive .\VelaFetch-0.2.0-windows-x64.zip
.\VelaFetch-0.2.0-windows-x64\velafetch.exe doctor
```

The portable package uses PyInstaller `onedir`. Keep `velafetch.exe`, `_internal`, and `ffmpeg`
together after extraction. It is currently unsigned, so Windows SmartScreen may show an unknown
publisher warning. The bundled FFmpeg is a pinned Windows x64 LGPL shared build; its license,
configuration, source locations, and checksums are included in the package and Release assets.

## Quick start

```powershell
git clone https://github.com/yz68ac/velafetch.git
cd velafetch
uv sync --group dev
uv run velafetch --help
```

`uv run velafetch ...` executes the script entry registered by the package. The equivalent module
entry is `uv run python -m velafetch ...`.

All root options must appear **before** the subcommand:

```powershell
uv run velafetch --timeout 45 --proxy http://127.0.0.1:7890 info "BV..."
uv run velafetch --anonymous formats "ep..."
uv run velafetch --ffmpeg D:\Tools\ffmpeg.exe download "BV..."
```

Available root options are `--timeout`, `--proxy`, `--ffmpeg`, `--anonymous`, and `--version`.
VelaFetch does not load a configuration file or proxy environment variables.

## Inspect media

The IDs below are placeholders; replace them with a real supported source.

```powershell
# Metadata only; this does not fetch playback tracks.
uv run velafetch info "BV..."
uv run velafetch info "BV..." --page 2
uv run velafetch info "ss..." --item 3 --json

# Fetch and display tracks for the selected playback unit.
uv run velafetch formats "BV..."
uv run velafetch formats "ep..." --json
uv run velafetch formats "https://space.bilibili.com/<mid>/lists/<id>?type=season" --item 1
```

`--item` selects a Bangumi episode or collection entry. `--page` selects a P inside a video. CLI
selection overrides a page or episode embedded in the source URL.

## Download

```powershell
# Default: best supported SDR video + AAC audio, MP4 copy mux, cover and all public subtitles.
uv run velafetch download "BV..." -o downloads

# Restrict quality and codec.
uv run velafetch download "BV..." --quality 1080p --codec avc -o downloads

# Select a page or episode.
uv run velafetch download "BV..." --page 2 --video-only
uv run velafetch download "ss..." --item 2 --danmaku

# Sequentially download a complete multi-P video, season, or collection.
uv run velafetch download "COLLECTION_URL" --all -o downloads

# Machine-readable result; progress and ANSI output are disabled.
uv run velafetch download "COLLECTION_URL" --all --json -o downloads
```

While transferring, the progress line shows the selected track's basic information, for example:

```text
(1/1) · Video · 1080p · 1920×1080 · AVC · SDR · 30 fps · 5.00 Mbps · Title
(1/1) · Audio · AAC · 192 kbps · 2 ch · Title
```

Useful options:

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

`auto` prefers AVC, then HEVC, then AV1 at the same resolution. AV1 is supported for SDR and HDR
is supported with HEVC. Explicit codec and dynamic-range requests fail instead of silently falling
back. Dolby Vision, FLAC, and E-AC-3 tracks can be inspected but are not selected automatically.

The default sidecars are the cover and all available public subtitles. Use `--no-cover` and
`--subtitles off` for media only. Danmaku remains opt-in. Batch downloads create a cleaned
source-title subdirectory below `-o`.

## Login

```powershell
uv run velafetch auth login
uv run velafetch auth status
uv run velafetch auth status --json
uv run velafetch auth logout
```

`auth login` requires an interactive terminal and renders the QR code without writing an image.
If QR login is unavailable, import a browser Cookie through the hidden prompt:

```powershell
uv run velafetch auth import-cookie
```

PowerShell can also pass the clipboard through stdin without placing the Cookie in command history:

```powershell
Get-Clipboard | uv run velafetch auth import-cookie --stdin
```

Only the required Bilibili Cookie fields are retained. There is deliberately no `--cookie` option,
Cookie environment variable, or general custom-header option.

Credentials are stored as plaintext JSON at `./.velafetch/credentials.json`, relative to the
current working directory. The file is Git-ignored and replaced atomically, but it is **not
encrypted**. Anyone who can read it can use the session. `auth logout` deletes only this file and
does not remotely log out the account or remove download partials. Use the root `--anonymous`
option to ignore local credentials for one command.

Cookies are scoped to HTTPS `.bilibili.com` requests and are not sent to media CDN, cover, subtitle,
or synthetic fixture hosts. Expired sessions require a new login; automatic Cookie refresh is not
implemented.

## Files and resume behavior

- Partial tracks live below `OUTPUT/.velafetch/<source-id>/...` and do not contain signed URLs or
  request headers in their names.
- A later run probes the remote size and resumes with HTTP Range when possible.
- Network interruption, cancellation, and FFmpeg failure preserve usable partials.
- Successful publication removes only the partials consumed by that item.
- Existing final files are skipped by default; `--overwrite` replaces them only after a complete
  new result is ready.

## Doctor

```powershell
uv run velafetch doctor
uv run velafetch doctor --network
uv run velafetch doctor --json
```

The default check validates FFmpeg without accessing the network. `--network` additionally checks
Bilibili connectivity. `doctor` reports whether FFmpeg came from `--ffmpeg`, the portable bundle,
or `PATH`.

## Project layout

```text
src/velafetch/
├── cli/             Typer commands and Rich/JSON rendering
├── application/     Download orchestration, transfer, assets, and naming
├── extractors/      Bilibili input parsing, API projection, WBI, Bangumi, and collections
├── selection/       Deterministic video/audio track selection
├── auth/            QR login, Cookie validation, and local credential storage
├── domain/          Immutable media and policy models
└── transport.py     Shared curl_cffi HTTP client
```

The main path is intentionally direct:

```text
CLI → resolve source → fetch metadata/formats → select tracks → transfer → mux/publish
```

## Development

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

The portable build downloads only the FFmpeg archive pinned in
`packaging/ffmpeg-windows-x64.json`; pass `--offline` to require a previously verified cache.

Tests are offline and use an in-memory HTTP fake plus synthetic `.invalid` fixtures. There is no
mandatory coverage percentage; tests are used to explain behavior, preserve contracts, and
reproduce real bugs.

Implementation notes are available for [M4](docs/m4-plan.md), [M5](docs/m5-plan.md),
[M6](docs/m6-plan.md), [M7](docs/m7-plan.md), and [M8](docs/m8-plan.md). The actual M8 work is
recorded in the [implementation log](docs/m8-implementation-log.md).

## Legal and security

Use VelaFetch only for content you are permitted to access and save. The project does not implement
payment, membership, region, access-control, or DRM bypasses. See
[docs/legal-and-security.md](docs/legal-and-security.md) for the complete boundary.

VelaFetch is licensed under the [MIT License](LICENSE). The bundled FFmpeg and Python dependencies
retain their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
