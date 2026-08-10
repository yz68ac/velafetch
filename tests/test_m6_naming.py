"""Deterministic M6 filename and template tests."""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest

from velafetch.application.naming import (
    TemplateContext,
    batch_output_root,
    default_stem,
    render_template,
    safe_filename,
    sidecar_path,
    target_paths,
    unit_stem,
)
from velafetch.domain.models import (
    CodecFamily,
    DynamicRange,
    MediaFormat,
    MediaItem,
    MediaKind,
    MediaPage,
    MediaRef,
    MediaResourceKind,
    MediaSource,
    OutputMode,
    Site,
)
from velafetch.errors import DownloadError
from velafetch.extractors import ResolvedMedia
from velafetch.selection import TrackSelection


def _unit(
    kind: MediaResourceKind,
    *,
    item_index: int = 1,
    page_index: int = 1,
    page_count: int = 1,
) -> ResolvedMedia:
    item_id = "ep8100002" if kind is MediaResourceKind.BANGUMI_SEASON else "BV1NM4111111"
    item_title = "Episode Two" if kind is MediaResourceKind.BANGUMI_SEASON else "Video Title"
    pages = tuple(
        MediaPage(
            index=index,
            page_id=str(9000 + index),
            title=f"Part {index}",
            duration_ms=1000,
            canonical_url=f"https://www.bilibili.com/video/{item_id}?p={index}",
        )
        for index in range(1, page_count + 1)
    )
    item = MediaItem(
        ref=MediaRef(
            site=Site.BILIBILI,
            kind=kind,
            canonical_id=item_id,
            canonical_url=f"https://www.bilibili.com/video/{item_id}",
            normalized_input=item_id,
            avid=1,
        ),
        title=item_title,
        duration_ms=page_count * 1000,
        pages=pages,
    )
    source_id = "BV1NM4111111" if kind is MediaResourceKind.VIDEO else "source-7"
    source_title = "Video Title" if kind is MediaResourceKind.VIDEO else "Source Title"
    return ResolvedMedia(
        resource_kind=kind,
        source_id=source_id,
        source_title=source_title,
        source_url="https://www.bilibili.com/video/BV1NM4111111",
        item_index=item_index,
        item_count=3,
        item=item,
        page_index=page_index,
    )


def _track(kind: MediaKind) -> MediaFormat:
    if kind is MediaKind.VIDEO:
        return MediaFormat(
            format_id="video",
            kind=kind,
            container="mp4",
            codec="avc1.640028",
            codec_family=CodecFamily.AVC,
            bitrate=1,
            source=MediaSource(urls=("https://media.invalid/video",)),
            width=1920,
            height=1080,
            dynamic_range=DynamicRange.SDR,
        )
    return MediaFormat(
        format_id="audio",
        kind=kind,
        container="m4a",
        codec="mp4a.40.2",
        codec_family=CodecFamily.AAC,
        bitrate=1,
        source=MediaSource(urls=("https://media.invalid/audio",)),
    )


def test_default_names_distinguish_single_batch_item_and_page_context() -> None:
    video = _unit(MediaResourceKind.VIDEO, page_index=2, page_count=2)
    episode = _unit(MediaResourceKind.BANGUMI_SEASON, item_index=2)
    collection = _unit(
        MediaResourceKind.UGC_SEASON,
        item_index=2,
        page_index=2,
        page_count=2,
    )

    assert default_stem(video, batch=False) == "Video Title - P02 - Part 2"
    assert default_stem(video, batch=True) == "P02 - Part 2"
    assert default_stem(episode, batch=False) == "Source Title - E02 - Episode Two"
    assert default_stem(episode, batch=True) == "E02 - Episode Two"
    assert default_stem(collection, batch=False) == (
        "Source Title - 02 - Video Title - P02 - Part 2"
    )
    assert default_stem(collection, batch=True) == "02 - Video Title - P02 - Part 2"
    assert batch_output_root(Path("out"), collection) == Path("out") / "Source Title"


def test_templates_allow_known_fields_and_integer_padding_only() -> None:
    unit = _unit(MediaResourceKind.UGC_SERIES, item_index=3, page_index=2, page_count=2)

    assert (
        unit_stem(
            unit,
            batch=True,
            template="{item:02d}-{page:02d}-{id}-{part_title}",
        )
        == "03-02-BV1NM4111111-Part 2"
    )

    context = TemplateContext("Source", "Title", "Part", "BV1NM4111111", 1, 1)
    for template in ("../{title}", "folder\\{title}", "{unknown}", "{title!r}", "{title:02d}"):
        with pytest.raises(DownloadError):
            render_template(template, context)


def test_unicode_reserved_names_and_long_components_are_cross_platform_safe() -> None:
    decomposed = "Cafe\N{COMBINING ACUTE ACCENT}"
    normalized = safe_filename(decomposed, "fallback")
    reserved = safe_filename("CON.txt", "fallback")
    first = safe_filename("航" * 300, "fallback")
    second = safe_filename("航" * 300, "fallback")

    assert normalized == unicodedata.normalize("NFC", decomposed)
    assert reserved == "_CON.txt"
    assert first == second and "-" in first
    assert len(first.encode("utf-8")) <= 240
    assert len(first.encode("utf-16-le")) // 2 <= 240


def test_mode_suffixes_and_sidecars_share_the_fitted_stem() -> None:
    video, audio = _track(MediaKind.VIDEO), _track(MediaKind.AUDIO)
    selection = TrackSelection(video, audio)
    stem = "V" * 300

    muxed = target_paths(Path("out"), stem, selection, OutputMode.MUXED)
    video_only = target_paths(Path("out"), stem, selection, OutputMode.VIDEO_ONLY)
    audio_only = target_paths(Path("out"), stem, selection, OutputMode.AUDIO_ONLY)
    no_mux = target_paths(Path("out"), stem, selection, OutputMode.NO_MUX)
    cover = sidecar_path(Path("out"), stem, ".cover.jpg")

    assert muxed[0].suffix == ".mp4"
    assert video_only[0].name.endswith(".video.mp4")
    assert audio_only[0].name.endswith(".audio.m4a")
    assert [path.name.rsplit(".", 2)[-2:] for path in no_mux] == [
        ["video", "mp4"],
        ["audio", "m4a"],
    ]
    for path in (*muxed, *video_only, *audio_only, *no_mux, cover):
        assert len(path.name.encode("utf-8")) <= 240
        assert len(path.name.encode("utf-16-le")) // 2 <= 240
