"""Offline examples for input parsing, WBI, and DASH extraction."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

import httpx
import pytest

from velafetch.domain.models import CodecFamily, DynamicRange, MediaKind
from velafetch.errors import ExtractionError, UnsupportedFeatureError
from velafetch.extractors import BilibiliExtractor, parse_bilibili_input, sign_wbi_query

FIXTURES = Path(__file__).parent / "fixtures" / "bilibili"


def _fixture(name: str) -> dict[str, object]:
    value = cast("object", json.loads((FIXTURES / name).read_text(encoding="utf-8")))
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    ("source", "normalized"),
    [
        ("BV1VF4111111", "BV1VF4111111"),
        ("av00042", "av42"),
        (
            "http://www.bilibili.com/video/BV1VF4111111?p=1&spm_id_from=test#part",
            "https://www.bilibili.com/video/BV1VF4111111",
        ),
    ],
)
def test_supported_inputs_are_normalized(source: str, normalized: str) -> None:
    assert parse_bilibili_input(source).normalized_input == normalized


@pytest.mark.parametrize(
    "source",
    [
        "",
        "BVshort",
        "https://b23.tv/BV1VF4111111",
        "https://www.bilibili.com.evil.invalid/video/BV1VF4111111",
        "https://www.bilibili.com/bangumi/play/ss1",
    ],
)
def test_unsupported_inputs_raise_a_readable_error(source: str) -> None:
    with pytest.raises(UnsupportedFeatureError):
        parse_bilibili_input(source)


@pytest.mark.asyncio
async def test_info_only_requests_metadata() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json=_fixture("view_single.json"))

    async with _client(handler) as client:
        item = await BilibiliExtractor(client).get_info("av100000001")

    assert paths == ["/x/web-interface/view"]
    assert item.ref.canonical_id == "BV1VF4111111"
    assert item.pages[0].formats == ()


@pytest.mark.asyncio
async def test_formats_projects_video_audio_and_hides_sources() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/view"):
            payload = _fixture("view_single.json")
        elif request.url.path.endswith("/nav"):
            payload = _fixture("nav_wbi.json")
        else:
            payload = _fixture("play_dash.json")
        return httpx.Response(200, json=payload)

    async with _client(handler) as client:
        item = await BilibiliExtractor(client, clock=lambda: 1_700_000_000).get_formats(
            "BV1VF4111111"
        )

    tracks = item.pages[0].formats
    assert tracks[0].kind is MediaKind.VIDEO
    assert {track.codec_family for track in tracks} >= {
        CodecFamily.AVC,
        CodecFamily.HEVC,
        CodecFamily.AV1,
        CodecFamily.AAC,
    }
    avc = next(track for track in tracks if track.codec_family is CodecFamily.AVC)
    assert len(avc.source.urls) == 2
    assert avc.source.required_headers["Referer"].endswith("BV1VF4111111")
    assert "media.invalid" not in item.model_dump_json()
    assert any(track.dynamic_range is DynamicRange.HDR for track in tracks)


def test_wbi_signing_is_deterministic() -> None:
    first = sign_wbi_query({"b": "two", "a": "one"}, "0123456789abcdef" * 2, 1_700_000_000)
    second = sign_wbi_query({"a": "one", "b": "two"}, "0123456789abcdef" * 2, 1_700_000_000)

    assert first == second
    assert "wts=1700000000" in first
    assert "w_rid=" in first


@pytest.mark.asyncio
async def test_api_and_json_errors_stay_understandable() -> None:
    responses = iter(
        [
            httpx.Response(200, content=b"not-json"),
            httpx.Response(200, json={"code": -404, "message": "not found"}),
        ]
    )

    async with _client(lambda _: next(responses)) as client:
        extractor = BilibiliExtractor(client)
        with pytest.raises(ExtractionError, match="invalid JSON"):
            await extractor.get_info("BV1VF4111111")
        with pytest.raises(ExtractionError, match="API error -404"):
            await extractor.get_info("BV1VF4111111")
