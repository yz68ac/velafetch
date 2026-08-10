"""Public single-item and sequential batch download command."""

from __future__ import annotations

import asyncio
import re
from contextlib import nullcontext
from pathlib import Path
from typing import Annotated

import typer

import velafetch.cli.rendering as rendering
from velafetch.application import SubtitleOutputFormat
from velafetch.cli.dependencies import DownloadRunner, runtime_options
from velafetch.domain.models import (
    CodecPreference,
    DynamicRangePreference,
    OutputMode,
    SelectionPolicy,
)


def register_download_command(cli: typer.Typer, service: DownloadRunner) -> None:
    @cli.command()
    def download(
        context: typer.Context,
        source: Annotated[str, typer.Argument(help="Bilibili video, season, or list.")],
        output_dir: Annotated[Path, typer.Option("-o", help="Output directory.")] = Path("."),
        quality: Annotated[str, typer.Option("--quality", help="best or HEIGHTp.")] = "best",
        codec: Annotated[
            CodecPreference, typer.Option("--codec", help="auto, avc, hevc, or av1.")
        ] = CodecPreference.AUTO,
        dynamic_range: Annotated[
            DynamicRangePreference,
            typer.Option("--dynamic-range", help="sdr or hdr."),
        ] = DynamicRangePreference.SDR,
        item_index: Annotated[
            int | None,
            typer.Option("--item", min=1, help="Select an episode or collection item."),
        ] = None,
        page_index: Annotated[
            int | None,
            typer.Option("--page", min=1, help="Select a video page."),
        ] = None,
        all_items: Annotated[
            bool,
            typer.Option("--all", help="Download every item and page sequentially."),
        ] = False,
        video_only: Annotated[bool, typer.Option("--video-only")] = False,
        audio_only: Annotated[bool, typer.Option("--audio-only")] = False,
        no_mux: Annotated[bool, typer.Option("--no-mux")] = False,
        overwrite: Annotated[bool, typer.Option("--overwrite")] = False,
        cover: Annotated[
            bool,
            typer.Option("--cover/--no-cover", help="Download the public cover."),
        ] = True,
        subtitles: Annotated[
            str,
            typer.Option("--subtitles", help="all, off, or comma-separated languages."),
        ] = "all",
        subtitle_format: Annotated[
            SubtitleOutputFormat,
            typer.Option("--subtitle-format", help="srt or json."),
        ] = SubtitleOutputFormat.SRT,
        danmaku: Annotated[
            bool,
            typer.Option("--danmaku", help="Download XML danmaku."),
        ] = False,
        output_template: Annotated[
            str | None,
            typer.Option("--output-template", help="Filename stem template."),
        ] = None,
        json_output: Annotated[bool, typer.Option("--json", help="Print JSON result.")] = False,
    ) -> None:
        """Download Bilibili videos, seasons, and collections."""

        if sum((video_only, audio_only, no_mux)) > 1:
            raise typer.BadParameter("output modes are mutually exclusive")
        if all_items and (item_index is not None or page_index is not None):
            raise typer.BadParameter("--all cannot be combined with --item or --page")
        if quality != "best" and not re.fullmatch(r"[1-9][0-9]{2,4}p", quality):
            raise typer.BadParameter("quality must be best or HEIGHTp")
        mode = (
            OutputMode.VIDEO_ONLY
            if video_only
            else OutputMode.AUDIO_ONLY
            if audio_only
            else OutputMode.NO_MUX
            if no_mux
            else OutputMode.MUXED
        )
        options = runtime_options(context)
        try:
            progress_context = nullcontext(None) if json_output else rendering.download_progress()
            with progress_context as progress:
                result = asyncio.run(
                    service.download(
                        source,
                        output_dir=output_dir,
                        policy=SelectionPolicy(
                            quality=quality,
                            codec=codec,
                            dynamic_range=dynamic_range,
                            output_mode=mode,
                        ),
                        item_index=item_index,
                        page_index=page_index,
                        all_items=all_items,
                        overwrite=overwrite,
                        ffmpeg_path=options.ffmpeg_path,
                        timeout=options.timeout,
                        proxy=options.proxy,
                        cover=cover,
                        subtitles=subtitles,
                        subtitle_format=subtitle_format,
                        danmaku=danmaku,
                        output_template=output_template,
                        progress=progress,
                        anonymous=options.anonymous,
                    )
                )
        except BaseException as error:
            rendering.emit_error(error, json_output=json_output)
        rendering.emit_download(result, json_output=json_output)
        if not result.ok:
            raise typer.Exit(1)

    _ = download
