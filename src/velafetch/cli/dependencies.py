"""Tiny dependency boundary used by CLI tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import typer

from velafetch.application import (
    DoctorReport,
    DownloadResult,
    ProgressCallback,
    SubtitleOutputFormat,
)
from velafetch.domain.models import SelectionPolicy
from velafetch.extractors import MediaResource, ResolvedMedia


class MediaService(Protocol):
    async def info(
        self,
        source: str,
        *,
        item_index: int | None,
        page_index: int | None,
        timeout: float,
        proxy: str | None,
    ) -> MediaResource: ...

    async def formats(
        self,
        source: str,
        *,
        item_index: int | None,
        page_index: int | None,
        timeout: float,
        proxy: str | None,
    ) -> ResolvedMedia: ...


class DoctorRunner(Protocol):
    async def run(
        self,
        *,
        ffmpeg_path: Path | None,
        check_network: bool,
        timeout: float,
        proxy: str | None,
    ) -> DoctorReport: ...


class DownloadRunner(Protocol):
    async def download(
        self,
        source: str,
        *,
        output_dir: Path,
        policy: SelectionPolicy,
        item_index: int | None,
        page_index: int | None,
        all_items: bool,
        overwrite: bool,
        ffmpeg_path: Path | None,
        timeout: float,
        proxy: str | None,
        cover: bool,
        subtitles: str,
        subtitle_format: SubtitleOutputFormat,
        danmaku: bool,
        output_template: str | None,
        progress: ProgressCallback | None,
    ) -> DownloadResult: ...


@dataclass(frozen=True, slots=True)
class CliDependencies:
    media_service: MediaService | None = None
    doctor_service: DoctorRunner | None = None
    download_service: DownloadRunner | None = None


@dataclass(frozen=True, slots=True)
class RuntimeOptions:
    timeout: float = 30.0
    proxy: str | None = None
    ffmpeg_path: Path | None = None


def runtime_options(context: typer.Context) -> RuntimeOptions:
    if not isinstance(context.obj, RuntimeOptions):
        raise RuntimeError("CLI options were not initialized")
    return context.obj
