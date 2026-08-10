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
        source: Annotated[str, typer.Argument(help="Bilibili video, season, or list.")],
        item_index: Annotated[
            int | None,
            typer.Option("--item", min=1, help="Select an episode or collection item."),
        ] = None,
        page_index: Annotated[
            int | None,
            typer.Option("--page", min=1, help="Select a video page."),
        ] = None,
        json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
    ) -> None:
        """Show basic video information."""

        options = runtime_options(context)
        try:
            resource = asyncio.run(
                service.info(
                    source,
                    item_index=item_index,
                    page_index=page_index,
                    timeout=options.timeout,
                    proxy=options.proxy,
                    anonymous=options.anonymous,
                )
            )
            rendering.emit_info(resource, json_output=json_output)
        except BaseException as error:
            rendering.emit_error(error, json_output=json_output)

    @cli.command()
    def formats(
        context: typer.Context,
        source: Annotated[str, typer.Argument(help="Bilibili video, season, or list.")],
        item_index: Annotated[
            int | None,
            typer.Option("--item", min=1, help="Select an episode or collection item."),
        ] = None,
        page_index: Annotated[
            int | None,
            typer.Option("--page", min=1, help="Select a video page."),
        ] = None,
        json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
    ) -> None:
        """List video and audio tracks."""

        options = runtime_options(context)
        try:
            item = asyncio.run(
                service.formats(
                    source,
                    item_index=item_index,
                    page_index=page_index,
                    timeout=options.timeout,
                    proxy=options.proxy,
                    anonymous=options.anonymous,
                )
            )
            rendering.emit_formats(item, json_output=json_output)
        except BaseException as error:
            rendering.emit_error(error, json_output=json_output)

    _ = info, formats
