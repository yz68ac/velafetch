"""Deterministic quality, codec, audio, and output-mode selection tests."""

from __future__ import annotations

import pytest

from velafetch.domain.models import (
    CodecFamily,
    CodecPreference,
    DynamicRange,
    DynamicRangePreference,
    MediaFormat,
    MediaKind,
    MediaPage,
    MediaSource,
    OutputMode,
    SelectionPolicy,
)
from velafetch.errors import SelectionError
from velafetch.selection import select_formats


def _source() -> MediaSource:
    return MediaSource.model_validate({"urls": ["https://media.invalid/track.m4s"]})


def _video(
    format_id: str,
    height: int,
    family: CodecFamily,
    *,
    fps: int = 30,
    bitrate: int = 1_000_000,
    supported: bool = True,
    dynamic_range: DynamicRange = DynamicRange.SDR,
) -> MediaFormat:
    return MediaFormat(
        format_id=format_id,
        kind=MediaKind.VIDEO,
        container="mp4",
        codec={
            CodecFamily.AVC: "avc1.640028",
            CodecFamily.HEVC: "hev1.1.6.L120.90",
            CodecFamily.AV1: "av01.0.12M.10",
        }[family],
        codec_family=family,
        bitrate=bitrate,
        source=_source(),
        quality_id=height,
        quality_label=f"{height}p",
        width=height * 16 // 9,
        height=height,
        frame_rate_numerator=fps,
        frame_rate_denominator=1,
        dynamic_range=dynamic_range,
        download_supported=supported,
        unsupported_reason=None if supported else "Deferred.",
    )


def _audio(format_id: str, bitrate: int, *, supported: bool = True) -> MediaFormat:
    return MediaFormat(
        format_id=format_id,
        kind=MediaKind.AUDIO,
        container="m4a",
        codec="mp4a.40.2",
        codec_family=CodecFamily.AAC,
        bitrate=bitrate,
        source=_source(),
        language="und",
        download_supported=supported,
        unsupported_reason=None if supported else "Deferred.",
    )


def _page(*formats: MediaFormat) -> MediaPage:
    return MediaPage(
        index=1, page_id="synthetic", title="Synthetic", duration_ms=1, formats=formats
    )


def test_best_ignores_deferred_tracks_and_auto_prefers_avc_at_the_best_height() -> None:
    selection = select_formats(
        _page(
            _video("av1-2160", 2160, CodecFamily.AV1, supported=False),
            _video("hevc-1080", 1080, CodecFamily.HEVC, fps=60, bitrate=9_000_000),
            _video("avc-1080", 1080, CodecFamily.AVC, fps=30, bitrate=4_000_000),
            _audio("aac-128", 128_000),
            _audio("aac-192", 192_000),
        ),
        SelectionPolicy(),
    )

    assert selection.video is not None
    assert selection.video.format_id == "avc-1080"
    assert selection.audio is not None
    assert selection.audio.format_id == "aac-192"


def test_auto_codec_order_is_avc_then_hevc_then_av1_at_the_same_height() -> None:
    selection = select_formats(
        _page(
            _video("av1", 2160, CodecFamily.AV1, fps=120, bitrate=12_000_000),
            _video("hevc", 2160, CodecFamily.HEVC, fps=60, bitrate=8_000_000),
            _video("avc", 2160, CodecFamily.AVC, fps=30, bitrate=6_000_000),
            _audio("aac", 128_000),
        ),
        SelectionPolicy(),
    )

    assert selection.video is not None
    assert selection.video.format_id == "avc"


def test_av1_sdr_and_hevc_hdr_are_strictly_selectable() -> None:
    page = _page(
        _video("av1-sdr", 2160, CodecFamily.AV1),
        _video(
            "hevc-hdr",
            2160,
            CodecFamily.HEVC,
            dynamic_range=DynamicRange.HDR,
        ),
        _audio("aac", 128_000),
    )

    av1 = select_formats(page, SelectionPolicy(codec=CodecPreference.AV1))
    hdr = select_formats(
        page,
        SelectionPolicy(
            codec=CodecPreference.HEVC,
            dynamic_range=DynamicRangePreference.HDR,
        ),
    )

    assert av1.video is not None and av1.video.format_id == "av1-sdr"
    assert hdr.video is not None and hdr.video.format_id == "hevc-hdr"
    with pytest.raises(SelectionError, match="requested codec"):
        select_formats(
            page,
            SelectionPolicy(
                codec=CodecPreference.AVC,
                dynamic_range=DynamicRangePreference.HDR,
            ),
        )


def test_quality_limit_selects_the_highest_height_not_exceeding_the_request() -> None:
    selection = select_formats(
        _page(
            _video("avc-1080", 1080, CodecFamily.AVC),
            _video("avc-720", 720, CodecFamily.AVC),
            _video("avc-480", 480, CodecFamily.AVC),
            _audio("aac", 128_000),
        ),
        SelectionPolicy(quality="900p"),
    )

    assert selection.video is not None
    assert selection.video.height == 720


def test_explicit_codec_is_strict_at_the_selected_height_without_cross_codec_downgrade() -> None:
    with pytest.raises(SelectionError, match="requested codec"):
        select_formats(
            _page(
                _video("avc-1080", 1080, CodecFamily.AVC),
                _video("hevc-720", 720, CodecFamily.HEVC),
                _audio("aac", 128_000),
            ),
            SelectionPolicy(codec=CodecPreference.HEVC),
        )


def test_explicit_codec_ties_use_frame_rate_bitrate_then_descending_id() -> None:
    selection = select_formats(
        _page(
            _video("hevc-a", 1080, CodecFamily.HEVC, fps=30, bitrate=9_000_000),
            _video("hevc-b", 1080, CodecFamily.HEVC, fps=60, bitrate=4_000_000),
            _video("hevc-c", 1080, CodecFamily.HEVC, fps=60, bitrate=4_000_000),
            _audio("aac", 128_000),
        ),
        SelectionPolicy(codec=CodecPreference.HEVC),
    )

    assert selection.video is not None
    assert selection.video.format_id == "hevc-c"


def test_audio_only_does_not_require_video_and_video_only_does_not_require_audio() -> None:
    audio = select_formats(
        _page(_audio("aac", 128_000)),
        SelectionPolicy(output_mode=OutputMode.AUDIO_ONLY),
    )
    video = select_formats(
        _page(_video("avc", 720, CodecFamily.AVC)),
        SelectionPolicy(output_mode=OutputMode.VIDEO_ONLY),
    )

    assert audio.video is None and audio.audio is not None
    assert video.video is not None and video.audio is None


@pytest.mark.parametrize(
    ("formats", "policy", "message"),
    [
        ((), SelectionPolicy(output_mode=OutputMode.VIDEO_ONLY), "video"),
        ((), SelectionPolicy(output_mode=OutputMode.AUDIO_ONLY), "AAC audio"),
        (
            (_video("avc", 1080, CodecFamily.AVC),),
            SelectionPolicy(quality="720p", output_mode=OutputMode.VIDEO_ONLY),
            "at or below",
        ),
        (
            (_audio("aac", 128_000, supported=False),),
            SelectionPolicy(output_mode=OutputMode.AUDIO_ONLY),
            "AAC audio",
        ),
    ],
)
def test_missing_required_tracks_are_selection_errors(
    formats: tuple[MediaFormat, ...],
    policy: SelectionPolicy,
    message: str,
) -> None:
    with pytest.raises(SelectionError, match=message):
        select_formats(_page(*formats), policy)
