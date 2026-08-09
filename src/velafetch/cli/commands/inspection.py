"""The ``info`` and ``formats`` commands."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

import velafetch.cli.rendering as rendering
from velafetch.cli.dependencies import MediaService, runtime_options


def register_inspection_commands(cli: typer.Typer, service: MediaService) -> None:
    @cli.command()
    def info(
        context: typer.Context,
        source: Annotated[str, typer.Argument(help="BV, av, or a standard Bilibili URL.")],
        json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
    ) -> None:
        """Show basic video information."""

        options = runtime_options(context)
        try:
            item = asyncio.run(service.info(source, timeout=options.timeout, proxy=options.proxy))
            rendering.emit_info(item, json_output=json_output)
        except BaseException as error:
            rendering.emit_error(error, json_output=json_output)

    @cli.command()
    def formats(
        context: typer.Context,
        source: Annotated[str, typer.Argument(help="BV, av, or a standard Bilibili URL.")],
        json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
    ) -> None:
        """List video and audio tracks."""

        options = runtime_options(context)
        try:
            item = asyncio.run(
                service.formats(source, timeout=options.timeout, proxy=options.proxy)
            )
            rendering.emit_formats(item, json_output=json_output)
        except BaseException as error:
            rendering.emit_error(error, json_output=json_output)

    _ = info, formats
