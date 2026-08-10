"""Small shared resource types for Bilibili resolution."""

from __future__ import annotations

from dataclasses import dataclass, replace
from urllib.parse import urlsplit, urlunsplit

from velafetch.domain.models import (
    MediaCollection,
    MediaItem,
    MediaPage,
    MediaResourceKind,
    MediaSource,
)
from velafetch.errors import ExtractionError, SelectionError

type MediaResource = MediaItem | MediaCollection


def public_source(url: str, *, referer: str | None = None) -> MediaSource:
    """Normalize a public asset URL while keeping it out of serialization and repr."""

    value = f"https:{url}" if url.startswith("//") else url
    try:
        parsed = urlsplit(value)
    except ValueError as error:
        raise ExtractionError("Bilibili returned an invalid public asset URL.") from error
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ExtractionError("Bilibili returned an invalid public asset URL.")
    normalized = urlunsplit(("https", parsed.netloc, parsed.path, parsed.query, ""))
    headers = {"Referer": referer} if referer is not None else {}
    return MediaSource(urls=(normalized,), required_headers=headers)


def choose_index(requested: int | None, default: int | None, count: int, *, label: str) -> int:
    selected = requested if requested is not None else default or 1
    if selected < 1 or selected > count:
        raise SelectionError(
            f"The selected {label} is outside the available range.",
            {"selection": label, "requested": selected, "available": count},
        )
    return selected


@dataclass(frozen=True, slots=True)
class ResolvedMedia:
    """One concrete video page with its enclosing source context."""

    resource_kind: MediaResourceKind
    source_id: str
    source_title: str
    source_url: str
    item_index: int
    item_count: int
    item: MediaItem
    page_index: int

    @property
    def page(self) -> MediaPage:
        return next(page for page in self.item.pages if page.index == self.page_index)

    def with_item(self, item: MediaItem) -> ResolvedMedia:
        return replace(self, item=item)
