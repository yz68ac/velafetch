"""Human tables and small JSON objects for CLI output."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Never

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TaskID,
    TextColumn,
    TransferSpeedColumn,
)
from rich.table import Table

from velafetch.application import (
    DoctorReport,
    DownloadResult,
    ProgressCallback,
    ProgressUpdate,
)
from velafetch.domain.models import MediaCollection, MediaFormat, MediaKind, MediaPage
from velafetch.errors import VelaFetchError
from velafetch.extractors import MediaResource, ResolvedMedia


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


@contextmanager
def download_progress() -> Iterator[ProgressCallback]:
    progress = Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        console=Console(stderr=True),
    )
    tasks: dict[tuple[int, MediaKind], TaskID] = {}

    def update(event: ProgressUpdate) -> None:
        key = (event.unit_number, event.kind)
        task_id = tasks.get(key)
        if task_id is None:
            description = (
                f"({event.unit_number}/{event.unit_count}) {event.label} · "
                f"{event.kind.value.capitalize()}"
            )
            task_id = progress.add_task(description, total=event.total)
            tasks[key] = task_id
        progress.update(task_id, completed=event.downloaded, total=event.total)

    with progress:
        yield update


def emit_download(result: DownloadResult, *, json_output: bool) -> None:
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "ok": result.ok,
                    "aborted": result.aborted,
                    "items": [
                        {
                            "id": item.media_id,
                            "title": item.title,
                            "item": item.item_index,
                            "page": item.page_index,
                            "status": item.status.value,
                            "outputs": [str(path) for path in item.output_paths],
                            "warnings": list(item.warnings),
                            "error": item.error,
                        }
                        for item in result.items
                    ],
                },
                ensure_ascii=False,
            )
        )
        return
    if len(result.items) == 1:
        item = result.items[0]
        prefix = item.status.value.capitalize()
        for path in item.output_paths:
            typer.echo(f"{prefix}: {path}")
        for warning in item.warnings:
            Console(stderr=True).print(f"[yellow]Warning:[/] {warning}")
        if item.error is not None:
            Console(stderr=True).print(f"[bold red]Error:[/] {item.error}")
        return
    table = Table(title="Download Summary")
    for name in ("Item", "Page", "ID", "Title", "Status", "Message"):
        table.add_column(name)
    for item in result.items:
        message = item.error or "; ".join(item.warnings) or "—"
        table.add_row(
            str(item.item_index),
            str(item.page_index),
            item.media_id,
            item.title,
            item.status.value,
            message,
        )
    Console().print(table)


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
        "dynamic_range": track.dynamic_range.value,
        "supported": track.download_supported,
        "reason": track.unsupported_reason,
    }


def _page_dict(page: MediaPage) -> dict[str, object]:
    return {
        "index": page.index,
        "title": page.title,
        "duration_ms": page.duration_ms,
    }


def emit_info(resource: MediaResource, *, json_output: bool) -> None:
    if isinstance(resource, MediaCollection):
        selected = resource.entries[resource.selected_index - 1]
        data = {
            "site": resource.ref.site.value,
            "kind": resource.ref.kind.value,
            "id": resource.ref.canonical_id,
            "url": resource.ref.canonical_url,
            "title": resource.title,
            "selected_item": resource.selected_index,
            "selected_page": resource.selected_page,
            "entries": [
                {
                    "index": entry.index,
                    "id": entry.entry_id,
                    "url": entry.canonical_url,
                    "title": entry.title,
                    "duration_ms": entry.duration_ms,
                }
                for entry in resource.entries
            ],
        }
        if json_output:
            typer.echo(json.dumps(data, ensure_ascii=False))
            return
        table = Table(title="Media Collection", show_header=False)
        table.add_column("Field", style="bold")
        table.add_column("Value")
        for label, value in (
            ("Kind", resource.ref.kind.value),
            ("ID", resource.ref.canonical_id),
            ("URL", resource.ref.canonical_url),
            ("Title", resource.title),
            ("Items", str(len(resource.entries))),
            ("Selected", selected.title),
        ):
            table.add_row(label, value)
        Console().print(table)
        entries = Table(title="Entries")
        for name in ("Selected", "Index", "ID", "Title", "Duration"):
            entries.add_column(name)
        for entry in resource.entries:
            entries.add_row(
                "*" if entry.index == resource.selected_index else "",
                str(entry.index),
                entry.entry_id,
                entry.title,
                _duration(entry.duration_ms),
            )
        Console().print(entries)
        return

    item = resource
    page = item.pages[item.ref.page_index - 1]
    data = {
        "site": item.ref.site.value,
        "kind": item.ref.kind.value,
        "id": item.ref.canonical_id,
        "url": str(item.ref.canonical_url),
        "title": item.title,
        "duration_ms": item.duration_ms,
        "page": _page_dict(page),
        "selected_page": page.index,
        "pages": [_page_dict(value) for value in item.pages],
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
    if len(item.pages) > 1:
        pages = Table(title="Pages")
        for name in ("Selected", "Index", "Title", "Duration"):
            pages.add_column(name)
        for value in item.pages:
            pages.add_row(
                "*" if value.index == page.index else "",
                str(value.index),
                value.title,
                _duration(value.duration_ms),
            )
        Console().print(pages)


def emit_formats(resolved: ResolvedMedia, *, json_output: bool) -> None:
    item = resolved.item
    tracks = resolved.page.formats
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "kind": resolved.resource_kind.value,
                    "source_id": resolved.source_id,
                    "id": item.ref.canonical_id,
                    "item": resolved.item_index,
                    "page": resolved.page_index,
                    "formats": [_format_dict(t) for t in tracks],
                },
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
