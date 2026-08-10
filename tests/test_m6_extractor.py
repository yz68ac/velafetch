"""Offline M6 resource enumeration and playback-unit tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs

import pytest

from tests.http_fakes import FakeHttpClient, FakeRequest, FakeResponse
from velafetch.domain.models import MediaCollection, MediaItem, MediaResourceKind
from velafetch.errors import ExtractionError, SelectionError, UnsupportedFeatureError
from velafetch.extractors import BilibiliExtractor, BilibiliInputKind, parse_bilibili_input

FIXTURES = Path(__file__).parent / "fixtures" / "bilibili"


def _fixture(name: str) -> dict[str, object]:
    value = cast("object", json.loads((FIXTURES / name).read_text(encoding="utf-8")))
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def _video_payload(bvid: str, avid: int, *, pages: int) -> dict[str, object]:
    payload = copy.deepcopy(_fixture("view_multi.json"))
    data = cast("dict[str, object]", payload["data"])
    data["bvid"] = bvid
    data["aid"] = avid
    data["title"] = f"Synthetic {bvid}"
    data["pages"] = cast("list[object]", data["pages"])[:pages]
    data["duration"] = 40 if pages == 1 else 100
    return payload


@pytest.mark.parametrize(
    ("source", "kind", "normalized"),
    [
        ("ss47200", BilibiliInputKind.BANGUMI_SEASON, "ss47200"),
        ("EP8100002", BilibiliInputKind.BANGUMI_EPISODE, "ep8100002"),
        (
            "http://www.bilibili.com/bangumi/play/ss47200?spm_id_from=test#ignored",
            BilibiliInputKind.BANGUMI_SEASON,
            "https://www.bilibili.com/bangumi/play/ss47200",
        ),
        (
            "https://space.bilibili.com/42/lists/7?type=season&spm_id_from=test",
            BilibiliInputKind.UGC_SEASON,
            "https://space.bilibili.com/42/lists/7?type=season",
        ),
        (
            "https://space.bilibili.com/42/lists/8?type=series",
            BilibiliInputKind.UGC_SERIES,
            "https://space.bilibili.com/42/lists/8?type=series",
        ),
    ],
)
def test_m6_inputs_are_strictly_normalized(
    source: str,
    kind: BilibiliInputKind,
    normalized: str,
) -> None:
    parsed = parse_bilibili_input(source)

    assert parsed.kind is kind
    assert parsed.normalized_input == normalized


@pytest.mark.parametrize(
    "source",
    [
        "https://www.bilibili.com/bangumi/play/md1",
        "https://www.bilibili.com/bangumi/play/ep1/extra",
        "https://space.bilibili.com/42/lists/7",
        "https://space.bilibili.com/42/lists/7?type=favorite",
        "https://space.bilibili.com:443/42/lists/7?type=season",
        "https://user:secret@space.bilibili.com/42/lists/7?type=series",
    ],
)
def test_m6_rejects_non_public_or_ambiguous_inputs(source: str) -> None:
    with pytest.raises(UnsupportedFeatureError):
        parse_bilibili_input(source)


@pytest.mark.asyncio
async def test_multi_page_video_selects_one_page_or_expands_all() -> None:
    requests: list[FakeRequest] = []

    def handler(request: FakeRequest) -> FakeResponse:
        requests.append(request)
        return FakeResponse(200, payload=_fixture("view_multi.json"))

    async with FakeHttpClient(handler) as client:
        extractor = BilibiliExtractor(client)
        info = await extractor.get_info("BV1MP4111111", page_index=2)
        units = await extractor.resolve_many("BV1MP4111111", all_items=True)

    assert isinstance(info, MediaItem)
    assert len(info.pages) == 2
    assert info.ref.page_index == 2
    assert [unit.page_index for unit in units] == [1, 2]
    assert [request.url.path for request in requests] == [
        "/x/web-interface/view",
        "/x/web-interface/view",
    ]


@pytest.mark.asyncio
async def test_bangumi_episode_selection_and_public_playback() -> None:
    requests: list[FakeRequest] = []

    def handler(request: FakeRequest) -> FakeResponse:
        requests.append(request)
        payload = (
            _fixture("bangumi_play_dash.json")
            if request.url.path.endswith("/playurl")
            else _fixture("season_public.json")
        )
        return FakeResponse(200, payload=payload)

    async with FakeHttpClient(handler) as client:
        extractor = BilibiliExtractor(client)
        selected = await extractor.get_info("ep8100002")
        overridden = await extractor.get_info("ep8100002", item_index=1)
        resolved = await extractor.get_formats("ss47200", item_index=2)
        all_units = await extractor.resolve_many("ep8100002", all_items=True)

    assert isinstance(selected, MediaCollection)
    assert selected.selected_index == 2
    assert isinstance(overridden, MediaCollection)
    assert overridden.selected_index == 1
    assert resolved.item.ref.canonical_id == "ep8100002"
    assert resolved.page.formats
    assert resolved.page.formats[0].source.required_headers["Referer"].endswith("ep8100002")
    assert [unit.item.ref.canonical_id for unit in all_units] == ["ep8100001", "ep8100002"]
    assert not any(request.url.path.endswith("/nav") for request in requests)


@pytest.mark.asyncio
async def test_ugc_season_paginates_deduplicates_and_recursively_expands_pages() -> None:
    requests: list[FakeRequest] = []

    def handler(request: FakeRequest) -> FakeResponse:
        requests.append(request)
        query = parse_qs(request.url.query)
        if request.url.path.endswith("/seasons_archives_list"):
            page = query["page_num"][0]
            return FakeResponse(200, payload=_fixture(f"ugc_season_page_{page}.json"))
        if request.url.path.endswith("/view"):
            bvid = query["bvid"][0]
            if bvid == "BV1US4111111":
                return FakeResponse(200, payload=_video_payload(bvid, 120000001, pages=2))
            return FakeResponse(200, payload=_video_payload(bvid, 120000002, pages=1))
        raise AssertionError(request.url.geturl())

    source = "https://space.bilibili.com/546195/lists/1903592?type=season"
    async with FakeHttpClient(handler) as client:
        extractor = BilibiliExtractor(client)
        collection = await extractor.get_info(source, item_index=2)
        units = await extractor.resolve_many(source, all_items=True)

    assert isinstance(collection, MediaCollection)
    assert collection.ref.kind is MediaResourceKind.UGC_SEASON
    assert [entry.entry_id for entry in collection.entries] == ["BV1US4111111", "BV1US4111112"]
    assert collection.selected_index == 2
    assert [(unit.item_index, unit.page_index) for unit in units] == [(1, 1), (1, 2), (2, 1)]
    list_pages = [
        parse_qs(request.url.query)["page_num"][0]
        for request in requests
        if request.url.path.endswith("/seasons_archives_list")
    ]
    assert list_pages == ["1", "2", "1", "2"]


@pytest.mark.asyncio
async def test_ugc_series_uses_metadata_and_archive_endpoints() -> None:
    paths: list[str] = []

    def handler(request: FakeRequest) -> FakeResponse:
        paths.append(request.url.path)
        payload = (
            _fixture("ugc_series_meta.json")
            if request.url.path.endswith("/series")
            else _fixture("ugc_series_archives.json")
        )
        return FakeResponse(200, payload=payload)

    source = "https://space.bilibili.com/42/lists/4684427?type=series"
    async with FakeHttpClient(handler) as client:
        resource = await BilibiliExtractor(client).get_info(source)

    assert isinstance(resource, MediaCollection)
    assert resource.ref.kind is MediaResourceKind.UGC_SERIES
    assert resource.entries[0].entry_id == "BV1SR4111111"
    assert paths == ["/x/series/series", "/x/series/archives"]


@pytest.mark.asyncio
async def test_selection_bounds_and_metadata_identity_are_checked() -> None:
    async with FakeHttpClient(
        lambda _: FakeResponse(200, payload=_fixture("view_multi.json"))
    ) as client:
        extractor = BilibiliExtractor(client)
        with pytest.raises(SelectionError, match="outside"):
            await extractor.get_info("BV1MP4111111", page_index=3)
        with pytest.raises(SelectionError, match="--item"):
            await extractor.get_info("BV1MP4111111", item_index=1)
        with pytest.raises(ExtractionError, match="identity"):
            await extractor.get_info("BV1WR4111111")


@pytest.mark.asyncio
async def test_api_retry_is_bounded_and_closes_each_response() -> None:
    responses = [
        FakeResponse(503, headers={"Retry-After": "0"}),
        FakeResponse(500),
        FakeResponse(200, payload=_fixture("view_multi.json")),
    ]
    returned = list(responses)
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    async with FakeHttpClient(lambda _: responses.pop(0)) as client:
        resource = await BilibiliExtractor(client, sleep=sleep).get_info("BV1MP4111111")

    assert isinstance(resource, MediaItem)
    assert delays == [0.0, 1.0]
    assert all(response.closed for response in returned)


@pytest.mark.asyncio
async def test_assets_use_signed_player_endpoint_and_share_the_wbi_key_cache() -> None:
    requests: list[FakeRequest] = []

    def handler(request: FakeRequest) -> FakeResponse:
        requests.append(request)
        if request.url.path.endswith("/view"):
            return FakeResponse(200, payload=_fixture("view_multi.json"))
        if request.url.path.endswith("/nav"):
            return FakeResponse(200, payload=_fixture("nav_wbi.json"))
        if request.url.path.endswith("/playurl"):
            return FakeResponse(200, payload=_fixture("play_dash.json"))
        if request.url.path.endswith("/player/wbi/v2"):
            return FakeResponse(200, payload=_fixture("player_assets.json"))
        raise AssertionError(request.url.geturl())

    async with FakeHttpClient(handler) as client:
        extractor = BilibiliExtractor(client, clock=lambda: 1_700_000_000)
        unit = await extractor.get_formats("BV1MP4111111")
        assets = await extractor.get_assets(unit)

    assert [track.language for track in assets.subtitles] == ["en-US", "zh-CN"]
    assert sum(request.url.path.endswith("/nav") for request in requests) == 1
    player_request = next(
        request for request in requests if request.url.path.endswith("/player/wbi/v2")
    )
    query = parse_qs(player_request.url.query)
    assert query["aid"] == ["100000010"]
    assert query["cid"] == ["900000010"]
    assert query["wts"] == ["1700000000"]
    assert len(query["w_rid"][0]) == 32
