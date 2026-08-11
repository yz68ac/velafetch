"""FFmpeg resolution stays predictable in source and portable builds."""

from __future__ import annotations

from pathlib import Path

from velafetch.application import FfmpegSource, resolve_ffmpeg


def test_configured_ffmpeg_always_wins() -> None:
    configured = Path("tools/ffmpeg.exe")

    result = resolve_ffmpeg(configured, which=lambda _: "system-ffmpeg")

    assert result is not None
    assert result.path == configured
    assert result.source is FfmpegSource.CONFIGURED


def test_frozen_windows_build_prefers_bundled_ffmpeg(tmp_path: Path) -> None:
    executable = tmp_path / "velafetch.exe"
    bundled = tmp_path / "ffmpeg" / "bin" / "ffmpeg.exe"
    bundled.parent.mkdir(parents=True)
    bundled.touch()

    result = resolve_ffmpeg(
        None,
        which=lambda _: "system-ffmpeg",
        frozen=True,
        executable=executable,
        platform="win32",
    )

    assert result is not None
    assert result.path == bundled
    assert result.source is FfmpegSource.BUNDLED


def test_source_run_ignores_an_adjacent_bundle_and_uses_path(tmp_path: Path) -> None:
    executable = tmp_path / "python.exe"
    bundled = tmp_path / "ffmpeg" / "bin" / "ffmpeg.exe"
    bundled.parent.mkdir(parents=True)
    bundled.touch()

    result = resolve_ffmpeg(
        None,
        which=lambda _: "C:/Tools/ffmpeg.exe",
        frozen=False,
        executable=executable,
        platform="win32",
    )

    assert result is not None
    assert result.path == Path("C:/Tools/ffmpeg.exe")
    assert result.source is FfmpegSource.PATH


def test_missing_bundled_and_system_ffmpeg_returns_none(tmp_path: Path) -> None:
    result = resolve_ffmpeg(
        None,
        which=lambda _: None,
        frozen=True,
        executable=tmp_path / "velafetch.exe",
        platform="win32",
    )

    assert result is None
