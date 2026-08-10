"""Sequential media transfer with small, observable recovery rules."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from pathlib import Path

from velafetch.domain.models import MediaFormat, MediaKind
from velafetch.errors import DownloadError, NetworkOperationError
from velafetch.transport import HttpClient, RequestError

TrackProgressCallback = Callable[[MediaKind, int, int | None], None]

_MAX_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 0.5
_SATISFIED_RANGE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")
_UNSATISFIED_RANGE = re.compile(r"^bytes \*/(\d+)$")


class _RetryableTransfer(Exception):
    def __init__(self, status_code: int | None = None, *, discard_part: bool = False) -> None:
        self.status_code = status_code
        self.discard_part = discard_part


def _satisfied_range(value: str | None) -> tuple[int, int, int] | None:
    if value is None or (match := _SATISFIED_RANGE.fullmatch(value.strip())) is None:
        return None
    start, end, total = (int(part) for part in match.groups())
    if start > end or end >= total:
        return None
    return start, end, total


def _unsatisfied_total(value: str | None) -> int | None:
    if value is None or (match := _UNSATISFIED_RANGE.fullmatch(value.strip())) is None:
        return None
    total = int(match.group(1))
    return total if total > 0 else None


def _content_length(value: str | None) -> int | None:
    if value is None:
        return None
    if not value.isdecimal():
        raise _RetryableTransfer()
    return int(value)


def _part_size(path: Path) -> int:
    try:
        if not path.exists():
            return 0
        if not path.is_file():
            raise DownloadError("A partial download path is not a file.")
        return path.stat().st_size
    except OSError as error:
        raise DownloadError("The partial download could not be inspected.") from error


def _discard_part(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as error:
        raise DownloadError("The invalid partial download could not be removed.") from error


def _request_headers(track: MediaFormat, *, resume_from: int | None) -> dict[str, str]:
    headers = {**track.source.required_headers, "Accept-Encoding": "identity"}
    if resume_from is not None:
        headers["Range"] = f"bytes={resume_from}-"
    return headers


async def _probe_total(client: HttpClient, track: MediaFormat) -> int | None:
    headers = _request_headers(track, resume_from=0)
    headers["Range"] = "bytes=0-0"
    for url in track.source.urls:
        try:
            async with client.stream("GET", url, headers=headers) as response:
                if response.status_code == 206:
                    parsed = _satisfied_range(response.headers.get("content-range"))
                    if parsed is not None and parsed[:2] == (0, 0):
                        return parsed[2]
                elif response.status_code == 200:
                    total = _content_length(response.headers.get("content-length"))
                    if total is not None and total > 0:
                        return total
                elif response.status_code == 416:
                    total = _unsatisfied_total(response.headers.get("content-range"))
                    if total is not None:
                        return total
        except (RequestError, _RetryableTransfer):
            continue
    return None


async def _transfer_once(
    client: HttpClient,
    track: MediaFormat,
    url: str,
    part_path: Path,
    known_total: int | None,
    progress: TrackProgressCallback | None,
) -> int | None:
    resume_from = _part_size(part_path)
    headers = _request_headers(track, resume_from=resume_from if resume_from else None)
    async with client.stream("GET", url, headers=headers) as response:
        status = response.status_code
        expected_end: int | None = None
        if status == 416:
            raise _RetryableTransfer(status)

        if status == 200:
            expected_total = _content_length(response.headers.get("content-length"))
            mode = "wb"
            downloaded = 0
        elif status == 206:
            parsed = _satisfied_range(response.headers.get("content-range"))
            if parsed is None or parsed[0] != resume_from:
                raise _RetryableTransfer(status)
            _, range_end, expected_total = parsed
            expected_end = range_end + 1
            if known_total is not None and expected_total != known_total:
                raise _RetryableTransfer(status, discard_part=True)
            mode = "ab" if resume_from else "wb"
            downloaded = resume_from
        else:
            raise _RetryableTransfer(status)

        if expected_total is not None and expected_total <= 0:
            raise _RetryableTransfer(status, discard_part=True)
        if progress is not None:
            progress(track.kind, downloaded, expected_total)

        try:
            with part_path.open(mode) as output:
                async for chunk in response.aiter_content():
                    if not chunk:
                        continue
                    output.write(chunk)
                    downloaded += len(chunk)
                    if progress is not None:
                        progress(track.kind, downloaded, expected_total)
        except RequestError:
            raise
        except OSError as error:
            raise DownloadError(
                f"The partial {track.kind.value} file could not be written."
            ) from error

    if expected_end is not None:
        if downloaded < expected_end:
            raise _RetryableTransfer(status)
        if downloaded > expected_end:
            raise _RetryableTransfer(status, discard_part=True)
    if expected_total is None:
        if downloaded == 0:
            raise _RetryableTransfer(status, discard_part=True)
        return None
    if downloaded < expected_total:
        raise _RetryableTransfer(status)
    if downloaded > expected_total:
        raise _RetryableTransfer(status, discard_part=True)
    return expected_total


async def transfer_track(
    client: HttpClient,
    track: MediaFormat,
    part_path: Path,
    progress: TrackProgressCallback | None,
) -> Path:
    """Download one track, preserving useful bytes across failures and cancellation."""

    try:
        part_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise DownloadError("The partial download directory could not be created.") from error

    local_size = _part_size(part_path)
    known_total = await _probe_total(client, track) if local_size else None
    if known_total is not None:
        if local_size == known_total:
            if progress is not None:
                progress(track.kind, local_size, known_total)
            return part_path
        if local_size > known_total:
            _discard_part(part_path)

    last_status: int | None = None
    for attempt in range(_MAX_ATTEMPTS):
        if attempt:
            await asyncio.sleep(_RETRY_DELAY_SECONDS)
        url = track.source.urls[attempt % len(track.source.urls)]
        try:
            completed_total = await _transfer_once(
                client,
                track,
                url,
                part_path,
                known_total,
                progress,
            )
        except RequestError:
            continue
        except _RetryableTransfer as error:
            last_status = error.status_code
            if error.status_code == 416:
                remote_total = await _probe_total(client, track)
                current_size = _part_size(part_path)
                if remote_total is not None and current_size == remote_total:
                    if progress is not None:
                        progress(track.kind, current_size, remote_total)
                    return part_path
                _discard_part(part_path)
                known_total = remote_total
            elif error.discard_part:
                _discard_part(part_path)
                known_total = None
            continue
        if completed_total is not None:
            known_total = completed_total
        return part_path

    status_note = f" Last HTTP status: {last_status}." if last_status is not None else ""
    raise NetworkOperationError(
        f"The {track.kind.value} download failed after {_MAX_ATTEMPTS} attempts.{status_note}"
    )
