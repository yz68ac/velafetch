"""Straightforward quality, codec, and audio-track selection."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from velafetch.domain.models import (
    CodecFamily,
    CodecPreference,
    MediaFormat,
    MediaKind,
    MediaPage,
    OutputMode,
    SelectionPolicy,
)
from velafetch.errors import SelectionError


@dataclass(frozen=True, slots=True)
class TrackSelection:
    """The optional video and audio tracks required by one output mode."""

    video: MediaFormat | None
    audio: MediaFormat | None


def _select_video(formats: tuple[MediaFormat, ...], policy: SelectionPolicy) -> MediaFormat:
    candidates = tuple(
        track
        for track in formats
        if track.kind is MediaKind.VIDEO
        and track.download_supported
        and track.codec_family in {CodecFamily.AVC, CodecFamily.HEVC}
    )
    if not candidates:
        raise SelectionError(
            "No supported video format is available.",
            {"kind": "video", "quality": policy.quality, "codec": policy.codec.value},
        )

    maximum_height = None if policy.quality == "best" else int(policy.quality[:-1])
    bounded = tuple(
        track
        for track in candidates
        if maximum_height is None or (track.height or 0) <= maximum_height
    )
    if not bounded:
        raise SelectionError(
            "No supported video format is available at or below the requested height.",
            {"kind": "video", "quality": policy.quality, "codec": policy.codec.value},
        )
    selected_height = max(track.height or 0 for track in bounded)
    at_height = tuple(track for track in bounded if track.height == selected_height)

    if policy.codec is not CodecPreference.AUTO:
        family = CodecFamily.AVC if policy.codec is CodecPreference.AVC else CodecFamily.HEVC
        at_height = tuple(track for track in at_height if track.codec_family is family)
        if not at_height:
            raise SelectionError(
                "The requested codec is not available at the selected height.",
                {
                    "kind": "video",
                    "quality": policy.quality,
                    "codec": policy.codec.value,
                    "height": selected_height,
                },
            )

    codec_rank = {CodecFamily.AVC: 1, CodecFamily.HEVC: 0}

    def rank(track: MediaFormat) -> tuple[object, ...]:
        frame_rate = Fraction(
            track.frame_rate_numerator or 1,
            track.frame_rate_denominator or 1,
        )
        return (
            codec_rank.get(track.codec_family, -1),
            frame_rate,
            track.bitrate,
            track.format_id,
        )

    return max(at_height, key=rank)


def _select_audio(formats: tuple[MediaFormat, ...]) -> MediaFormat:
    candidates = tuple(
        track
        for track in formats
        if track.kind is MediaKind.AUDIO
        and track.download_supported
        and track.codec_family is CodecFamily.AAC
    )
    if not candidates:
        raise SelectionError(
            "No supported AAC audio format is available.",
            {"kind": "audio"},
        )
    return max(candidates, key=lambda track: (track.bitrate, track.format_id))


def select_formats(page: MediaPage, policy: SelectionPolicy) -> TrackSelection:
    """Select exactly the tracks required by the requested output mode."""

    needs_video = policy.output_mode in {
        OutputMode.MUXED,
        OutputMode.VIDEO_ONLY,
        OutputMode.NO_MUX,
    }
    needs_audio = policy.output_mode in {
        OutputMode.MUXED,
        OutputMode.AUDIO_ONLY,
        OutputMode.NO_MUX,
    }
    video = _select_video(page.formats, policy) if needs_video else None
    audio = _select_audio(page.formats) if needs_audio else None
    return TrackSelection(video=video, audio=audio)
