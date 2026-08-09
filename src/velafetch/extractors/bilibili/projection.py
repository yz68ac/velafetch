"""DASH collection projection and stable public format ordering."""

from __future__ import annotations

from fractions import Fraction
from typing import cast

from velafetch.domain.models import CodecFamily, MediaFormat, MediaKind
from velafetch.errors import ExtractionError
from velafetch.extractors.bilibili.payload import JsonMapping, mapping
from velafetch.extractors.bilibili.track import project_audio, project_video


def _track_values(value: object | None, *, field: str) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return cast("list[object]", value)
    if isinstance(value, dict):
        return [value]
    raise ExtractionError(
        "The Bilibili DASH response has an invalid track collection.",
        {"stage": "formats", "field": field},
    )


def _descending_text(value: str) -> tuple[int, ...]:
    return tuple(-ord(character) for character in value)


def sort_formats(formats: tuple[MediaFormat, ...]) -> tuple[MediaFormat, ...]:
    """Return the stable public order without considering private source URLs."""

    video_codec_rank = {
        CodecFamily.AVC: 0,
        CodecFamily.HEVC: 1,
        CodecFamily.AV1: 2,
        CodecFamily.UNKNOWN: 3,
    }
    audio_codec_rank = {
        CodecFamily.AAC: 0,
        CodecFamily.EAC3: 1,
        CodecFamily.FLAC: 2,
        CodecFamily.UNKNOWN: 3,
    }

    def key(track: MediaFormat) -> tuple[object, ...]:
        if track.kind is MediaKind.VIDEO:
            frame_rate = Fraction(
                track.frame_rate_numerator or 1,
                track.frame_rate_denominator or 1,
            )
            return (
                0,
                -(track.height or 0),
                -int(track.download_supported),
                video_codec_rank.get(track.codec_family, 4),
                -frame_rate,
                -track.bitrate,
                _descending_text(track.format_id),
            )
        return (
            1,
            -int(track.download_supported),
            -track.bitrate,
            audio_codec_rank.get(track.codec_family, 4),
            _descending_text(track.format_id),
        )

    return tuple(sorted(formats, key=key))


def project_formats(data: JsonMapping, canonical_url: str) -> tuple[MediaFormat, ...]:
    """Project ordinary and optional Dolby/FLAC DASH collections."""

    dash = mapping(data.get("dash"), stage="formats", field="dash")
    videos = _track_values(dash.get("video"), field="video")
    audios = _track_values(dash.get("audio"), field="audio")

    dolby_value = dash.get("dolby")
    if dolby_value is not None:
        dolby = mapping(dolby_value, stage="formats", field="dolby")
        audios.extend(_track_values(dolby.get("audio"), field="dolby.audio"))
    flac_value = dash.get("flac")
    if flac_value is not None:
        flac = mapping(flac_value, stage="formats", field="flac")
        audios.extend(_track_values(flac.get("audio"), field="flac.audio"))

    projected = [*(project_video(value, canonical_url) for value in videos)]
    projected.extend(project_audio(value, canonical_url) for value in audios)
    unique = {track.format_id: track for track in projected}
    return sort_formats(tuple(unique.values()))
