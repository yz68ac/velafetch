"""Cover, subtitle, and danmaku sidecar tests with synthetic responses."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

import velafetch.application.assets as asset_module
from tests.http_fakes import FakeHttpClient, FakeRequest, FakeResponse
from velafetch.application.assets import (
    SubtitleOutputFormat,
    download_cover,
    download_danmaku,
    download_subtitles,
    parse_subtitle_selection,
)
from velafetch.domain.models import (
    MediaItem,
    MediaPage,
    MediaRef,
    MediaResourceKind,
    MediaSource,
    Site,
)
from velafetch.extractors import ResolvedMedia, SubtitleTrack
from velafetch.extractors.bilibili.assets import project_assets

FIXTURES = Path(__file__).parent / "fixtures" / "bilibili"


def _fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _fixture(name: str) -> dict[str, object]:
    value = cast("object", json.loads(_fixture_bytes(name)))
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def _unit(*, cover: bool = True) -> ResolvedMedia:
    canonical_url = "https://www.bilibili.com/video/BV1AS4111111"
    cover_source = (
        MediaSource(
            urls=("https://assets.invalid/cover.webp?token=synthetic",),
            required_headers={"Referer": canonical_url},
        )
        if cover
        else None
    )
    page = MediaPage(
        index=1,
        page_id="900000099",
        title="Asset Page",
        duration_ms=1000,
        avid=140000001,
        bvid="BV1AS4111111",
        canonical_url=canonical_url,
        cover=cover_source,
    )
    item = MediaItem(
        ref=MediaRef(
            site=Site.BILIBILI,
            kind=MediaResourceKind.VIDEO,
            canonical_id="BV1AS4111111",
            canonical_url=canonical_url,
            normalized_input="BV1AS4111111",
            avid=140000001,
        ),
        title="Asset Video",
        duration_ms=1000,
        pages=(page,),
        cover=cover_source,
    )
    return ResolvedMedia(
        MediaResourceKind.VIDEO,
        "BV1AS4111111",
        "Asset Video",
        canonical_url,
        1,
        1,
        item,
        1,
    )


def _subtitle(track_id: str, language: str, filename: str) -> SubtitleTrack:
    return SubtitleTrack(
        track_id,
        language,
        language,
        MediaSource(urls=(f"https://subtitle.invalid/{filename}?token=synthetic",)),
    )


def test_player_assets_are_sorted_and_private_urls_do_not_serialize() -> None:
    assets = project_assets(_unit(), _fixture("player_assets.json")["data"])  # type: ignore[arg-type]

    assert [track.language for track in assets.subtitles] == ["en-US", "zh-CN"]
    assert assets.cover is not None
    assert assets.danmaku.urls[0].endswith("oid=900000099")
    assert "subtitle.invalid" not in repr(assets.subtitles[0])


def test_subtitle_selection_parses_all_off_and_case_insensitive_languages() -> None:
    assert parse_subtitle_selection("all").all_languages is True
    assert parse_subtitle_selection("OFF").enabled is False
    selected = parse_subtitle_selection(" ZH-cn, en-US,zh-CN ")
    assert selected.languages == frozenset({"zh-cn", "en-us"})


@pytest.mark.asyncio
async def test_srt_is_stably_sorted_and_json_preserves_the_response_structure(
    tmp_path: Path,
) -> None:
    requests: list[FakeRequest] = []

    def handler(request: FakeRequest) -> FakeResponse:
        requests.append(request)
        return FakeResponse(
            200,
            content=_fixture_bytes("subtitle_body.json"),
            headers={"Content-Type": "application/json"},
        )

    tracks = (
        _subtitle("1", "zh-CN", "zh.json"),
        _subtitle("2", "en-US", "en.json"),
    )
    async with FakeHttpClient(handler) as client:
        srt = await download_subtitles(
            client,
            tracks,
            parse_subtitle_selection("zh-cn"),
            SubtitleOutputFormat.SRT,
            tmp_path,
            "Asset Video",
            overwrite=False,
        )
        raw_json = await download_subtitles(
            client,
            tracks,
            parse_subtitle_selection("en-us"),
            SubtitleOutputFormat.JSON,
            tmp_path,
            "Asset Video",
            overwrite=False,
        )

    assert not srt.errors and not raw_json.errors
    text = srt.paths[0].read_text(encoding="utf-8-sig")
    assert text.index("First cue") < text.index("Second cue")
    assert "00:00:00,250 --> 00:00:01,750" in text
    assert (
        json.loads(raw_json.paths[0].read_text(encoding="utf-8"))["body"][0]["content"]
        == "Second cue"
    )
    assert all(request.headers["accept-encoding"] == "identity" for request in requests)


@pytest.mark.asyncio
async def test_missing_explicit_language_is_partial_but_no_subtitles_for_all_is_normal(
    tmp_path: Path,
) -> None:
    async with FakeHttpClient(lambda _: pytest.fail("network should not be used")) as client:
        missing = await download_subtitles(
            client,
            (),
            parse_subtitle_selection("ja-JP"),
            SubtitleOutputFormat.SRT,
            tmp_path,
            "Asset Video",
            overwrite=False,
        )
        all_missing = await download_subtitles(
            client,
            (),
            parse_subtitle_selection("all"),
            SubtitleOutputFormat.SRT,
            tmp_path,
            "Asset Video",
            overwrite=False,
        )

    assert "ja-jp" in missing.errors[0]
    assert all_missing.errors == ()


@pytest.mark.asyncio
async def test_cover_retry_after_is_bounded_and_failures_are_warnings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    returned = [
        FakeResponse(429, headers={"Retry-After": "99"}),
        FakeResponse(200, content=b"synthetic-image", headers={"Content-Type": "image/webp"}),
    ]
    responses = iter(returned)
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        assert returned[0].closed is True
        delays.append(delay)

    monkeypatch.setattr(asset_module.asyncio, "sleep", sleep)
    async with FakeHttpClient(lambda _: next(responses)) as client:
        result = await download_cover(
            client,
            _unit(),
            tmp_path,
            "Asset Video",
            overwrite=False,
        )

    assert result.errors == () and result.saved == 1
    assert result.paths[0].name == "Asset Video.cover.webp"
    assert delays == [30.0]

    async with FakeHttpClient(
        lambda _: FakeResponse(200, content=b"html", headers={"Content-Type": "text/html"})
    ) as client:
        warning = await download_cover(
            client,
            _unit(),
            tmp_path,
            "Other Video",
            overwrite=False,
        )
    assert warning.errors == ()
    assert warning.warnings == ("The cover response is not an image.",)


@pytest.mark.asyncio
async def test_danmaku_accepts_public_xml_and_reports_invalid_content(
    tmp_path: Path,
) -> None:
    async with FakeHttpClient(
        lambda _: FakeResponse(200, content=b'<?xml version="1.0"?><i><d>hello</d></i>')
    ) as client:
        saved = await download_danmaku(
            client,
            _unit(),
            tmp_path,
            "Asset Video",
            overwrite=False,
        )
    assert saved.saved == 1
    assert saved.paths[0].name == "Asset Video.danmaku.xml"

    async with FakeHttpClient(lambda _: FakeResponse(200, content=b"not xml")) as client:
        failed = await download_danmaku(
            client,
            _unit(),
            tmp_path,
            "Other Video",
            overwrite=False,
        )
    assert failed.errors == ("The danmaku response is not recognized XML.",)


@pytest.mark.asyncio
async def test_existing_sidecars_skip_without_request_and_publish_failures_are_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = tmp_path / "Asset Video.zh-CN.srt"
    existing.write_text("old", encoding="utf-8")
    track = _subtitle("1", "zh-CN", "zh.json")
    async with FakeHttpClient(lambda _: pytest.fail("network should not be used")) as client:
        skipped = await download_subtitles(
            client,
            (track,),
            parse_subtitle_selection("all"),
            SubtitleOutputFormat.SRT,
            tmp_path,
            "Asset Video",
            overwrite=False,
        )
    assert skipped.paths == (existing,)
    assert existing.read_text(encoding="utf-8") == "old"

    def fail_replace(source: Path, target: Path) -> None:
        del source, target
        raise OSError("synthetic private path")

    monkeypatch.setattr(asset_module.os, "replace", fail_replace)
    async with FakeHttpClient(
        lambda _: FakeResponse(200, content=_fixture_bytes("subtitle_body.json"))
    ) as client:
        failed = await download_subtitles(
            client,
            (_subtitle("2", "en-US", "en.json"),),
            parse_subtitle_selection("all"),
            SubtitleOutputFormat.SRT,
            tmp_path,
            "New Video",
            overwrite=False,
        )
    assert failed.errors == ("A sidecar file could not be published.",)
    assert not tuple(tmp_path.glob(".New Video*.part"))
