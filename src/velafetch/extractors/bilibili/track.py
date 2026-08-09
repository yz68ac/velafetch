"""Projection of one Bilibili DASH entry into a stable private media track."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from fractions import Fraction

from velafetch import __version__
from velafetch.domain.models import (
    CodecFamily,
    DynamicRange,
    MediaFormat,
    MediaKind,
    MediaSource,
)
from velafetch.errors import ExtractionError
from velafetch.extractors.bilibili.payload import (
    mapping,
    optional_positive_int,
    optional_value,
    required_int,
    required_string,
    sequence,
)

USER_AGENT = f"VelaFetch/{__version__}"


def _codec_family(codec: str, codecid: int | None, *, kind: MediaKind) -> CodecFamily:
    normalized = codec.casefold()
    if kind is MediaKind.VIDEO:
        if codecid == 7 or normalized.startswith(("avc1", "avc3")):
            return CodecFamily.AVC
        if codecid == 12 or normalized.startswith(("hev1", "hvc1", "hevc")):
            return CodecFamily.HEVC
        if codecid == 13 or normalized.startswith("av01"):
            return CodecFamily.AV1
    else:
        if normalized.startswith(("mp4a", "aac")):
            return CodecFamily.AAC
        if "flac" in normalized:
            return CodecFamily.FLAC
        if normalized.startswith(("ec-3", "ec3", "eac3")):
            return CodecFamily.EAC3
    return CodecFamily.UNKNOWN


def _container(mime_type: str, *, kind: MediaKind) -> str:
    normalized = mime_type.casefold()
    if normalized in {"video/mp4", "application/mp4"}:
        return "mp4"
    if normalized == "audio/mp4":
        return "m4a"
    if normalized in {"audio/flac", "audio/x-flac"}:
        return "flac"
    if "/" in normalized:
        subtype = normalized.rsplit("/", 1)[-1].split(";", 1)[0]
        if subtype and re.fullmatch(r"[a-z0-9.+-]+", subtype):
            return subtype
    return "unknown" if kind is MediaKind.VIDEO else "audio"


def _frame_rate(value: object) -> tuple[int, int]:
    if isinstance(value, bool):
        raise ValueError("Boolean frame rate")
    try:
        frame_rate = Fraction(str(value))
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError("Invalid frame rate") from error
    if frame_rate <= 0:
        raise ValueError("Non-positive frame rate")
    return frame_rate.numerator, frame_rate.denominator


def _dynamic_range(track: Mapping[str, object], quality_id: int) -> DynamicRange:
    raw = optional_value(track, "dynamic_range", "dynamicRange", "hdr_type", "hdrType")
    text = str(raw).casefold() if raw is not None else ""
    if quality_id == 126 or "dolby" in text:
        return DynamicRange.DOLBY_VISION
    if quality_id == 125 or "hdr" in text:
        return DynamicRange.HDR
    return DynamicRange.SDR


def _source_urls(track: Mapping[str, object]) -> tuple[str, ...]:
    primary = optional_value(track, "baseUrl", "base_url")
    if not isinstance(primary, str) or not primary:
        raise ExtractionError(
            "A Bilibili media track has no primary URL.",
            {"stage": "formats", "field": "base_url"},
        )
    backup_value = optional_value(track, "backupUrl", "backup_url")
    backups = (
        [] if backup_value is None else sequence(backup_value, stage="formats", field="backup_url")
    )
    ordered: list[str] = []
    for value in [primary, *backups]:
        if not isinstance(value, str) or not value:
            raise ExtractionError(
                "A Bilibili media track has an invalid backup URL.",
                {"stage": "formats", "field": "backup_url"},
            )
        if value not in ordered:
            ordered.append(value)
    return tuple(ordered)


def _format_id(
    *,
    kind: MediaKind,
    api_id: int,
    family: CodecFamily,
    metadata: tuple[object, ...],
) -> str:
    identity = json.dumps(metadata, ensure_ascii=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(identity.encode()).hexdigest()[:12]
    return f"{kind.value}-{api_id}-{family.value}-{fingerprint}"


def _video_support(
    family: CodecFamily,
    dynamic_range: DynamicRange,
    container: str,
) -> tuple[bool, str | None]:
    if dynamic_range is DynamicRange.DOLBY_VISION:
        return False, "Dolby Vision video is planned for M6."
    if dynamic_range is DynamicRange.HDR:
        return False, "HDR video is planned for M6."
    if family is CodecFamily.AV1:
        return False, "AV1 video is planned for M6."
    if family not in {CodecFamily.AVC, CodecFamily.HEVC}:
        return False, "This video codec is not supported by the MVP."
    if container != "mp4":
        return False, "This video container is not supported by the MVP."
    return True, None


def _audio_support(family: CodecFamily, container: str) -> tuple[bool, str | None]:
    if family is CodecFamily.FLAC:
        return False, "FLAC audio is planned for M6."
    if family is CodecFamily.EAC3:
        return False, "E-AC-3 audio is planned for M6."
    if family is not CodecFamily.AAC:
        return False, "This audio codec is not supported by the MVP."
    if container != "m4a":
        return False, "This audio container is not supported by the MVP."
    return True, None


def _media_source(track: Mapping[str, object], canonical_url: str) -> MediaSource:
    return MediaSource(
        urls=_source_urls(track),
        required_headers={"Referer": canonical_url, "User-Agent": USER_AGENT},
    )


def project_video(track_value: object, canonical_url: str) -> MediaFormat:
    """Project a single video representation and its support state."""

    track = mapping(track_value, stage="formats", field="video")
    api_id = required_int(track, "id", stage="formats")
    codec = required_string(track, "codecs", stage="formats")
    codecid_value = track.get("codecid")
    codecid = (
        codecid_value
        if isinstance(codecid_value, int) and not isinstance(codecid_value, bool)
        else None
    )
    family = _codec_family(codec, codecid, kind=MediaKind.VIDEO)
    mime_type = optional_value(track, "mimeType", "mime_type")
    if not isinstance(mime_type, str):
        raise ExtractionError(
            "A Bilibili video track has no MIME type.",
            {"stage": "formats", "field": "mime_type"},
        )
    container = _container(mime_type, kind=MediaKind.VIDEO)
    bitrate = required_int(track, "bandwidth", stage="formats", minimum=1)
    width = required_int(track, "width", stage="formats", minimum=1)
    height = required_int(track, "height", stage="formats", minimum=1)
    try:
        frame_numerator, frame_denominator = _frame_rate(
            optional_value(track, "frameRate", "frame_rate")
        )
    except ValueError as error:
        raise ExtractionError(
            "A Bilibili video track has an invalid frame rate.",
            {"stage": "formats", "field": "frame_rate"},
        ) from error
    dynamic_range = _dynamic_range(track, api_id)
    supported, reason = _video_support(family, dynamic_range, container)
    metadata = (
        MediaKind.VIDEO.value,
        api_id,
        family.value,
        codec,
        bitrate,
        width,
        height,
        frame_numerator,
        frame_denominator,
        dynamic_range.value,
        container,
    )
    return MediaFormat(
        format_id=_format_id(
            kind=MediaKind.VIDEO,
            api_id=api_id,
            family=family,
            metadata=metadata,
        ),
        kind=MediaKind.VIDEO,
        container=container,
        codec=codec,
        codec_family=family,
        bitrate=bitrate,
        source=_media_source(track, canonical_url),
        quality_id=api_id,
        quality_label=f"{height}p",
        width=width,
        height=height,
        frame_rate_numerator=frame_numerator,
        frame_rate_denominator=frame_denominator,
        dynamic_range=dynamic_range,
        download_supported=supported,
        unsupported_reason=reason,
    )


def project_audio(track_value: object, canonical_url: str) -> MediaFormat:
    """Project a single audio representation and its support state."""

    track = mapping(track_value, stage="formats", field="audio")
    api_id = required_int(track, "id", stage="formats")
    codec = required_string(track, "codecs", stage="formats")
    codecid_value = track.get("codecid")
    codecid = (
        codecid_value
        if isinstance(codecid_value, int) and not isinstance(codecid_value, bool)
        else None
    )
    family = _codec_family(codec, codecid, kind=MediaKind.AUDIO)
    mime_type = optional_value(track, "mimeType", "mime_type")
    if not isinstance(mime_type, str):
        raise ExtractionError(
            "A Bilibili audio track has no MIME type.",
            {"stage": "formats", "field": "mime_type"},
        )
    container = _container(mime_type, kind=MediaKind.AUDIO)
    bitrate = required_int(track, "bandwidth", stage="formats", minimum=1)
    sample_rate = optional_positive_int(track, "audio_sample_rate", "sampleRate", "sample_rate")
    channels = optional_positive_int(track, "channels", "audio_channels")
    language_value = optional_value(track, "lang", "language")
    language = language_value if isinstance(language_value, str) and language_value else "und"
    supported, reason = _audio_support(family, container)
    metadata = (
        MediaKind.AUDIO.value,
        api_id,
        family.value,
        codec,
        bitrate,
        sample_rate,
        channels,
        language,
        container,
    )
    return MediaFormat(
        format_id=_format_id(
            kind=MediaKind.AUDIO,
            api_id=api_id,
            family=family,
            metadata=metadata,
        ),
        kind=MediaKind.AUDIO,
        container=container,
        codec=codec,
        codec_family=family,
        bitrate=bitrate,
        source=_media_source(track, canonical_url),
        sample_rate_hz=sample_rate,
        channels=channels,
        language=language,
        download_supported=supported,
        unsupported_reason=reason,
    )
