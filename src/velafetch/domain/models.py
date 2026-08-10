"""Media models used by the extractor and track selector."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Site(StrEnum):
    BILIBILI = "bilibili"


class MediaResourceKind(StrEnum):
    VIDEO = "video"
    BANGUMI_SEASON = "bangumi_season"
    UGC_SEASON = "ugc_season"
    UGC_SERIES = "ugc_series"


class MediaKind(StrEnum):
    VIDEO = "video"
    AUDIO = "audio"


class CodecFamily(StrEnum):
    AVC = "avc"
    HEVC = "hevc"
    AV1 = "av1"
    AAC = "aac"
    FLAC = "flac"
    EAC3 = "eac3"
    UNKNOWN = "unknown"


class DynamicRange(StrEnum):
    SDR = "sdr"
    HDR = "hdr"
    DOLBY_VISION = "dolby_vision"
    UNKNOWN = "unknown"


class CodecPreference(StrEnum):
    AUTO = "auto"
    AVC = "avc"
    HEVC = "hevc"
    AV1 = "av1"


class DynamicRangePreference(StrEnum):
    SDR = "sdr"
    HDR = "hdr"


class OutputMode(StrEnum):
    MUXED = "muxed"
    VIDEO_ONLY = "video_only"
    AUDIO_ONLY = "audio_only"
    NO_MUX = "no_mux"


class MediaSource(Model):
    """Private download URLs; deliberately hidden from repr and serialization."""

    urls: tuple[str, ...] = Field(min_length=1, repr=False, exclude=True)
    required_headers: dict[str, str] = Field(default_factory=dict, repr=False, exclude=True)


class MediaFormat(Model):
    format_id: str
    kind: MediaKind
    container: str
    codec: str
    codec_family: CodecFamily
    bitrate: int
    source: MediaSource = Field(repr=False, exclude=True)
    quality_id: int | None = None
    quality_label: str | None = None
    width: int | None = None
    height: int | None = None
    frame_rate_numerator: int | None = None
    frame_rate_denominator: int | None = None
    dynamic_range: DynamicRange = DynamicRange.UNKNOWN
    sample_rate_hz: int | None = None
    channels: int | None = None
    language: str | None = None
    download_supported: bool = True
    unsupported_reason: str | None = None

    @model_validator(mode="after")
    def check_kind(self) -> MediaFormat:
        if self.kind is MediaKind.VIDEO and (self.width is None or self.height is None):
            raise ValueError("video tracks need width and height")
        if self.kind is MediaKind.AUDIO and (self.width is not None or self.height is not None):
            raise ValueError("audio tracks cannot have video dimensions")
        return self


class MediaRef(Model):
    site: Site
    kind: MediaResourceKind = MediaResourceKind.VIDEO
    canonical_id: str
    canonical_url: str
    normalized_input: str
    page_index: int = 1
    avid: int | None = None


class MediaPage(Model):
    index: int
    page_id: str
    title: str
    duration_ms: int
    formats: tuple[MediaFormat, ...] = ()
    avid: int | None = None
    bvid: str | None = None
    episode_id: int | None = None
    canonical_url: str | None = None
    cover: MediaSource | None = Field(default=None, repr=False, exclude=True)


class MediaItem(Model):
    ref: MediaRef
    title: str
    duration_ms: int
    pages: tuple[MediaPage, ...]
    cover: MediaSource | None = Field(default=None, repr=False, exclude=True)


class MediaCollectionEntry(Model):
    index: int
    entry_id: str
    canonical_url: str
    title: str
    duration_ms: int
    avid: int | None = None
    bvid: str | None = None
    cid: int | None = None
    episode_id: int | None = None
    cover: MediaSource | None = Field(default=None, repr=False, exclude=True)


class MediaCollection(Model):
    ref: MediaRef
    title: str
    entries: tuple[MediaCollectionEntry, ...]
    selected_index: int = 1
    selected_page: int = 1
    cover: MediaSource | None = Field(default=None, repr=False, exclude=True)


class SelectionPolicy(Model):
    quality: str = Field(default="best", pattern=r"^(best|[1-9][0-9]{2,4}p)$")
    codec: CodecPreference = CodecPreference.AUTO
    dynamic_range: DynamicRangePreference = DynamicRangePreference.SDR
    output_mode: OutputMode = OutputMode.MUXED
