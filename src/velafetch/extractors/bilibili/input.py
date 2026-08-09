"""Validation and normalization for the three public Bilibili input forms."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from velafetch.errors import UnsupportedFeatureError

_BV_PATTERN = re.compile(r"^(?i:BV)([A-Za-z0-9]{9,10})$")
_AV_PATTERN = re.compile(r"^(?i:av)([0-9]+)$")


@dataclass(frozen=True, slots=True)
class BilibiliInput:
    """A validated source before the canonical BV identity is fetched."""

    bvid: str | None
    avid: int | None
    normalized_input: str

    def __post_init__(self) -> None:
        if (self.bvid is None) == (self.avid is None):
            raise ValueError("exactly one Bilibili identifier is required")


def is_bvid(value: str) -> bool:
    """Return whether an API value has one of the supported BV shapes."""

    return _BV_PATTERN.fullmatch(value) is not None


def _unsupported_source() -> UnsupportedFeatureError:
    return UnsupportedFeatureError(
        "The source is not a supported Bilibili video input.",
        {"reason": "unsupported_source"},
    )


def _parse_identifier(value: str, *, normalized_as_url: bool) -> BilibiliInput:
    bv_match = _BV_PATTERN.fullmatch(value)
    if bv_match is not None:
        bvid = f"BV{bv_match.group(1)}"
        normalized = f"https://www.bilibili.com/video/{bvid}" if normalized_as_url else bvid
        return BilibiliInput(bvid=bvid, avid=None, normalized_input=normalized)

    av_match = _AV_PATTERN.fullmatch(value)
    if av_match is not None:
        avid = int(av_match.group(1))
        if avid <= 0:
            raise _unsupported_source()
        identifier = f"av{avid}"
        normalized = (
            f"https://www.bilibili.com/video/{identifier}" if normalized_as_url else identifier
        )
        return BilibiliInput(bvid=None, avid=avid, normalized_input=normalized)
    raise _unsupported_source()


def parse_bilibili_input(source: str) -> BilibiliInput:
    """Parse the ordinary single-page input forms supported by this project."""

    value = source.strip()
    if not value:
        raise _unsupported_source()
    if "://" not in value:
        return _parse_identifier(value, normalized_as_url=False)

    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise _unsupported_source() from error
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or (parsed.hostname or "").lower() != "www.bilibili.com"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or "%" in parsed.path
    ):
        raise _unsupported_source()

    path = parsed.path.rstrip("/")
    segments = path.split("/")
    if len(segments) != 3 or segments[:2] != ["", "video"]:
        raise _unsupported_source()
    query = parse_qs(parsed.query, keep_blank_values=True)
    if "p" in query and any(page != "1" for page in query["p"]):
        raise UnsupportedFeatureError(
            "Multi-page video selection is not supported until M6.",
            {"reason": "multi_page"},
        )
    return _parse_identifier(segments[2], normalized_as_url=True)
