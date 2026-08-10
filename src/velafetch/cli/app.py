"""Typer application factory and console entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from velafetch import __version__
from velafetch.application import DoctorService, DownloadService, MediaApplicationService
from velafetch.cli.commands import (
    register_doctor_command,
    register_download_command,
    register_inspection_commands,
)
from velafetch.cli.dependencies import CliDependencies, RuntimeOptions

__all__ = ["CliDependencies", "app", "create_app", "run"]


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"velafetch {__version__}")
        raise typer.Exit()


def create_app(dependencies: CliDependencies | None = None) -> typer.Typer:
    effects = dependencies or CliDependencies()
    cli = typer.Typer(
        add_completion=False,
        help="A practical Bilibili CLI downloader.",
        invoke_without_command=True,
        no_args_is_help=False,
        pretty_exceptions_enable=False,
    )

    @cli.callback()
    def main(
        context: typer.Context,
        timeout: Annotated[
            float,
            typer.Option("--timeout", min=0.1, help="HTTP timeout in seconds."),
        ] = 30.0,
        proxy: Annotated[str | None, typer.Option("--proxy", help="HTTP proxy.")] = None,
        ffmpeg: Annotated[
            Path | None,
            typer.Option("--ffmpeg", help="Path to FFmpeg."),
        ] = None,
        version: Annotated[
            bool,
            typer.Option("--version", callback=_version_callback, is_eager=True),
        ] = False,
    ) -> None:
        """Run one VelaFetch command."""

        del version
        context.obj = RuntimeOptions(timeout=timeout, proxy=proxy, ffmpeg_path=ffmpeg)
        if context.invoked_subcommand is None:
            typer.echo(context.get_help())

    register_inspection_commands(cli, effects.media_service or MediaApplicationService())
    register_download_command(cli, effects.download_service or DownloadService())
    register_doctor_command(cli, effects.doctor_service or DoctorService())
    _ = main
    return cli


app = create_app()


def run() -> None:
    app()
