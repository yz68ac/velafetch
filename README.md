# VelaFetch

VelaFetch is a Python CLI for inspecting and downloading public or user-authorized Bilibili media.
The implementation keeps the request → extraction → selection → transfer path readable enough to
study while supporting practical multi-item downloads, recovery, and an optional local login.

## What works

- `info` inspects ordinary videos, multi-P videos, public Bangumi seasons/episodes, and public UGC
  season/series lists.
- `formats` lists the selected playback unit's DASH tracks without exposing private media URLs.
- `download` supports one item/page or sequential `--all` downloads, persistent `.part` resume,
  backup CDN URLs, four output modes, and FFmpeg copy muxing.
- Cover images and all public subtitle tracks are downloaded by default; XML danmaku is opt-in.
- Filename templates, AV1 SDR, HEVC HDR, and JSON batch results are available.
- `doctor` checks FFmpeg and can optionally test Bilibili connectivity.
- `auth` can scan a Web QR code, validate a hidden Cookie, show login status, or remove the local
  login.
- One `curl_cffi.AsyncSession` with a fixed Chrome profile is reused for each command.

```powershell
uv sync --group dev
uv run velafetch --help

uv run velafetch auth login
uv run velafetch auth status

uv run velafetch info BV1xxxxxxxxx --page 2
uv run velafetch info ss47200 --json
uv run velafetch formats "https://space.bilibili.com/546195/lists/1903592?type=season" --item 1

uv run velafetch download BV1xxxxxxxxx -o downloads
uv run velafetch download BV1xxxxxxxxx --page 2 --video-only
uv run velafetch download ss47200 --item 1 --danmaku
uv run velafetch download COLLECTION_URL --all --json -o downloads
uv run velafetch doctor
```

`auth login` renders a QR code only in an interactive terminal. As a fallback, `auth import-cookie`
uses a hidden prompt; `Get-Clipboard | uv run velafetch auth import-cookie --stdin` avoids placing
the Cookie itself in PowerShell history. VelaFetch deliberately has no `--cookie` option, Cookie
environment variable, or credential configuration field.

`--item` selects a season episode or collection entry; `--page` selects a video P. `--all` is only
available on `download` and recursively expands every selected video's pages. Batch output goes into
a cleaned source-title subdirectory.

Useful download options include:

```text
--quality best|HEIGHTp
--codec auto|avc|hevc|av1
--dynamic-range sdr|hdr
--video-only | --audio-only | --no-mux
--cover / --no-cover
--subtitles all|off|LANG[,LANG...]
--subtitle-format srt|json
--danmaku
--output-template "{item:02d}-{page:02d}-{title}"
--overwrite
--json
```

The root options are `--timeout`, `--proxy`, `--ffmpeg`, `--anonymous`, and `--version`; put them
before the subcommand. `--anonymous` completely ignores the local login for that command. There is
no configuration-file or environment-variable merge system.

## Login and access boundary

By explicit project choice, the active Bilibili Cookie is stored as plaintext JSON at
`./.velafetch/credentials.json`, relative to the current working directory. The file is Git-ignored
and atomically replaced, but it is not encrypted: anyone who can read it can use the session. Run
`velafetch auth logout` to remove only this file. Moving to another working directory creates an
independent login state.

The Cookie is scoped to HTTPS requests under `.bilibili.com`; it is not sent to media CDN, cover,
or subtitle hosts. An authenticated session can expose account-visible qualities, subtitles, and
ordinary DASH playback that the account is already authorized to access. VelaFetch does not bypass
payment, membership, region restrictions, access control, or DRM. Expired sessions require a new
QR login; automatic Cookie refresh is intentionally not implemented. Favorites, watch-later lists,
password/SMS login, TV tokens, and paid-course inputs remain unsupported.

The Chrome profile is fixed. VelaFetch does not rotate fingerprints, proxies, or identities.
`--proxy` passes one explicit proxy to curl; system proxy environment variables are ignored.

## Files and recovery

Interrupted tracks remain below `OUTPUT/.velafetch/<source-id>/...`. A later run probes the remote
size and resumes when possible. Final media and sidecars are published with `os.replace`; existing
files are kept unless `--overwrite` is supplied. Successful publication removes only the partials
used by that item.

## Development

```powershell
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
uv lock --check
uv build
```

Tests are offline and use an in-memory HTTP fake plus synthetic `.invalid` fixtures. There is no
mandatory coverage percentage: tests are added to explain behavior, preserve contracts, and
reproduce real bugs.

Milestone notes: [M4](docs/m4-plan.md), [M5](docs/m5-plan.md), [M6](docs/m6-plan.md),
[M7](docs/m7-plan.md).
