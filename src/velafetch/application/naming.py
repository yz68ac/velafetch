"""Concrete cross-platform names for media, partials, and sidecars."""

from __future__ import annotations

import hashlib
import re
import string
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from velafetch.domain.models import MediaResourceKind, OutputMode
from velafetch.errors import DownloadError
from velafetch.extractors import ResolvedMedia
from velafetch.selection import TrackSelection

_INVALID_FILENAME = re.compile(r'[\x00-\x1f<>:"/\\|?*]')
_RESERVED = {"con", "prn", "aux", "nul"} | {
    f"{prefix}{number}" for prefix in ("com", "lpt") for number in range(1, 10)
}
_ALLOWED_TEMPLATE_FIELDS = {"source_title", "title", "part_title", "id", "item", "page"}
_MAX_COMPONENT = 240


def _units(value: str) -> tuple[int, int]:
    return len(value.encode("utf-8")), len(value.encode("utf-16-le")) // 2


def _fits(value: str) -> bool:
    utf8, utf16 = _units(value)
    return utf8 <= _MAX_COMPONENT and utf16 <= _MAX_COMPONENT


def _truncate(value: str, suffix: str = "") -> str:
    candidate = f"{value}{suffix}"
    if _fits(candidate):
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    marker = f"-{digest}"
    kept: list[str] = []
    for character in value:
        trial = f"{''.join(kept)}{character}{marker}{suffix}"
        if not _fits(trial):
            break
        kept.append(character)
    return f"{''.join(kept).rstrip()}{marker}"


def safe_filename(title: str, fallback: str) -> str:
    """Clean a filename stem without allowing path construction."""

    cleaned = _INVALID_FILENAME.sub("_", unicodedata.normalize("NFC", title))
    cleaned = cleaned.strip().rstrip(".") or fallback
    if cleaned.split(".", 1)[0].casefold() in _RESERVED:
        cleaned = f"_{cleaned}"
    return _truncate(cleaned)


def safe_language(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", unicodedata.normalize("NFC", value)).strip("._")
    return safe_filename(cleaned or "und", "und")


@dataclass(frozen=True, slots=True)
class TemplateContext:
    source_title: str
    title: str
    part_title: str
    id: str
    item: int
    page: int


def render_template(template: str, context: TemplateContext) -> str:
    formatter = string.Formatter()
    if not template or "/" in template or "\\" in template:
        raise DownloadError("The output template must describe one filename, not a path.")
    try:
        parsed = tuple(formatter.parse(template))
    except ValueError as error:
        raise DownloadError("The output template is malformed.") from error
    for _, field, _, conversion in parsed:
        if field is not None and field not in _ALLOWED_TEMPLATE_FIELDS:
            raise DownloadError(f"The output template uses an unknown field: {field}.")
        if conversion is not None:
            raise DownloadError("Output template conversions are not supported.")
    values: dict[str, str | int] = {
        "source_title": safe_filename(context.source_title, context.id),
        "title": safe_filename(context.title, context.id),
        "part_title": safe_filename(context.part_title, context.id),
        "id": safe_filename(context.id, "media"),
        "item": context.item,
        "page": context.page,
    }
    try:
        rendered = formatter.vformat(template, (), values)
    except (KeyError, ValueError) as error:
        raise DownloadError("The output template has an invalid format specifier.") from error
    return safe_filename(rendered, context.id)


def default_stem(unit: ResolvedMedia, *, batch: bool) -> str:
    page = unit.page
    item = unit.item
    if unit.resource_kind is MediaResourceKind.VIDEO:
        if len(item.pages) == 1:
            value = item.title
        elif batch:
            value = f"P{page.index:02d} - {page.title}"
        else:
            value = f"{item.title} - P{page.index:02d} - {page.title}"
    elif unit.resource_kind is MediaResourceKind.BANGUMI_SEASON:
        prefix = f"E{unit.item_index:02d} - {item.title}"
        value = prefix if batch else f"{unit.source_title} - {prefix}"
    else:
        prefix = f"{unit.item_index:02d} - {item.title}"
        if len(item.pages) > 1:
            prefix = f"{prefix} - P{page.index:02d} - {page.title}"
        value = prefix if batch else f"{unit.source_title} - {prefix}"
    return safe_filename(value, item.ref.canonical_id)


def unit_stem(unit: ResolvedMedia, *, batch: bool, template: str | None) -> str:
    if template is None:
        return default_stem(unit, batch=batch)
    return render_template(
        template,
        TemplateContext(
            source_title=unit.source_title,
            title=unit.item.title,
            part_title=unit.page.title,
            id=unit.item.ref.canonical_id,
            item=unit.item_index,
            page=unit.page_index,
        ),
    )


def batch_output_root(output_root: Path, unit: ResolvedMedia) -> Path:
    return output_root / safe_filename(unit.source_title, unit.source_id)


def _named_path(root: Path, stem: str, suffix: str) -> Path:
    fitted = _truncate(stem, suffix)
    return root / f"{fitted}{suffix}"


def target_paths(
    output_root: Path,
    stem: str,
    selection: TrackSelection,
    mode: OutputMode,
) -> tuple[Path, ...]:
    if mode is OutputMode.MUXED:
        return (_named_path(output_root, stem, ".mp4"),)
    if mode is OutputMode.VIDEO_ONLY:
        assert selection.video is not None
        return (_named_path(output_root, stem, f".video.{selection.video.container}"),)
    if mode is OutputMode.AUDIO_ONLY:
        assert selection.audio is not None
        return (_named_path(output_root, stem, f".audio.{selection.audio.container}"),)
    assert selection.video is not None and selection.audio is not None
    return (
        _named_path(output_root, stem, f".video.{selection.video.container}"),
        _named_path(output_root, stem, f".audio.{selection.audio.container}"),
    )


def partial_path(output_root: Path, unit: ResolvedMedia, format_id: str, container: str) -> Path:
    if unit.resource_kind is MediaResourceKind.BANGUMI_SEASON:
        segment = f"ep-{unit.page.episode_id}"
    elif unit.resource_kind is MediaResourceKind.VIDEO:
        segment = f"page-{unit.page_index}"
    else:
        segment = f"{unit.item.ref.canonical_id}/page-{unit.page_index}"
    return output_root / ".velafetch" / unit.source_id / segment / f"{format_id}.{container}.part"


def sidecar_path(output_root: Path, stem: str, suffix: str) -> Path:
    return _named_path(output_root, stem, suffix)
