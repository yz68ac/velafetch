"""Public cover, subtitle, and danmaku descriptors."""

from __future__ import annotations

from dataclasses import dataclass

from velafetch.domain.models import MediaSource
from velafetch.errors import ExtractionError
from velafetch.extractors.bilibili.payload import JsonMapping, mapping, sequence
from velafetch.extractors.bilibili.resources import ResolvedMedia, public_source


@dataclass(frozen=True, slots=True)
class SubtitleTrack:
    track_id: str
    language: str
    label: str
    source: MediaSource


@dataclass(frozen=True, slots=True)
class MediaAssets:
    cover: MediaSource | None
    subtitles: tuple[SubtitleTrack, ...]
    danmaku: MediaSource


def project_assets(resolved: ResolvedMedia, player_data: JsonMapping) -> MediaAssets:
    referer = resolved.page.canonical_url or resolved.item.ref.canonical_url
    subtitle_value = player_data.get("subtitle")
    subtitles: list[SubtitleTrack] = []
    if subtitle_value is not None:
        subtitle = mapping(subtitle_value, stage="assets", field="subtitle")
        raw_tracks = sequence(
            subtitle.get("subtitles", []),
            stage="assets",
            field="subtitle.subtitles",
        )
        seen: set[str] = set()
        for position, raw in enumerate(raw_tracks, start=1):
            track = mapping(raw, stage="assets", field="subtitle track")
            language_value = track.get("lan")
            url_value = track.get("subtitle_url")
            if not isinstance(language_value, str) or not language_value:
                raise ExtractionError("A Bilibili subtitle track has no language.")
            if not isinstance(url_value, str) or not url_value:
                raise ExtractionError("A Bilibili subtitle track has no public URL.")
            id_value = track.get("id")
            track_id = str(id_value) if isinstance(id_value, (int, str)) else str(position)
            identity = f"{language_value.casefold()}:{track_id}"
            if identity in seen:
                continue
            seen.add(identity)
            label_value = track.get("lan_doc")
            label = label_value if isinstance(label_value, str) and label_value else language_value
            subtitles.append(
                SubtitleTrack(
                    track_id=track_id,
                    language=language_value,
                    label=label,
                    source=public_source(url_value, referer=referer),
                )
            )
    subtitles.sort(key=lambda track: (track.language.casefold(), track.track_id))
    cover = resolved.page.cover or resolved.item.cover
    danmaku = public_source(
        f"https://api.bilibili.com/x/v1/dm/list.so?oid={resolved.page.page_id}",
        referer=referer,
    )
    return MediaAssets(cover=cover, subtitles=tuple(subtitles), danmaku=danmaku)
