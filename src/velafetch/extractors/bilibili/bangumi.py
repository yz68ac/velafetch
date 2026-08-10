"""Projection of public Bangumi seasons and episodes."""

from __future__ import annotations

from velafetch.domain.models import (
    MediaCollection,
    MediaCollectionEntry,
    MediaItem,
    MediaPage,
    MediaRef,
    MediaResourceKind,
    Site,
)
from velafetch.errors import ExtractionError, SelectionError
from velafetch.extractors.bilibili.input import is_bvid
from velafetch.extractors.bilibili.payload import (
    JsonMapping,
    mapping,
    required_int,
    required_string,
    sequence,
)
from velafetch.extractors.bilibili.resources import choose_index, public_source


def project_bangumi_collection(
    result: JsonMapping,
    *,
    normalized_input: str,
    requested_item: int | None,
    requested_episode_id: int | None,
) -> MediaCollection:
    season_id = required_int(result, "season_id", stage="season", minimum=1)
    title_value = result.get("season_title", result.get("title"))
    if not isinstance(title_value, str) or not title_value.strip():
        raise ExtractionError("Bilibili omitted the Bangumi season title.")
    title = title_value.strip()
    canonical_url = f"https://www.bilibili.com/bangumi/play/ss{season_id}"
    cover_value = result.get("cover")
    cover = (
        public_source(cover_value, referer=canonical_url)
        if isinstance(cover_value, str) and cover_value
        else None
    )
    episode_values = sequence(result.get("episodes"), stage="season", field="episodes")
    if not episode_values:
        raise ExtractionError("The Bangumi season has no public episodes.")

    entries: list[MediaCollectionEntry] = []
    selected_from_episode: int | None = None
    seen_ids: set[int] = set()
    for index, value in enumerate(episode_values, start=1):
        episode = mapping(value, stage="season", field=f"episodes[{index - 1}]")
        episode_id = required_int(episode, "id", stage="season", minimum=1)
        if episode_id in seen_ids:
            raise ExtractionError("The Bangumi season contains duplicate episode IDs.")
        seen_ids.add(episode_id)
        avid = required_int(episode, "aid", stage="season", minimum=1)
        cid = required_int(episode, "cid", stage="season", minimum=1)
        bvid = required_string(episode, "bvid", stage="season")
        if not is_bvid(bvid):
            raise ExtractionError("A Bangumi episode has an invalid BV identifier.")
        short_title = required_string(episode, "title", stage="season").strip()
        long_value = episode.get("long_title")
        long_title = long_value.strip() if isinstance(long_value, str) else ""
        entry_title = " - ".join(part for part in (short_title, long_title) if part) or title
        duration = required_int(episode, "duration", stage="season")
        episode_url = f"https://www.bilibili.com/bangumi/play/ep{episode_id}"
        episode_cover_value = episode.get("cover")
        episode_cover = (
            public_source(episode_cover_value, referer=episode_url)
            if isinstance(episode_cover_value, str) and episode_cover_value
            else cover
        )
        entries.append(
            MediaCollectionEntry(
                index=index,
                entry_id=f"ep{episode_id}",
                canonical_url=episode_url,
                title=entry_title,
                duration_ms=duration,
                avid=avid,
                bvid=bvid,
                cid=cid,
                episode_id=episode_id,
                cover=episode_cover,
            )
        )
        if requested_episode_id == episode_id:
            selected_from_episode = index

    if requested_episode_id is not None and selected_from_episode is None:
        raise SelectionError("The requested episode is not part of the returned season.")
    selected_index = choose_index(
        requested_item,
        selected_from_episode,
        len(entries),
        label="item",
    )
    return MediaCollection(
        ref=MediaRef(
            site=Site.BILIBILI,
            kind=MediaResourceKind.BANGUMI_SEASON,
            canonical_id=f"ss{season_id}",
            canonical_url=canonical_url,
            normalized_input=normalized_input,
        ),
        title=title,
        entries=tuple(entries),
        selected_index=selected_index,
        cover=cover,
    )


def bangumi_entry_item(collection: MediaCollection, entry: MediaCollectionEntry) -> MediaItem:
    if entry.avid is None or entry.bvid is None or entry.cid is None or entry.episode_id is None:
        raise ExtractionError("The Bangumi episode identity is incomplete.")
    page = MediaPage(
        index=1,
        page_id=str(entry.cid),
        title=entry.title,
        duration_ms=entry.duration_ms,
        avid=entry.avid,
        bvid=entry.bvid,
        episode_id=entry.episode_id,
        canonical_url=entry.canonical_url,
        cover=entry.cover,
    )
    return MediaItem(
        ref=MediaRef(
            site=Site.BILIBILI,
            kind=MediaResourceKind.BANGUMI_SEASON,
            canonical_id=entry.entry_id,
            canonical_url=entry.canonical_url,
            normalized_input=collection.ref.normalized_input,
            avid=entry.avid,
        ),
        title=entry.title,
        duration_ms=entry.duration_ms,
        pages=(page,),
        cover=entry.cover,
    )
