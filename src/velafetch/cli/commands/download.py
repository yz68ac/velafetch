"""The placeholder for the saved M4 download plan."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated

import typer

import velafetch.cli.rendering as rendering
from velafetch.domain.models import CodecPreference
from velafetch.errors import UnsupportedFeatureError


def register_download_command(cli: typer.Typer) -> None:
    @cli.command()
    def download(
        source: Annotated[str, typer.Argument(help="BV, av, or a standard Bilibili URL.")],
        output_dir: Annotated[Path, typer.Option("-o", help="Output directory.")] = Path("."),
        quality: Annotated[str, typer.Option("--quality", help="best or HEIGHTp.")] = "best",
        codec: Annotated[
            CodecPreference, typer.Option("--codec", help="auto, avc, or hevc.")
        ] = CodecPreference.AUTO,
        video_only: Annotated[bool, typer.Option("--video-only")] = False,
        audio_only: Annotated[bool, typer.Option("--audio-only")] = False,
        no_mux: Annotated[bool, typer.Option("--no-mux")] = False,
        overwrite: Annotated[bool, typer.Option("--overwrite")] = False,
    ) -> None:
        """Download support is the next learning milestone."""

        del source, output_dir, codec, overwrite
        if sum((video_only, audio_only, no_mux)) > 1:
            raise typer.BadParameter("output modes are mutually exclusive")
        if quality != "best" and not re.fullmatch(r"[1-9][0-9]{2,4}p", quality):
            raise typer.BadParameter("quality must be best or HEIGHTp")
        rendering.emit_error(
            UnsupportedFeatureError("Downloading is planned for M4."),
            json_output=False,
        )

    _ = download
