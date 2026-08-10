"""One playback unit's transfer, optional mux, and final publication."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from velafetch.application.naming import partial_path
from velafetch.application.transfer import TrackProgressCallback, transfer_track
from velafetch.domain.models import OutputMode, SelectionPolicy
from velafetch.errors import DownloadError
from velafetch.extractors import ResolvedMedia
from velafetch.selection import TrackSelection
from velafetch.transport import HttpClient


def _prune_part_directories(part_path: Path, output_root: Path) -> None:
    state_root = output_root / ".velafetch"
    current = part_path.parent
    while current != output_root:
        try:
            current.rmdir()
        except OSError:
            return
        if current == state_root:
            return
        current = current.parent


def _remove_part(part_path: Path, output_root: Path) -> None:
    try:
        part_path.unlink(missing_ok=True)
    except OSError:
        return
    _prune_part_directories(part_path, output_root)


def _publish(completed: tuple[Path, ...], targets: tuple[Path, ...], *, overwrite: bool) -> None:
    for completed_file, target in zip(completed, targets, strict=True):
        if target.exists() and not overwrite:
            raise DownloadError("An output file appeared while downloading.")
        os.replace(completed_file, target)


async def _stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=3)
    except TimeoutError:
        process.kill()
        await process.wait()


async def _mux(ffmpeg: str, video: Path, audio: Path, destination: Path) -> None:
    try:
        process = await asyncio.create_subprocess_exec(
            ffmpeg,
            "-nostdin",
            "-y",
            "-i",
            str(video),
            "-i",
            str(audio),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c",
            "copy",
            str(destination),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError as error:
        raise DownloadError("FFmpeg could not be started.") from error
    try:
        return_code = await process.wait()
    except asyncio.CancelledError:
        await _stop_process(process)
        raise
    if return_code != 0:
        raise DownloadError("FFmpeg could not mux the selected tracks.")
    if not destination.is_file():
        raise DownloadError("FFmpeg finished without creating an output file.")


async def download_media(
    client: HttpClient,
    unit: ResolvedMedia,
    selection: TrackSelection,
    targets: tuple[Path, ...],
    *,
    state_root: Path,
    ffmpeg: str | None,
    overwrite: bool,
    policy: SelectionPolicy,
    progress: TrackProgressCallback | None,
) -> bool:
    """Download and publish the selected tracks; return whether media was newly saved."""

    if not overwrite and any(target.exists() for target in targets):
        return False
    for target in targets:
        if target.is_dir():
            raise DownloadError("An output path is already a directory.")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise DownloadError("The output directory could not be created.") from error

    video_file = (
        partial_path(
            state_root,
            unit,
            selection.video.format_id,
            selection.video.container,
        )
        if selection.video is not None
        else None
    )
    audio_file = (
        partial_path(
            state_root,
            unit,
            selection.audio.format_id,
            selection.audio.container,
        )
        if selection.audio is not None
        else None
    )
    parts = tuple(path for path in (video_file, audio_file) if path is not None)
    try:
        if selection.video is not None:
            assert video_file is not None
            await transfer_track(client, selection.video, video_file, progress)
        if selection.audio is not None:
            assert audio_file is not None
            await transfer_track(client, selection.audio, audio_file, progress)
        if policy.output_mode is OutputMode.MUXED:
            assert ffmpeg is not None and video_file is not None and audio_file is not None
            with tempfile.TemporaryDirectory(
                prefix=".velafetch-mux-", dir=targets[0].parent
            ) as name:
                muxed = Path(name) / "muxed.mp4"
                await _mux(ffmpeg, video_file, audio_file, muxed)
                _publish((muxed,), targets, overwrite=overwrite)
            for part in parts:
                _remove_part(part, state_root)
        else:
            _publish(parts, targets, overwrite=overwrite)
    except DownloadError:
        raise
    except OSError as error:
        raise DownloadError("The completed output could not be published.") from error
    finally:
        for part in parts:
            _prune_part_directories(part, state_root)
    return True
