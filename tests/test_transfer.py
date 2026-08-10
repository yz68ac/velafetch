"""Offline examples for retry, fallback, and resumable track transfer."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import velafetch.application.transfer as transfer_module
from tests.http_fakes import FakeHttpClient, FakeRequest, FakeResponse
from velafetch.application.transfer import transfer_track
from velafetch.domain.models import CodecFamily, MediaFormat, MediaKind, MediaSource
from velafetch.errors import NetworkOperationError
from velafetch.transport import RequestError

DATA = b"abcdef"


def _track(*hosts: str) -> MediaFormat:
    return MediaFormat(
        format_id="video-32-avc-test",
        kind=MediaKind.VIDEO,
        container="mp4",
        codec="avc1.64001F",
        codec_family=CodecFamily.AVC,
        bitrate=1000,
        source=MediaSource(
            urls=tuple(f"https://{host}/video.m4s?token=secret" for host in hosts),
            required_headers={"Referer": "https://www.bilibili.com/video/BV1Test11111"},
        ),
        width=640,
        height=360,
    )


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transfer_module, "_RETRY_DELAY_SECONDS", 0)


@pytest.mark.asyncio
async def test_primary_failure_uses_backup_url(tmp_path: Path) -> None:
    requests: list[FakeRequest] = []

    def handler(request: FakeRequest) -> FakeResponse:
        requests.append(request)
        if request.url.hostname == "primary.invalid":
            return FakeResponse(503)
        return FakeResponse(200, content=DATA, headers={"Content-Length": str(len(DATA))})

    result = await transfer_track(
        FakeHttpClient(handler),
        _track("primary.invalid", "backup.invalid"),
        tmp_path / "track.part",
        None,
    )

    assert result.read_bytes() == DATA
    assert [request.url.hostname for request in requests] == ["primary.invalid", "backup.invalid"]
    assert requests[-1].headers["accept-encoding"] == "identity"


@pytest.mark.asyncio
async def test_three_failures_cycle_sources_without_leaking_urls(tmp_path: Path) -> None:
    requests: list[FakeRequest] = []

    def handler(request: FakeRequest) -> FakeResponse:
        requests.append(request)
        return FakeResponse(503)

    with pytest.raises(NetworkOperationError) as caught:
        await transfer_track(
            FakeHttpClient(handler),
            _track("primary.invalid", "backup-a.invalid", "backup-b.invalid"),
            tmp_path / "track.part",
            None,
        )

    assert [request.url.hostname for request in requests] == [
        "primary.invalid",
        "backup-a.invalid",
        "backup-b.invalid",
    ]
    assert "3 attempts" in str(caught.value)
    assert "503" in str(caught.value)
    assert "invalid" not in str(caught.value)
    assert "secret" not in str(caught.value)


@pytest.mark.asyncio
async def test_stream_error_resumes_on_next_source(tmp_path: Path) -> None:
    requests: list[FakeRequest] = []

    def handler(request: FakeRequest) -> FakeResponse:
        requests.append(request)
        if len(requests) == 1:
            return FakeResponse(
                200,
                chunks=(b"abc",),
                headers={"Content-Length": "6"},
                stream_error=RequestError("synthetic disconnect"),
            )
        assert request.headers["range"] == "bytes=3-"
        return FakeResponse(
            206,
            content=b"def",
            headers={"Content-Length": "3", "Content-Range": "bytes 3-5/6"},
        )

    part = tmp_path / "track.part"
    await transfer_track(
        FakeHttpClient(handler),
        _track("primary.invalid", "backup.invalid"),
        part,
        None,
    )

    assert part.read_bytes() == DATA


@pytest.mark.asyncio
async def test_second_run_probes_and_resumes_existing_part(tmp_path: Path) -> None:
    part = tmp_path / "track.part"
    first_requests = 0

    def interrupted(request: FakeRequest) -> FakeResponse:
        nonlocal first_requests
        first_requests += 1
        if first_requests == 1:
            return FakeResponse(
                200,
                chunks=(b"abc",),
                headers={"Content-Length": "6"},
                stream_error=RequestError("synthetic disconnect"),
            )
        return FakeResponse(
            206,
            headers={"Content-Range": "bytes 3-5/6"},
            stream_error=RequestError("still disconnected"),
        )

    with pytest.raises(NetworkOperationError):
        await transfer_track(FakeHttpClient(interrupted), _track("primary.invalid"), part, None)
    assert first_requests == 3
    assert part.read_bytes() == b"abc"

    second_requests: list[FakeRequest] = []

    def resumed(request: FakeRequest) -> FakeResponse:
        second_requests.append(request)
        if request.headers["range"] == "bytes=0-0":
            return FakeResponse(206, content=b"a", headers={"Content-Range": "bytes 0-0/6"})
        assert request.headers["range"] == "bytes=3-"
        return FakeResponse(206, content=b"def", headers={"Content-Range": "bytes 3-5/6"})

    progress: list[tuple[MediaKind, int, int | None]] = []
    await transfer_track(
        FakeHttpClient(resumed),
        _track("primary.invalid"),
        part,
        lambda kind, done, total: progress.append((kind, done, total)),
    )

    assert part.read_bytes() == DATA
    assert [request.headers["range"] for request in second_requests] == [
        "bytes=0-0",
        "bytes=3-",
    ]
    assert progress[0] == (MediaKind.VIDEO, 3, 6)


@pytest.mark.asyncio
async def test_range_ignored_by_server_restarts_cleanly(tmp_path: Path) -> None:
    part = tmp_path / "track.part"
    part.write_bytes(b"abc")

    def handler(request: FakeRequest) -> FakeResponse:
        if request.headers["range"] == "bytes=0-0":
            return FakeResponse(206, content=b"a", headers={"Content-Range": "bytes 0-0/6"})
        return FakeResponse(200, content=b"uvwxyz", headers={"Content-Length": "6"})

    progress: list[tuple[MediaKind, int, int | None]] = []
    await transfer_track(
        FakeHttpClient(handler),
        _track("primary.invalid"),
        part,
        lambda kind, done, total: progress.append((kind, done, total)),
    )

    assert part.read_bytes() == b"uvwxyz"
    assert (MediaKind.VIDEO, 0, 6) in progress


@pytest.mark.asyncio
async def test_invalid_content_range_falls_back_without_corrupting_part(tmp_path: Path) -> None:
    part = tmp_path / "track.part"
    part.write_bytes(b"abc")
    requests: list[FakeRequest] = []

    def handler(request: FakeRequest) -> FakeResponse:
        requests.append(request)
        if request.headers["range"] == "bytes=0-0":
            return FakeResponse(206, content=b"a", headers={"Content-Range": "bytes 0-0/6"})
        if request.url.hostname == "primary.invalid":
            return FakeResponse(206, content=b"cdef", headers={"Content-Range": "bytes 2-5/6"})
        return FakeResponse(206, content=b"def", headers={"Content-Range": "bytes 3-5/6"})

    await transfer_track(
        FakeHttpClient(handler),
        _track("primary.invalid", "backup.invalid"),
        part,
        None,
    )

    assert part.read_bytes() == DATA
    assert requests[-1].url.hostname == "backup.invalid"


@pytest.mark.asyncio
async def test_body_larger_than_declared_range_discards_the_part(tmp_path: Path) -> None:
    part = tmp_path / "track.part"
    part.write_bytes(b"abc")
    requests = 0

    def handler(request: FakeRequest) -> FakeResponse:
        nonlocal requests
        requests += 1
        if requests == 1:
            return FakeResponse(206, content=b"a", headers={"Content-Range": "bytes 0-0/6"})
        if requests == 2:
            return FakeResponse(206, content=b"def", headers={"Content-Range": "bytes 3-4/6"})
        assert "range" not in request.headers
        return FakeResponse(200, content=DATA, headers={"Content-Length": "6"})

    await transfer_track(FakeHttpClient(handler), _track("primary.invalid"), part, None)

    assert part.read_bytes() == DATA


@pytest.mark.asyncio
async def test_416_without_content_range_rechecks_completed_part(tmp_path: Path) -> None:
    part = tmp_path / "track.part"
    part.write_bytes(DATA)
    responses = iter(
        [
            FakeResponse(503),
            FakeResponse(416),
            FakeResponse(206, content=b"a", headers={"Content-Range": "bytes 0-0/6"}),
        ]
    )

    result = await transfer_track(
        FakeHttpClient(lambda _: next(responses)),
        _track("primary.invalid"),
        part,
        None,
    )

    assert result.read_bytes() == DATA


@pytest.mark.asyncio
async def test_missing_length_accepts_nonempty_eof(tmp_path: Path) -> None:
    part = tmp_path / "track.part"
    await transfer_track(
        FakeHttpClient(lambda _: FakeResponse(200, content=DATA)),
        _track("primary.invalid"),
        part,
        None,
    )
    assert part.read_bytes() == DATA


@pytest.mark.asyncio
async def test_short_eof_resumes_and_oversized_body_restarts(tmp_path: Path) -> None:
    short_part = tmp_path / "short.part"
    short_requests = 0

    def short_handler(request: FakeRequest) -> FakeResponse:
        nonlocal short_requests
        short_requests += 1
        if short_requests == 1:
            return FakeResponse(200, content=b"abc", headers={"Content-Length": "6"})
        return FakeResponse(206, content=b"def", headers={"Content-Range": "bytes 3-5/6"})

    await transfer_track(FakeHttpClient(short_handler), _track("primary.invalid"), short_part, None)
    assert short_part.read_bytes() == DATA

    large_part = tmp_path / "large.part"
    large_requests: list[FakeRequest] = []

    def large_handler(request: FakeRequest) -> FakeResponse:
        large_requests.append(request)
        if len(large_requests) == 1:
            return FakeResponse(200, content=DATA, headers={"Content-Length": "3"})
        return FakeResponse(200, content=b"xyz", headers={"Content-Length": "3"})

    await transfer_track(FakeHttpClient(large_handler), _track("primary.invalid"), large_part, None)
    assert large_part.read_bytes() == b"xyz"
    assert "range" not in large_requests[-1].headers


@pytest.mark.asyncio
async def test_remote_length_change_discards_old_part(tmp_path: Path) -> None:
    part = tmp_path / "track.part"
    part.write_bytes(b"abc")
    requests: list[FakeRequest] = []

    def handler(request: FakeRequest) -> FakeResponse:
        requests.append(request)
        if len(requests) == 1:
            return FakeResponse(206, content=b"a", headers={"Content-Range": "bytes 0-0/6"})
        if len(requests) == 2:
            return FakeResponse(206, content=b"defg", headers={"Content-Range": "bytes 3-6/7"})
        return FakeResponse(200, content=b"1234567", headers={"Content-Length": "7"})

    await transfer_track(
        FakeHttpClient(handler),
        _track("primary.invalid", "backup.invalid"),
        part,
        None,
    )

    assert part.read_bytes() == b"1234567"
    assert "range" not in requests[-1].headers


@pytest.mark.asyncio
async def test_cancellation_closes_response_and_keeps_partial_bytes(tmp_path: Path) -> None:
    part = tmp_path / "track.part"
    never = asyncio.Event()
    response = FakeResponse(
        200,
        chunks=(b"abc",),
        headers={"Content-Length": "6"},
        wait_after_chunks=never,
    )
    written = asyncio.Event()

    def progress(kind: MediaKind, done: int, total: int | None) -> None:
        del kind, total
        if done == 3:
            written.set()

    task = asyncio.create_task(
        transfer_track(
            FakeHttpClient(lambda _: response),
            _track("primary.invalid"),
            part,
            progress,
        )
    )
    await written.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert response.closed is True
    assert part.read_bytes() == b"abc"
