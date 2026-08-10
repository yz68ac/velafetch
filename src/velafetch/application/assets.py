"""Download and publish small cover, subtitle, and danmaku sidecars."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from enum import StrEnum
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

from velafetch.application.naming import safe_language, sidecar_path
from velafetch.domain.models import MediaSource
from velafetch.errors import DownloadError
from velafetch.extractors import ResolvedMedia, SubtitleTrack
from velafetch.extractors.bilibili.resources import public_source
from velafetch.transport import HttpClient, RequestError

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_ASSET_RETRY_DELAY = 0.5


class SubtitleOutputFormat(StrEnum):
    SRT = "srt"
    JSON = "json"


@dataclass(frozen=True, slots=True)
class SubtitleSelection:
    enabled: bool
    all_languages: bool
    languages: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class ArtifactResult:
    paths: tuple[Path, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    saved: int = 0

    def merge(self, other: ArtifactResult) -> ArtifactResult:
        return ArtifactResult(
            paths=(*self.paths, *other.paths),
            warnings=(*self.warnings, *other.warnings),
            errors=(*self.errors, *other.errors),
            saved=self.saved + other.saved,
        )


def parse_subtitle_selection(value: str) -> SubtitleSelection:
    normalized = value.strip()
    if normalized.casefold() == "off":
        return SubtitleSelection(False, False)
    if normalized.casefold() == "all":
        return SubtitleSelection(True, True)
    languages = frozenset(part.strip().casefold() for part in normalized.split(",") if part.strip())
    if not languages:
        raise DownloadError("--subtitles must be all, off, or a comma-separated language list.")
    return SubtitleSelection(True, False, languages)


def _retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        delay = float(value)
    except ValueError:
        try:
            delay = parsedate_to_datetime(value).timestamp() - time.time()
        except (TypeError, ValueError, OverflowError):
            return None
    return min(30.0, max(0.0, delay))


async def _read_asset(client: HttpClient, source: MediaSource, label: str) -> tuple[bytes, str]:
    headers = {**source.required_headers, "Accept-Encoding": "identity"}
    last_status: int | None = None
    for attempt in range(3):
        delay = _ASSET_RETRY_DELAY * (2**attempt)
        try:
            async with client.stream("GET", source.urls[0], headers=headers) as response:
                last_status = response.status_code
                if not 200 <= response.status_code < 300:
                    if response.status_code in _RETRYABLE_STATUS and attempt < 2:
                        retry_delay = _retry_after(response.headers.get("retry-after"))
                        delay = retry_delay if retry_delay is not None else delay
                    elif response.status_code in _RETRYABLE_STATUS:
                        break
                    else:
                        raise DownloadError(
                            f"The {label} request returned HTTP {response.status_code}."
                        )
                else:
                    chunks: list[bytes] = []
                    async for chunk in response.aiter_content():
                        if chunk:
                            chunks.append(chunk)
                    content = b"".join(chunks)
                    if not content:
                        raise DownloadError(f"The {label} response was empty.")
                    return content, response.headers.get("content-type", "")
        except RequestError:
            if attempt == 2:
                break
        await asyncio.sleep(delay)
    status_note = f" Last HTTP status: {last_status}." if last_status is not None else ""
    raise DownloadError(f"The {label} request failed after 3 attempts.{status_note}")


def _publish_bytes(target: Path, content: bytes, *, overwrite: bool) -> tuple[Path, bool]:
    if target.exists() and not overwrite:
        return target, False
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".part",
            dir=target.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(content)
            if target.exists() and not overwrite:
                return target, False
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    except OSError as error:
        raise DownloadError("A sidecar file could not be published.") from error
    return target, True


def _cover_extension(source: MediaSource) -> str:
    suffix = Path(urlsplit(source.urls[0]).path).suffix.casefold()
    return suffix if suffix in {".jpg", ".jpeg", ".png", ".webp"} else ".jpg"


async def download_cover(
    client: HttpClient,
    unit: ResolvedMedia,
    output_root: Path,
    stem: str,
    *,
    overwrite: bool,
) -> ArtifactResult:
    source = unit.page.cover or unit.item.cover
    if source is None:
        return ArtifactResult(warnings=("No public cover is available.",))
    target = sidecar_path(output_root, stem, f".cover{_cover_extension(source)}")
    if target.exists() and not overwrite:
        return ArtifactResult(paths=(target,))
    try:
        content, content_type = await _read_asset(client, source, "cover")
        if content_type and not content_type.casefold().startswith("image/"):
            raise DownloadError("The cover response is not an image.")
        path, saved = _publish_bytes(target, content, overwrite=overwrite)
        return ArtifactResult(paths=(path,), saved=int(saved))
    except DownloadError as error:
        return ArtifactResult(warnings=(str(error),))


def _subtitle_payload(content: bytes) -> tuple[dict[str, object], list[dict[str, object]]]:
    try:
        value = cast("object", json.loads(content))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DownloadError("A subtitle response is not valid JSON.") from error
    if not isinstance(value, dict) or not isinstance(value.get("body"), list):
        raise DownloadError("A subtitle response has no body list.")
    payload = cast("dict[str, object]", value)
    body: list[dict[str, object]] = []
    for raw in cast("list[object]", payload["body"]):
        if not isinstance(raw, dict):
            raise DownloadError("A subtitle cue is invalid.")
        body.append(cast("dict[str, object]", raw))
    return payload, body


def _timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


def _srt(body: list[dict[str, object]]) -> bytes:
    cues: list[tuple[float, float, int, str]] = []
    for index, cue in enumerate(body):
        start, end, content = cue.get("from"), cue.get("to"), cue.get("content")
        if (
            isinstance(start, bool)
            or not isinstance(start, (int, float))
            or isinstance(end, bool)
            or not isinstance(end, (int, float))
            or not isinstance(content, str)
            or end < start
        ):
            raise DownloadError("A subtitle cue has invalid timing or text.")
        cues.append((float(start), float(end), index, content.replace("\r\n", "\n")))
    cues.sort(key=lambda cue: (cue[0], cue[1], cue[2]))
    blocks = [
        f"{number}\n{_timestamp(start)} --> {_timestamp(end)}\n{text}\n"
        for number, (start, end, _, text) in enumerate(cues, start=1)
    ]
    return "\n".join(blocks).encode("utf-8-sig")


async def download_subtitles(
    client: HttpClient,
    tracks: tuple[SubtitleTrack, ...],
    selection: SubtitleSelection,
    output_format: SubtitleOutputFormat,
    output_root: Path,
    stem: str,
    *,
    overwrite: bool,
) -> ArtifactResult:
    if not selection.enabled:
        return ArtifactResult()
    selected = tuple(
        track
        for track in tracks
        if selection.all_languages or track.language.casefold() in selection.languages
    )
    missing = (
        selection.languages - {track.language.casefold() for track in selected}
        if not selection.all_languages
        else frozenset()
    )
    result = ArtifactResult(
        errors=tuple(
            f"The requested subtitle language is unavailable: {lang}." for lang in sorted(missing)
        )
    )
    language_counts: dict[str, int] = {}
    for track in selected:
        language = safe_language(track.language)
        language_counts[language] = language_counts.get(language, 0) + 1
        suffix_language = (
            language
            if language_counts[language] == 1
            else f"{language}-{safe_language(track.track_id)}"
        )
        target = sidecar_path(output_root, stem, f".{suffix_language}.{output_format.value}")
        if target.exists() and not overwrite:
            result = result.merge(ArtifactResult(paths=(target,)))
            continue
        try:
            content, _ = await _read_asset(client, track.source, "subtitle")
            payload, body = _subtitle_payload(content)
            rendered = (
                _srt(body)
                if output_format is SubtitleOutputFormat.SRT
                else (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            )
            path, saved = _publish_bytes(target, rendered, overwrite=overwrite)
            result = result.merge(ArtifactResult(paths=(path,), saved=int(saved)))
        except DownloadError as error:
            result = result.merge(ArtifactResult(errors=(str(error),)))
    return result


async def download_danmaku(
    client: HttpClient,
    unit: ResolvedMedia,
    output_root: Path,
    stem: str,
    *,
    overwrite: bool,
) -> ArtifactResult:
    referer = unit.page.canonical_url or unit.item.ref.canonical_url
    source = public_source(
        f"https://api.bilibili.com/x/v1/dm/list.so?oid={unit.page.page_id}",
        referer=referer,
    )
    target = sidecar_path(output_root, stem, ".danmaku.xml")
    if target.exists() and not overwrite:
        return ArtifactResult(paths=(target,))
    try:
        content, _ = await _read_asset(client, source, "danmaku")
        if not content.lstrip().startswith((b"<?xml", b"<i>")):
            raise DownloadError("The danmaku response is not recognized XML.")
        path, saved = _publish_bytes(target, content, overwrite=overwrite)
        return ArtifactResult(paths=(path,), saved=int(saved))
    except DownloadError as error:
        return ArtifactResult(errors=(str(error),))
