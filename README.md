# VelaFetch

VelaFetch is a small Python CLI for learning how a Bilibili media tool works. The code favors a
short, readable call path over production-style abstraction.

## What works

- `info` reads metadata for a public, single-page BV, av, or standard Bilibili video URL.
- `formats` reads and displays DASH video and audio tracks.
- `doctor` checks FFmpeg and optionally checks Bilibili connectivity.
- `download` is still a placeholder for M4; it does not download files yet.

```powershell
uv sync --group dev
uv run velafetch --help
uv run velafetch info BV1xxxxxxxxx
uv run velafetch formats BV1xxxxxxxxx --json
uv run velafetch doctor
```

Root options are intentionally small: `--timeout`, `--proxy`, `--ffmpeg`, and `--version`.
There is no configuration-file system or environment-variable merge layer.

## Development

```powershell
uv run ruff check .
uv run pyright
uv run pytest
```

Tests are offline and use synthetic API fixtures. There is no mandatory coverage percentage: add
a test when it helps explain behavior or reproduce a bug.

## Learning rules

- Prefer a direct implementation before introducing an interface or framework.
- Add validation after a real failure shows why it is useful.
- Never print private media URLs or credentials.
- Never invoke FFmpeg through a shell.
- Never overwrite a user file unless the command explicitly asks for it.

The lightweight M4 implementation plan is in [docs/m4-plan.md](docs/m4-plan.md). It starts with a
single sequential download path; retry and resume are intentionally learned from later bugs.
