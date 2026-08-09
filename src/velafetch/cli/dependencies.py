"""Tiny dependency boundary used by CLI tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import typer

from velafetch.application import DoctorReport
from velafetch.domain.models import MediaItem


class MediaService(Protocol):
    async def info(self, source: str, *, timeout: float, proxy: str | None) -> MediaItem: ...

    async def formats(self, source: str, *, timeout: float, proxy: str | None) -> MediaItem: ...


class DoctorRunner(Protocol):
    async def run(
        self,
        *,
        ffmpeg_path: Path | None,
        check_network: bool,
        timeout: float,
        proxy: str | None,
    ) -> DoctorReport: ...


@dataclass(frozen=True, slots=True)
class CliDependencies:
    media_service: MediaService | None = None
    doctor_service: DoctorRunner | None = None


@dataclass(frozen=True, slots=True)
class RuntimeOptions:
    timeout: float = 30.0
    proxy: str | None = None
    ffmpeg_path: Path | None = None


def runtime_options(context: typer.Context) -> RuntimeOptions:
    if not isinstance(context.obj, RuntimeOptions):
        raise RuntimeError("CLI options were not initialized")
    return context.obj
