$ErrorActionPreference = "Stop"

uv run ruff check .
uv run pyright
uv run pytest
