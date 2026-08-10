"""Sequential M6 batch orchestration and sidecar lifecycle tests."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs

import pytest

import velafetch.application.assets as asset_module
import velafetch.application.transfer as transfer_module
from tests.http_fakes import FakeHttpClient, FakeRequest, FakeResponse
from velafetch.application import DownloadService, DownloadStatus
from velafetch.domain.models import OutputMode, SelectionPolicy
from velafetch.errors import DownloadError

FIXTURES = Path(__file__).parent / "fixtures" / "bilibili"
VIDEO_BYTES = b"m6-synthetic-video"


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transfer_module, "_RETRY_DELAY_SECONDS", 0)
    monkeypatch.setattr(asset_module, "_ASSET_RETRY_DELAY", 0)


def _fixture(name: str) -> dict[str, object]:
    value = cast("object", json.loads((FIXTURES / name).read_text(encoding="utf-8")))
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def _service(handler: Callable[[FakeRequest], FakeResponse]) -> DownloadService:
    def factory(
        timeout: float,
        proxy: str | None,
        cookies: Mapping[str, str] | None,
    ) -> FakeHttpClient:
        del timeout, proxy, cookies
        return FakeHttpClient(handler)

    return DownloadService(factory)


def _media_response(content: bytes = VIDEO_BYTES, status: int = 200) -> FakeResponse:
    return FakeResponse(status, content=content, headers={"Content-Length": str(len(content))})


@pytest.mark.asyncio
async def test_all_multi_page_downloads_sequentially_into_a_source_directory(
    tmp_path: Path,
) -> None:
    requests: list[FakeRequest] = []

    def handler(request: FakeRequest) -> FakeResponse:
        requests.append(request)
        if request.url.path.endswith("/view"):
            return FakeResponse(200, payload=_fixture("view_multi.json"))
        if request.url.path.endswith("/nav"):
            return FakeResponse(200, payload=_fixture("nav_wbi.json"))
        if request.url.path.endswith("/playurl"):
            return FakeResponse(200, payload=_fixture("play_dash.json"))
        return _media_response()

    result = await _service(handler).download(
        "BV1MP4111111",
        output_dir=tmp_path,
        policy=SelectionPolicy(output_mode=OutputMode.VIDEO_ONLY),
        all_items=True,
        cover=False,
        subtitles="off",
    )

    assert result.ok and not result.aborted
    assert [item.status for item in result.items] == [DownloadStatus.SAVED, DownloadStatus.SAVED]
    assert [path.name for path in result.output_paths] == [
        "P01 - Launch.video.mp4",
        "P02 - Orbit.video.mp4",
    ]
    assert {path.parent for path in result.output_paths} == {tmp_path / "Vela Multi Flight"}
    play_cids = [
        parse_qs(request.url.query)["cid"][0]
        for request in requests
        if request.url.path.endswith("/playurl")
    ]
    assert play_cids == ["900000010", "900000011"]
    assert sum(request.url.hostname == "video.media.invalid" for request in requests) == 2


@pytest.mark.asyncio
async def test_rerun_skips_media_but_fills_missing_default_sidecars(tmp_path: Path) -> None:
    media_requests: list[FakeRequest] = []

    def handler(request: FakeRequest) -> FakeResponse:
        if request.url.path.endswith("/view"):
            payload = copy.deepcopy(_fixture("view_single.json"))
            cast("dict[str, object]", payload["data"])["pic"] = (
                "https://assets.invalid/video-cover.jpg?token=synthetic"
            )
            return FakeResponse(200, payload=payload)
        if request.url.path.endswith("/nav"):
            return FakeResponse(200, payload=_fixture("nav_wbi.json"))
        if request.url.path.endswith("/playurl"):
            return FakeResponse(200, payload=_fixture("play_dash.json"))
        if request.url.path.endswith("/player/wbi/v2"):
            return FakeResponse(200, payload=_fixture("player_assets.json"))
        if request.url.hostname == "video.media.invalid":
            media_requests.append(request)
            return _media_response()
        if request.url.hostname == "assets.invalid":
            return FakeResponse(200, content=b"image", headers={"Content-Type": "image/jpeg"})
        if request.url.hostname == "subtitle.invalid":
            return FakeResponse(200, content=(FIXTURES / "subtitle_body.json").read_bytes())
        if request.url.path.endswith("/list.so"):
            return FakeResponse(200, content=b"<i><d>synthetic</d></i>")
        raise AssertionError(request.url.geturl())

    service = _service(handler)
    first = await service.download(
        "BV1VF4111111",
        output_dir=tmp_path,
        policy=SelectionPolicy(output_mode=OutputMode.VIDEO_ONLY),
        cover=False,
        subtitles="off",
    )
    media_requests.clear()
    second = await service.download(
        "BV1VF4111111",
        output_dir=tmp_path,
        policy=SelectionPolicy(output_mode=OutputMode.VIDEO_ONLY),
        subtitles="zh-cn",
        danmaku=True,
    )

    assert first.ok and second.ok
    assert media_requests == []
    assert second.items[0].status is DownloadStatus.SAVED
    assert {path.name for path in second.output_paths} == {
        "Vela Synthetic Flight.video.mp4",
        "Vela Synthetic Flight.cover.jpg",
        "Vela Synthetic Flight.zh-CN.srt",
        "Vela Synthetic Flight.danmaku.xml",
    }


@pytest.mark.asyncio
async def test_subtitle_failure_marks_one_item_partial_and_batch_continues(
    tmp_path: Path,
) -> None:
    media_pages: list[str] = []

    def handler(request: FakeRequest) -> FakeResponse:
        query = parse_qs(request.url.query)
        if request.url.path.endswith("/view"):
            return FakeResponse(200, payload=_fixture("view_multi.json"))
        if request.url.path.endswith("/nav"):
            return FakeResponse(200, payload=_fixture("nav_wbi.json"))
        if request.url.path.endswith("/playurl"):
            media_pages.append(query["cid"][0])
            return FakeResponse(200, payload=_fixture("play_dash.json"))
        if request.url.path.endswith("/player/wbi/v2"):
            cid = query["cid"][0]
            return FakeResponse(
                200,
                payload={
                    "code": 0,
                    "data": {
                        "subtitle": {
                            "subtitles": [
                                {
                                    "id": cid,
                                    "lan": "en-US",
                                    "lan_doc": "English",
                                    "subtitle_url": f"https://subtitle.invalid/{cid}.json",
                                }
                            ]
                        }
                    },
                },
            )
        if request.url.hostname == "video.media.invalid":
            return _media_response()
        if request.url.hostname == "subtitle.invalid":
            content = (
                b"not-json"
                if request.url.path.startswith("/900000010")
                else (FIXTURES / "subtitle_body.json").read_bytes()
            )
            return FakeResponse(200, content=content)
        raise AssertionError(request.url.geturl())

    result = await _service(handler).download(
        "BV1MP4111111",
        output_dir=tmp_path,
        policy=SelectionPolicy(output_mode=OutputMode.VIDEO_ONLY),
        all_items=True,
        cover=False,
        subtitles="all",
    )

    assert result.ok is False and result.aborted is False
    assert [item.status for item in result.items] == [
        DownloadStatus.PARTIAL,
        DownloadStatus.SAVED,
    ]
    assert media_pages == ["900000010", "900000011"]


@pytest.mark.asyncio
async def test_media_failure_aborts_batch_and_preserves_safe_result(tmp_path: Path) -> None:
    play_cids: list[str] = []

    def handler(request: FakeRequest) -> FakeResponse:
        if request.url.path.endswith("/view"):
            return FakeResponse(200, payload=_fixture("view_multi.json"))
        if request.url.path.endswith("/nav"):
            return FakeResponse(200, payload=_fixture("nav_wbi.json"))
        if request.url.path.endswith("/playurl"):
            play_cids.append(parse_qs(request.url.query)["cid"][0])
            return FakeResponse(200, payload=_fixture("play_dash.json"))
        return _media_response(status=503)

    result = await _service(handler).download(
        "BV1MP4111111",
        output_dir=tmp_path,
        policy=SelectionPolicy(output_mode=OutputMode.VIDEO_ONLY),
        all_items=True,
        cover=False,
        subtitles="off",
    )

    assert result.aborted is True and result.ok is False
    assert len(result.items) == 1
    assert result.items[0].status is DownloadStatus.FAILED
    assert result.items[0].error is not None
    assert "media.invalid" not in result.items[0].error
    assert play_cids == ["900000010"]


@pytest.mark.asyncio
async def test_duplicate_template_targets_are_rejected_before_playback(tmp_path: Path) -> None:
    paths: list[str] = []

    def handler(request: FakeRequest) -> FakeResponse:
        paths.append(request.url.path)
        return FakeResponse(200, payload=_fixture("view_multi.json"))

    with pytest.raises(DownloadError, match="duplicate"):
        await _service(handler).download(
            "BV1MP4111111",
            output_dir=tmp_path,
            policy=SelectionPolicy(output_mode=OutputMode.VIDEO_ONLY),
            all_items=True,
            cover=False,
            subtitles="off",
            output_template="same-name",
        )

    assert paths == ["/x/web-interface/view"]
