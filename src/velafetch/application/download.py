"""Sequential single and batch download orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from velafetch.application.assets import (
    ArtifactResult,
    SubtitleOutputFormat,
    download_cover,
    download_danmaku,
    download_subtitles,
    parse_subtitle_selection,
)
from velafetch.application.ffmpeg import resolve_ffmpeg
from velafetch.application.media_download import download_media
from velafetch.application.naming import (
    batch_output_root,
    target_paths,
    unit_stem,
)
from velafetch.application.transfer import TrackProgressCallback
from velafetch.auth import CredentialStore
from velafetch.domain.models import MediaFormat, MediaKind, OutputMode, SelectionPolicy
from velafetch.errors import DownloadError, VelaFetchError
from velafetch.extractors import BilibiliExtractor, ResolvedMedia
from velafetch.selection import select_formats
from velafetch.transport import HttpClientFactory, create_http_client


class DownloadStatus(StrEnum):
    SAVED = "saved"
    SKIPPED = "skipped"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ProgressUpdate:
    unit_number: int
    unit_count: int
    label: str
    kind: MediaKind
    downloaded: int
    total: int | None
    quality: str | None = None
    codec: str | None = None
    width: int | None = None
    height: int | None = None
    frame_rate_numerator: int | None = None
    frame_rate_denominator: int | None = None
    bitrate: int | None = None
    dynamic_range: str | None = None
    channels: int | None = None
    language: str | None = None


ProgressCallback = Callable[[ProgressUpdate], None]


@dataclass(frozen=True, slots=True)
class DownloadItemResult:
    media_id: str
    title: str
    item_index: int
    page_index: int
    status: DownloadStatus
    output_paths: tuple[Path, ...] = ()
    warnings: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True, slots=True)
class DownloadResult:
    items: tuple[DownloadItemResult, ...]
    aborted: bool = False

    @property
    def ok(self) -> bool:
        return all(
            item.status not in {DownloadStatus.PARTIAL, DownloadStatus.FAILED}
            for item in self.items
        )

    @property
    def output_paths(self) -> tuple[Path, ...]:
        return tuple(path for item in self.items for path in item.output_paths)

    @property
    def skipped(self) -> bool:
        return bool(self.items) and all(
            item.status is DownloadStatus.SKIPPED for item in self.items
        )


def _unique_units(
    units: tuple[ResolvedMedia, ...], *, batch: bool, template: str | None
) -> tuple[str, ...]:
    stems = tuple(unit_stem(unit, batch=batch, template=template) for unit in units)
    if len(set(stem.casefold() for stem in stems)) != len(stems):
        raise DownloadError("The selected output template creates duplicate batch filenames.")
    return stems


class DownloadService:
    """Resolve and download one or many Bilibili playback units."""

    def __init__(
        self,
        client_factory: HttpClientFactory = create_http_client,
        credential_store: CredentialStore | None = None,
    ) -> None:
        self._client_factory = client_factory
        self._credential_store = credential_store or CredentialStore()

    async def download(
        self,
        source: str,
        *,
        output_dir: Path,
        policy: SelectionPolicy,
        item_index: int | None = None,
        page_index: int | None = None,
        all_items: bool = False,
        overwrite: bool = False,
        ffmpeg_path: Path | None = None,
        timeout: float = 30.0,
        proxy: str | None = None,
        cover: bool = True,
        subtitles: str = "all",
        subtitle_format: SubtitleOutputFormat = SubtitleOutputFormat.SRT,
        danmaku: bool = False,
        output_template: str | None = None,
        progress: ProgressCallback | None = None,
        anonymous: bool = False,
    ) -> DownloadResult:
        subtitle_selection = parse_subtitle_selection(subtitles)
        output_root = output_dir.expanduser().resolve()
        try:
            output_root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise DownloadError("The output directory could not be created.") from error
        if not output_root.is_dir():
            raise DownloadError("The output path is not a directory.")

        ffmpeg = None
        if policy.output_mode is OutputMode.MUXED:
            ffmpeg_location = resolve_ffmpeg(ffmpeg_path)
            if ffmpeg_location is None:
                raise DownloadError("FFmpeg was not found. Use --ffmpeg to provide its path.")
            ffmpeg = str(ffmpeg_location.path)

        credentials = None if anonymous else self._credential_store.load()
        cookies = None if credentials is None else credentials.cookie_mapping()
        async with self._client_factory(timeout, proxy, cookies) as client:
            extractor = BilibiliExtractor(client)
            units = await extractor.resolve_many(
                source,
                item_index=item_index,
                page_index=page_index,
                all_items=all_items,
            )
            batch = all_items
            stems = _unique_units(units, batch=batch, template=output_template)
            publish_root = batch_output_root(output_root, units[0]) if batch else output_root
            results: list[DownloadItemResult] = []
            aborted = False

            for unit_number, (metadata_unit, stem) in enumerate(
                zip(units, stems, strict=True), start=1
            ):
                output_paths: tuple[Path, ...] = ()
                warnings: tuple[str, ...] = ()
                media_saved = False
                try:
                    unit = await extractor.load_formats(metadata_unit)
                    selection = select_formats(unit.page, policy)
                    media_targets = target_paths(publish_root, stem, selection, policy.output_mode)

                    track_progress: TrackProgressCallback | None = None
                    if progress is not None:

                        def report_track_progress(
                            kind: MediaKind,
                            downloaded: int,
                            total: int | None,
                            *,
                            current: int = unit_number,
                            label: str = stem,
                            video_track: MediaFormat | None = selection.video,
                            audio_track: MediaFormat | None = selection.audio,
                        ) -> None:
                            track = video_track if kind is MediaKind.VIDEO else audio_track
                            progress(
                                ProgressUpdate(
                                    current,
                                    len(units),
                                    label,
                                    kind,
                                    downloaded,
                                    total,
                                    quality=track.quality_label if track else None,
                                    codec=track.codec_family.value if track else None,
                                    width=track.width if track else None,
                                    height=track.height if track else None,
                                    frame_rate_numerator=(
                                        track.frame_rate_numerator if track else None
                                    ),
                                    frame_rate_denominator=(
                                        track.frame_rate_denominator if track else None
                                    ),
                                    bitrate=track.bitrate if track else None,
                                    dynamic_range=(track.dynamic_range.value if track else None),
                                    channels=track.channels if track else None,
                                    language=track.language if track else None,
                                )
                            )

                        track_progress = report_track_progress

                    media_saved = await download_media(
                        client,
                        unit,
                        selection,
                        media_targets,
                        state_root=output_root,
                        ffmpeg=ffmpeg,
                        overwrite=overwrite,
                        policy=policy,
                        progress=track_progress,
                    )
                    output_paths = tuple(path for path in media_targets if path.exists())
                except VelaFetchError as error:
                    results.append(
                        DownloadItemResult(
                            metadata_unit.item.ref.canonical_id,
                            metadata_unit.item.title,
                            metadata_unit.item_index,
                            metadata_unit.page_index,
                            DownloadStatus.FAILED,
                            output_paths,
                            warnings,
                            str(error),
                        )
                    )
                    aborted = True
                    break

                artifacts = ArtifactResult()
                if cover:
                    artifacts = artifacts.merge(
                        await download_cover(
                            client,
                            unit,
                            publish_root,
                            stem,
                            overwrite=overwrite,
                        )
                    )
                if subtitle_selection.enabled:
                    try:
                        assets = await extractor.get_assets(unit)
                    except VelaFetchError as error:
                        artifacts = artifacts.merge(ArtifactResult(errors=(str(error),)))
                    else:
                        artifacts = artifacts.merge(
                            await download_subtitles(
                                client,
                                assets.subtitles,
                                subtitle_selection,
                                subtitle_format,
                                publish_root,
                                stem,
                                overwrite=overwrite,
                            )
                        )
                if danmaku:
                    artifacts = artifacts.merge(
                        await download_danmaku(
                            client,
                            unit,
                            publish_root,
                            stem,
                            overwrite=overwrite,
                        )
                    )

                output_paths = (*output_paths, *artifacts.paths)
                warnings = artifacts.warnings
                if artifacts.errors:
                    status = DownloadStatus.PARTIAL
                    error = " ".join(artifacts.errors)
                elif media_saved or artifacts.saved:
                    status = DownloadStatus.SAVED
                    error = None
                else:
                    status = DownloadStatus.SKIPPED
                    error = None
                results.append(
                    DownloadItemResult(
                        unit.item.ref.canonical_id,
                        unit.item.title,
                        unit.item_index,
                        unit.page_index,
                        status,
                        output_paths,
                        warnings,
                        error,
                    )
                )
        return DownloadResult(tuple(results), aborted=aborted)
