"""Projection of public UGC season and series lists."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from urllib.parse import urlencode

from velafetch.domain.models import (
    MediaCollection,
    MediaCollectionEntry,
    MediaRef,
    MediaResourceKind,
    Site,
)
from velafetch.errors import ExtractionError
from velafetch.extractors.bilibili.input import BilibiliInput, BilibiliInputKind, is_bvid
from velafetch.extractors.bilibili.payload import (
    JsonMapping,
    api_data,
    mapping,
    required_int,
    required_string,
    sequence,
)
from velafetch.extractors.bilibili.resources import choose_index, public_source

JsonFetcher = Callable[..., Awaitable[JsonMapping]]

_UGC_SEASON_ENDPOINT = "https://api.bilibili.com/x/polymer/web-space/seasons_archives_list"
_UGC_SERIES_META_ENDPOINT = "https://api.bilibili.com/x/series/series"
_UGC_SERIES_ENDPOINT = "https://api.bilibili.com/x/series/archives"


async def fetch_ugc_collection(
    parsed: BilibiliInput,
    requested_item: int | None,
    fetch_json: JsonFetcher,
) -> MediaCollection:
    """Read every server page for one public UGC season or series."""

    if parsed.mid is None or parsed.collection_id is None:
        raise ExtractionError("The public collection identity is incomplete.")
    headers: Mapping[str, str] = {"Referer": parsed.normalized_input}
    archives: list[object] = []
    if parsed.kind is BilibiliInputKind.UGC_SEASON:
        meta: JsonMapping | None = None
        page_number = 1
        while True:
            query = urlencode(
                {
                    "mid": parsed.mid,
                    "season_id": parsed.collection_id,
                    "page_num": page_number,
                    "page_size": 30,
                    "sort_reverse": "false",
                }
            )
            data = api_data(
                await fetch_json(
                    f"{_UGC_SEASON_ENDPOINT}?{query}",
                    stage="collection",
                    headers=headers,
                ),
                stage="collection",
            )
            if meta is None:
                meta = mapping(data.get("meta"), stage="collection", field="meta")
            batch = sequence(data.get("archives"), stage="collection", field="archives")
            archives.extend(batch)
            total = _page_total(data)
            if len(archives) >= total:
                break
            if not batch:
                raise ExtractionError("The public collection pagination ended early.")
            page_number += 1
        assert meta is not None
    else:
        meta_data = api_data(
            await fetch_json(
                f"{_UGC_SERIES_META_ENDPOINT}?{urlencode({'series_id': parsed.collection_id})}",
                stage="collection",
                headers=headers,
            ),
            stage="collection",
        )
        meta = mapping(meta_data.get("meta"), stage="collection", field="meta")
        page_number = 1
        while True:
            query = urlencode(
                {
                    "mid": parsed.mid,
                    "series_id": parsed.collection_id,
                    "pn": page_number,
                    "ps": 30,
                    "only_normal": "true",
                    "sort": "desc",
                }
            )
            data = api_data(
                await fetch_json(
                    f"{_UGC_SERIES_ENDPOINT}?{query}",
                    stage="collection",
                    headers=headers,
                ),
                stage="collection",
            )
            batch = sequence(data.get("archives"), stage="collection", field="archives")
            archives.extend(batch)
            total = _page_total(data)
            if len(archives) >= total:
                break
            if not batch:
                raise ExtractionError("The public series pagination ended early.")
            page_number += 1
    return project_ugc_collection(
        parsed,
        meta=meta,
        archives=archives,
        requested_item=requested_item,
    )


def _page_total(data: JsonMapping) -> int:
    page = mapping(data.get("page"), stage="collection", field="page")
    return required_int(page, "total", stage="collection")


def project_ugc_collection(
    parsed: BilibiliInput,
    *,
    meta: JsonMapping,
    archives: list[object],
    requested_item: int | None,
) -> MediaCollection:
    if parsed.mid is None or parsed.collection_id is None:
        raise ExtractionError("The public collection identity is incomplete.")
    is_season = parsed.kind is BilibiliInputKind.UGC_SEASON
    title_field = "title" if is_season else "name"
    title = required_string(meta, title_field, stage="collection").strip()
    if not title:
        raise ExtractionError("The public collection has no title.")
    kind = MediaResourceKind.UGC_SEASON if is_season else MediaResourceKind.UGC_SERIES
    kind_token = "season" if is_season else "series"
    canonical_id = f"ugc-{kind_token}-{parsed.mid}-{parsed.collection_id}"
    canonical_url = (
        f"https://space.bilibili.com/{parsed.mid}/lists/{parsed.collection_id}?type={kind_token}"
    )
    cover_value = meta.get("cover")
    cover = (
        public_source(cover_value, referer=canonical_url)
        if isinstance(cover_value, str) and cover_value
        else None
    )

    entries: list[MediaCollectionEntry] = []
    seen: set[str] = set()
    for raw in archives:
        archive = mapping(raw, stage="collection", field="archive")
        bvid = required_string(archive, "bvid", stage="collection")
        if not is_bvid(bvid):
            raise ExtractionError("A public collection entry has an invalid BV identifier.")
        if bvid in seen:
            continue
        seen.add(bvid)
        avid = required_int(archive, "aid", stage="collection", minimum=1)
        entry_title = required_string(archive, "title", stage="collection").strip() or bvid
        duration = required_int(archive, "duration", stage="collection")
        entry_url = f"https://www.bilibili.com/video/{bvid}"
        entry_cover_value = archive.get("pic")
        entry_cover = (
            public_source(entry_cover_value, referer=entry_url)
            if isinstance(entry_cover_value, str) and entry_cover_value
            else cover
        )
        entries.append(
            MediaCollectionEntry(
                index=len(entries) + 1,
                entry_id=bvid,
                canonical_url=entry_url,
                title=entry_title,
                duration_ms=duration * 1000,
                avid=avid,
                bvid=bvid,
                cover=entry_cover,
            )
        )
    if not entries:
        raise ExtractionError("The public collection contains no videos.")
    selected_index = choose_index(requested_item, None, len(entries), label="item")
    return MediaCollection(
        ref=MediaRef(
            site=Site.BILIBILI,
            kind=kind,
            canonical_id=canonical_id,
            canonical_url=canonical_url,
            normalized_input=parsed.normalized_input,
        ),
        title=title,
        entries=tuple(entries),
        selected_index=selected_index,
        cover=cover,
    )
