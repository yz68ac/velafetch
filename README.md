# VelaFetch

VelaFetch is a Python CLI for inspecting and downloading anonymously accessible Bilibili media.
The implementation keeps the request → extraction → selection → transfer path readable enough to
study while supporting practical multi-item downloads and recovery.

## What works

- `info` inspects ordinary videos, multi-P videos, public Bangumi seasons/episodes, and public UGC
  season/series lists.
- `formats` lists the selected playback unit's DASH tracks without exposing private media URLs.
- `download` supports one item/page or sequential `--all` downloads, persistent `.part` resume,
  backup CDN URLs, four output modes, and FFmpeg copy muxing.
- Cover images and all public subtitle tracks are downloaded by default; XML danmaku is opt-in.
- Filename templates, AV1 SDR, HEVC HDR, and JSON batch results are available.
- `doctor` checks FFmpeg and can optionally test Bilibili connectivity.
- One `curl_cffi.AsyncSession` with a fixed Chrome profile is reused for each command.

```powershell
uv sync --group dev
uv run velafetch --help

uv run velafetch info BV1xxxxxxxxx --page 2
uv run velafetch info ss47200 --json
uv run velafetch formats "https://space.bilibili.com/546195/lists/1903592?type=season" --item 1

uv run velafetch download BV1xxxxxxxxx -o downloads
uv run velafetch download BV1xxxxxxxxx --page 2 --video-only
uv run velafetch download ss47200 --item 1 --danmaku
uv run velafetch download COLLECTION_URL --all --json -o downloads
uv run velafetch doctor
```

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

The root options remain `--timeout`, `--proxy`, `--ffmpeg`, and `--version`; put them before the
subcommand. There is no configuration-file or environment-variable merge system.

## Anonymous-access boundary

VelaFetch does not accept cookies or credentials in M6. It does not bypass login, payment,
membership, region restrictions, access control, or DRM. Bilibili may mark subtitle metadata with
`need_login_subtitle`; those tracks are unavailable within this anonymous-only milestone. Asking
for a specific unavailable language produces a partial item result, while no public subtitles in
the default `all` mode is normal.

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

Milestone notes: [M4](docs/m4-plan.md), [M5](docs/m5-plan.md), [M6](docs/m6-plan.md).
