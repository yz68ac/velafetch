"""Locate an explicitly configured, bundled, or system FFmpeg executable."""

from __future__ import annotations

import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class FfmpegSource(StrEnum):
    CONFIGURED = "configured"
    BUNDLED = "bundled"
    PATH = "path"


@dataclass(frozen=True, slots=True)
class FfmpegExecutable:
    path: Path
    source: FfmpegSource


def resolve_ffmpeg(
    configured: Path | None,
    *,
    which: Callable[[str], str | None] | None = None,
    frozen: bool | None = None,
    executable: Path | None = None,
    platform: str | None = None,
) -> FfmpegExecutable | None:
    """Resolve FFmpeg with configured > portable bundle > PATH precedence."""

    if configured is not None:
        return FfmpegExecutable(configured.expanduser(), FfmpegSource.CONFIGURED)

    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if is_frozen:
        program = executable or Path(sys.executable)
        platform_name = platform or sys.platform
        filename = "ffmpeg.exe" if platform_name == "win32" else "ffmpeg"
        bundled = program.resolve().parent / "ffmpeg" / "bin" / filename
        if bundled.is_file():
            return FfmpegExecutable(bundled, FfmpegSource.BUNDLED)

    lookup = which or shutil.which
    system = lookup("ffmpeg")
    if system is None:
        return None
    return FfmpegExecutable(Path(system), FfmpegSource.PATH)
