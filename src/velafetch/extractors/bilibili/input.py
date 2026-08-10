"""Strict parsing for public Bilibili video, season, episode, and list inputs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import parse_qs, urlencode, urlsplit

from velafetch.errors import UnsupportedFeatureError

_BV_PATTERN = re.compile(r"^(?i:BV)([A-Za-z0-9]{9,10})$")
_AV_PATTERN = re.compile(r"^(?i:av)([0-9]+)$")
_SEASON_PATTERN = re.compile(r"^(?i:ss)([0-9]+)$")
_EPISODE_PATTERN = re.compile(r"^(?i:ep)([0-9]+)$")


class BilibiliInputKind(StrEnum):
    VIDEO = "video"
    BANGUMI_SEASON = "bangumi_season"
    BANGUMI_EPISODE = "bangumi_episode"
    UGC_SEASON = "ugc_season"
    UGC_SERIES = "ugc_series"


@dataclass(frozen=True, slots=True)
class BilibiliInput:
    """A validated source before its full public metadata is fetched."""

    kind: BilibiliInputKind
    normalized_input: str
    bvid: str | None = None
    avid: int | None = None
    season_id: int | None = None
    episode_id: int | None = None
    mid: int | None = None
    collection_id: int | None = None
    selected_page: int | None = None


def is_bvid(value: str) -> bool:
    return _BV_PATTERN.fullmatch(value) is not None


def _unsupported_source() -> UnsupportedFeatureError:
    return UnsupportedFeatureError(
        "The source is not a supported public Bilibili input.",
        {"reason": "unsupported_source"},
    )


def _positive(value: str) -> int:
    if not value.isdecimal() or (number := int(value)) <= 0:
        raise _unsupported_source()
    return number


def _identifier(value: str, *, normalized_as_url: bool) -> BilibiliInput:
    if match := _BV_PATTERN.fullmatch(value):
        bvid = f"BV{match.group(1)}"
        normalized = f"https://www.bilibili.com/video/{bvid}" if normalized_as_url else bvid
        return BilibiliInput(BilibiliInputKind.VIDEO, normalized, bvid=bvid)
    if match := _AV_PATTERN.fullmatch(value):
        avid = _positive(match.group(1))
        token = f"av{avid}"
        normalized = f"https://www.bilibili.com/video/{token}" if normalized_as_url else token
        return BilibiliInput(BilibiliInputKind.VIDEO, normalized, avid=avid)
    if match := _SEASON_PATTERN.fullmatch(value):
        season_id = _positive(match.group(1))
        token = f"ss{season_id}"
        normalized = (
            f"https://www.bilibili.com/bangumi/play/{token}" if normalized_as_url else token
        )
        return BilibiliInput(
            BilibiliInputKind.BANGUMI_SEASON,
            normalized,
            season_id=season_id,
        )
    if match := _EPISODE_PATTERN.fullmatch(value):
        episode_id = _positive(match.group(1))
        token = f"ep{episode_id}"
        normalized = (
            f"https://www.bilibili.com/bangumi/play/{token}" if normalized_as_url else token
        )
        return BilibiliInput(
            BilibiliInputKind.BANGUMI_EPISODE,
            normalized,
            episode_id=episode_id,
        )
    raise _unsupported_source()


def _query_index(query: dict[str, list[str]], name: str) -> int | None:
    values = query.get(name)
    if values is None:
        return None
    if len(values) != 1:
        raise _unsupported_source()
    return _positive(values[0])


def _parse_www(path: str, query: dict[str, list[str]]) -> BilibiliInput:
    segments = path.rstrip("/").split("/")
    if len(segments) == 3 and segments[:2] == ["", "video"]:
        parsed = _identifier(segments[2], normalized_as_url=True)
        if parsed.kind is not BilibiliInputKind.VIDEO:
            raise _unsupported_source()
        selected_page = _query_index(query, "p")
        normalized = parsed.normalized_input
        if selected_page not in {None, 1}:
            normalized = f"{normalized}?{urlencode({'p': selected_page})}"
        return BilibiliInput(
            parsed.kind,
            normalized,
            bvid=parsed.bvid,
            avid=parsed.avid,
            selected_page=selected_page,
        )
    if len(segments) == 4 and segments[:3] == ["", "bangumi", "play"]:
        parsed = _identifier(segments[3], normalized_as_url=True)
        if parsed.kind not in {
            BilibiliInputKind.BANGUMI_SEASON,
            BilibiliInputKind.BANGUMI_EPISODE,
        }:
            raise _unsupported_source()
        return parsed
    raise _unsupported_source()


def _parse_space(path: str, query: dict[str, list[str]]) -> BilibiliInput:
    segments = path.rstrip("/").split("/")
    if len(segments) != 4 or segments[2] != "lists":
        raise _unsupported_source()
    mid = _positive(segments[1])
    collection_id = _positive(segments[3])
    list_types = query.get("type")
    if list_types is None or len(list_types) != 1 or list_types[0] not in {"season", "series"}:
        raise _unsupported_source()
    list_type = list_types[0]
    kind = BilibiliInputKind.UGC_SEASON if list_type == "season" else BilibiliInputKind.UGC_SERIES
    normalized = (
        f"https://space.bilibili.com/{mid}/lists/{collection_id}?{urlencode({'type': list_type})}"
    )
    return BilibiliInput(
        kind,
        normalized,
        mid=mid,
        collection_id=collection_id,
    )


def parse_bilibili_input(source: str) -> BilibiliInput:
    """Normalize one accepted public input and discard tracking parameters."""

    value = source.strip()
    if not value:
        raise _unsupported_source()
    if "://" not in value:
        return _identifier(value, normalized_as_url=False)

    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise _unsupported_source() from error
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or "%" in parsed.path
    ):
        raise _unsupported_source()

    query = parse_qs(parsed.query, keep_blank_values=True)
    hostname = (parsed.hostname or "").lower()
    if hostname == "www.bilibili.com":
        return _parse_www(parsed.path, query)
    if hostname == "space.bilibili.com":
        return _parse_space(parsed.path, query)
    raise _unsupported_source()
