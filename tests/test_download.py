"""Offline tests for the first complete download path."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

import pytest

import velafetch.application.transfer as transfer_module
from tests.http_fakes import FakeHttpClient, FakeRequest, FakeResponse
from velafetch.application import DownloadService, DownloadStatus, ProgressUpdate, safe_filename
from velafetch.domain.models import MediaKind, OutputMode, SelectionPolicy

FIXTURES = Path(__file__).parent / "fixtures" / "bilibili"
VIDEO_BYTES = b"synthetic-video"
AUDIO_BYTES = b"synthetic-audio"


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transfer_module, "_RETRY_DELAY_SECONDS", 0)


def _fixture(name: str) -> dict[str, object]:
    value = cast("object", json.loads((FIXTURES / name).read_text(encoding="utf-8")))
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def _handler(
    media_requests: list[FakeRequest],
    *,
    media_status: int = 200,
    video_bytes: bytes = VIDEO_BYTES,
) -> Callable[[FakeRequest], FakeResponse]:
    def handler(request: FakeRequest) -> FakeResponse:
        if request.url.hostname == "api.bilibili.com":
            if request.url.path.endswith("/view"):
                payload = _fixture("view_single.json")
            elif request.url.path.endswith("/nav"):
                payload = _fixture("nav_wbi.json")
            else:
                payload = _fixture("play_dash.json")
            return FakeResponse(200, payload=payload)

        media_requests.append(request)
        content = video_bytes if request.url.hostname == "video.media.invalid" else AUDIO_BYTES
        return FakeResponse(
            media_status,
            content=content,
            headers={"Content-Length": str(len(content))},
        )

    return handler


def _service(handler: Callable[[FakeRequest], FakeResponse]) -> DownloadService:
    def client_factory(
        timeout: float,
        proxy: str | None,
        cookies: Mapping[str, str] | None,
    ) -> FakeHttpClient:
        del timeout, proxy, cookies
        return FakeHttpClient(handler)

    return DownloadService(client_factory)


class FakeProcess:
    def __init__(self, destination: Path, exit_code: int = 0, *, blocking: bool = False) -> None:
        self.destination = destination
        self.exit_code = exit_code
        self.blocking = blocking
        self.returncode: int | None = None
        self.started = asyncio.Event()
        self.finished = asyncio.Event()
        self.terminated = False
        self.killed = False

    async def wait(self) -> int:
        self.started.set()
        if self.blocking:
            await self.finished.wait()
        if self.returncode is None:
            self.returncode = self.exit_code
        if self.returncode == 0:
            self.destination.write_bytes(b"synthetic-muxed")
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15
        self.finished.set()

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        self.finished.set()


@pytest.mark.asyncio
async def test_default_download_streams_tracks_then_muxes_and_publishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media_requests: list[FakeRequest] = []
    ffmpeg_arguments: tuple[object, ...] | None = None

    async def fake_exec(*arguments: object, **kwargs: object) -> FakeProcess:
        nonlocal ffmpeg_arguments
        del kwargs
        ffmpeg_arguments = arguments
        return FakeProcess(Path(str(arguments[-1])))

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    progress: list[ProgressUpdate] = []
    output_dir = tmp_path / "downloads"
    result = await _service(_handler(media_requests)).download(
        "BV1VF4111111",
        output_dir=output_dir,
        policy=SelectionPolicy(),
        ffmpeg_path=Path("fake-ffmpeg"),
        progress=progress.append,
    )

    assert result.output_paths == (output_dir / "Vela Synthetic Flight.mp4",)
    assert result.output_paths[0].read_bytes() == b"synthetic-muxed"
    assert [request.url.hostname for request in media_requests] == [
        "video.media.invalid",
        "audio.media.invalid",
    ]
    assert media_requests[0].headers["referer"].endswith("BV1VF4111111")
    assert ffmpeg_arguments is not None
    assert ffmpeg_arguments[0] == "fake-ffmpeg"
    assert ffmpeg_arguments[-3:-1] == ("-c", "copy")
    assert progress[-1].kind is MediaKind.AUDIO
    assert progress[-1].downloaded == len(AUDIO_BYTES)
    assert progress[-1].total == len(AUDIO_BYTES)
    video_progress = next(event for event in progress if event.kind is MediaKind.VIDEO)
    assert video_progress.quality == "2160p"
    assert video_progress.codec == "av1"
    assert (video_progress.width, video_progress.height) == (3840, 2160)
    assert video_progress.frame_rate_numerator == 60
    assert video_progress.frame_rate_denominator == 1
    assert video_progress.bitrate == 8_000_000
    assert progress[-1].codec == "aac"
    assert progress[-1].bitrate == 192_000
    assert not tuple(output_dir.glob(".velafetch-*"))
    assert not (output_dir / ".velafetch").exists()


@pytest.mark.parametrize(
    ("mode", "names", "hosts"),
    [
        (
            OutputMode.VIDEO_ONLY,
            ("Vela Synthetic Flight.video.mp4",),
            ("video.media.invalid",),
        ),
        (
            OutputMode.AUDIO_ONLY,
            ("Vela Synthetic Flight.audio.m4a",),
            ("audio.media.invalid",),
        ),
        (
            OutputMode.NO_MUX,
            ("Vela Synthetic Flight.video.mp4", "Vela Synthetic Flight.audio.m4a"),
            ("video.media.invalid", "audio.media.invalid"),
        ),
    ],
)
@pytest.mark.asyncio
async def test_non_muxed_modes_publish_the_selected_tracks(
    tmp_path: Path,
    mode: OutputMode,
    names: tuple[str, ...],
    hosts: tuple[str, ...],
) -> None:
    media_requests: list[FakeRequest] = []
    result = await _service(_handler(media_requests)).download(
        "BV1VF4111111",
        output_dir=tmp_path,
        policy=SelectionPolicy(output_mode=mode),
    )

    assert tuple(path.name for path in result.output_paths) == names
    assert tuple(request.url.hostname for request in media_requests) == hosts
    expected = (
        (VIDEO_BYTES, AUDIO_BYTES)
        if mode is OutputMode.NO_MUX
        else (VIDEO_BYTES if mode is OutputMode.VIDEO_ONLY else AUDIO_BYTES,)
    )
    assert tuple(path.read_bytes() for path in result.output_paths) == expected


@pytest.mark.asyncio
async def test_existing_output_skips_media_and_overwrite_replaces_it(tmp_path: Path) -> None:
    first_requests: list[FakeRequest] = []
    policy = SelectionPolicy(output_mode=OutputMode.VIDEO_ONLY)
    first = await _service(_handler(first_requests)).download(
        "BV1VF4111111", output_dir=tmp_path, policy=policy
    )

    skipped_requests: list[FakeRequest] = []
    skipped = await _service(_handler(skipped_requests, video_bytes=b"replacement")).download(
        "BV1VF4111111", output_dir=tmp_path, policy=policy
    )
    assert skipped.skipped is True
    assert skipped_requests == []
    assert first.output_paths[0].read_bytes() == VIDEO_BYTES

    replaced_requests: list[FakeRequest] = []
    replaced = await _service(_handler(replaced_requests, video_bytes=b"replacement")).download(
        "BV1VF4111111",
        output_dir=tmp_path,
        policy=policy,
        overwrite=True,
    )
    assert replaced.skipped is False
    assert replaced.output_paths[0].read_bytes() == b"replacement"


@pytest.mark.asyncio
async def test_http_failure_is_clean_but_ffmpeg_failure_keeps_completed_parts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media_requests: list[FakeRequest] = []
    service = _service(_handler(media_requests, media_status=503))
    failed = await service.download(
        "BV1VF4111111",
        output_dir=tmp_path,
        policy=SelectionPolicy(output_mode=OutputMode.VIDEO_ONLY),
    )
    assert failed.items[0].status is DownloadStatus.FAILED
    assert failed.items[0].error is not None
    assert "media.invalid" not in failed.items[0].error
    assert not tuple(tmp_path.iterdir())

    async def failed_exec(*arguments: object, **kwargs: object) -> FakeProcess:
        del kwargs
        return FakeProcess(Path(str(arguments[-1])), exit_code=1)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", failed_exec)
    failed = await _service(_handler([])).download(
        "BV1VF4111111",
        output_dir=tmp_path,
        policy=SelectionPolicy(),
        ffmpeg_path=Path("fake-ffmpeg"),
    )
    assert failed.items[0].status is DownloadStatus.FAILED
    assert failed.items[0].error is not None
    assert "could not mux" in failed.items[0].error
    parts = tuple((tmp_path / ".velafetch").rglob("*.part"))
    assert len(parts) == 2
    assert {part.read_bytes() for part in parts} == {VIDEO_BYTES, AUDIO_BYTES}
    assert not tuple(tmp_path.glob(".velafetch-mux-*"))


@pytest.mark.asyncio
async def test_cancellation_stops_ffmpeg_and_keeps_completed_parts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process: FakeProcess | None = None

    async def blocking_exec(*arguments: object, **kwargs: object) -> FakeProcess:
        nonlocal process
        del kwargs
        process = FakeProcess(Path(str(arguments[-1])), blocking=True)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", blocking_exec)
    task = asyncio.create_task(
        _service(_handler([])).download(
            "BV1VF4111111",
            output_dir=tmp_path,
            policy=SelectionPolicy(),
            ffmpeg_path=Path("fake-ffmpeg"),
        )
    )
    while process is None:
        await asyncio.sleep(0)
    await process.started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert process.terminated is True
    assert process.killed is False
    parts = tuple((tmp_path / ".velafetch").rglob("*.part"))
    assert len(parts) == 2
    assert {part.read_bytes() for part in parts} == {VIDEO_BYTES, AUDIO_BYTES}
    assert not tuple(tmp_path.glob(".velafetch-mux-*"))


def test_safe_filename_replaces_basic_invalid_characters_and_has_a_fallback() -> None:
    assert safe_filename('  A/B:<C>*?".  ', "BVfallback") == "A_B__C____"
    assert safe_filename("\x00... ", "BVfallback") == "_"
    assert safe_filename("... ", "BVfallback") == "BVfallback"
