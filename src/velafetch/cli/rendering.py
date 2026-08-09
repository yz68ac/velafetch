"""Human tables and small JSON objects for CLI output."""

from __future__ import annotations

import asyncio
import json
from typing import Never

import typer
from rich.console import Console
from rich.table import Table

from velafetch.application import DoctorReport
from velafetch.domain.models import MediaFormat, MediaItem
from velafetch.errors import VelaFetchError


def emit_error(error: BaseException, *, json_output: bool) -> Never:
    if isinstance(error, (KeyboardInterrupt, asyncio.CancelledError)):
        message, code = "Operation cancelled.", 130
    elif isinstance(error, VelaFetchError):
        message, code = str(error), 1
    else:
        message, code = f"{type(error).__name__}: {error}", 1
    if json_output:
        typer.echo(json.dumps({"error": message}, ensure_ascii=False), err=True)
    else:
        Console(stderr=True).print(f"[bold red]Error:[/] {message}")
    raise typer.Exit(code)


def _duration(milliseconds: int) -> str:
    seconds = milliseconds // 1000
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _format_dict(track: MediaFormat) -> dict[str, object]:
    return {
        "id": track.format_id,
        "kind": track.kind.value,
        "container": track.container,
        "codec": track.codec,
        "codec_family": track.codec_family.value,
        "bitrate": track.bitrate,
        "quality": track.quality_label,
        "width": track.width,
        "height": track.height,
        "fps": (
            f"{track.frame_rate_numerator}/{track.frame_rate_denominator}"
            if track.frame_rate_numerator and track.frame_rate_denominator
            else None
        ),
        "supported": track.download_supported,
        "reason": track.unsupported_reason,
    }


def emit_info(item: MediaItem, *, json_output: bool) -> None:
    page = item.pages[0]
    data = {
        "site": item.ref.site.value,
        "id": item.ref.canonical_id,
        "url": str(item.ref.canonical_url),
        "title": item.title,
        "duration_ms": item.duration_ms,
        "page": {"index": page.index, "title": page.title},
    }
    if json_output:
        typer.echo(json.dumps(data, ensure_ascii=False))
        return
    table = Table(title="Media Information", show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")
    for label, value in (
        ("ID", item.ref.canonical_id),
        ("URL", str(item.ref.canonical_url)),
        ("Title", item.title),
        ("Duration", _duration(item.duration_ms)),
        ("Page", page.title),
    ):
        table.add_row(label, value)
    Console().print(table)


def emit_formats(item: MediaItem, *, json_output: bool) -> None:
    tracks = item.pages[0].formats
    if json_output:
        typer.echo(
            json.dumps(
                {"id": item.ref.canonical_id, "formats": [_format_dict(t) for t in tracks]},
                ensure_ascii=False,
            )
        )
        return
    table = Table(title=f"Available Formats — {item.ref.canonical_id}")
    for name in ("ID", "Kind", "Quality", "Codec", "Resolution", "Bitrate", "Supported"):
        table.add_column(name)
    for track in tracks:
        table.add_row(
            track.format_id,
            track.kind.value,
            track.quality_label or "—",
            track.codec_family.value,
            f"{track.width}x{track.height}" if track.width and track.height else "—",
            f"{track.bitrate / 1000:.0f} kbps",
            "yes" if track.download_supported else "no",
        )
    Console().print(table)


def emit_doctor(report: DoctorReport, *, json_output: bool) -> None:
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "ok": report.ok,
                    "checks": [
                        {"name": c.name, "status": c.status, "message": c.message}
                        for c in report.checks
                    ],
                }
            )
        )
        return
    table = Table(title="VelaFetch Doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Message")
    for check in report.checks:
        table.add_row(check.name, check.status, check.message)
    Console().print(table)
