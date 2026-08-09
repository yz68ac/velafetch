"""The small environment check used by ``doctor``."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

import velafetch.cli.rendering as rendering
from velafetch.cli.dependencies import DoctorRunner, runtime_options


def register_doctor_command(cli: typer.Typer, service: DoctorRunner) -> None:
    @cli.command()
    def doctor(
        context: typer.Context,
        network: Annotated[bool, typer.Option("--network", help="Check Bilibili access.")] = False,
        json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
    ) -> None:
        """Check FFmpeg and optional network access."""

        options = runtime_options(context)
        try:
            report = asyncio.run(
                service.run(
                    ffmpeg_path=options.ffmpeg_path,
                    check_network=network,
                    timeout=options.timeout,
                    proxy=options.proxy,
                )
            )
            rendering.emit_doctor(report, json_output=json_output)
            if not report.ok:
                raise typer.Exit(1)
        except typer.Exit:
            raise
        except BaseException as error:
            rendering.emit_error(error, json_output=json_output)

    _ = doctor
