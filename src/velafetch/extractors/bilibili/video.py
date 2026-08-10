"""Projection of ordinary Bilibili video metadata and pages."""

from __future__ import annotations

from typing import cast

from velafetch.domain.models import MediaItem, MediaPage, MediaRef, MediaResourceKind, Site
from velafetch.errors import ExtractionError, UnsupportedFeatureError
from velafetch.extractors.bilibili.input import is_bvid
from velafetch.extractors.bilibili.payload import (
    JsonMapping,
    mapping,
    required_int,
    required_string,
    sequence,
)
from velafetch.extractors.bilibili.resources import public_source


def project_video_metadata(
    data: JsonMapping,
    *,
    normalized_input: str,
    selected_page: int,
) -> MediaItem:
    redirect_url = data.get("redirect_url")
    if isinstance(redirect_url, str) and "/bangumi/" in redirect_url:
        raise UnsupportedFeatureError(
            "This video redirects to a Bangumi episode; use its ss or ep input.",
            {"reason": "bangumi_redirect"},
        )
    rights_value = data.get("rights")
    if isinstance(rights_value, dict):
        rights = cast("JsonMapping", rights_value)
        if any(rights.get(name) == 1 for name in ("pay", "arc_pay", "is_stein_gate")):
            raise UnsupportedFeatureError(
                "This Bilibili content type is not publicly downloadable.",
                {"reason": "restricted_content"},
            )

    bvid = required_string(data, "bvid", stage="metadata")
    if not is_bvid(bvid):
        raise ExtractionError("The Bilibili API returned an invalid canonical identifier.")
    avid = required_int(data, "aid", stage="metadata", minimum=1)
    title = required_string(data, "title", stage="metadata").strip()
    duration = required_int(data, "duration", stage="metadata")
    canonical_url = f"https://www.bilibili.com/video/{bvid}"
    cover_value = data.get("pic")
    cover = (
        public_source(cover_value, referer=canonical_url)
        if isinstance(cover_value, str) and cover_value
        else None
    )

    page_values = sequence(data.get("pages"), stage="metadata", field="pages")
    if not page_values:
        raise ExtractionError("The Bilibili video has no playable pages.")
    pages: list[MediaPage] = []
    seen_indexes: set[int] = set()
    for position, value in enumerate(page_values, start=1):
        page_data = mapping(value, stage="metadata", field=f"pages[{position - 1}]")
        index = required_int(page_data, "page", stage="metadata", minimum=1)
        if index in seen_indexes:
            raise ExtractionError("The Bilibili video contains duplicate page indexes.")
        seen_indexes.add(index)
        cid = required_int(page_data, "cid", stage="metadata", minimum=1)
        page_duration = required_int(page_data, "duration", stage="metadata")
        part = required_string(page_data, "part", stage="metadata").strip() or title
        page_url = canonical_url if index == 1 else f"{canonical_url}?p={index}"
        pages.append(
            MediaPage(
                index=index,
                page_id=str(cid),
                title=part,
                duration_ms=page_duration * 1000,
                avid=avid,
                bvid=bvid,
                canonical_url=page_url,
                cover=cover,
            )
        )
    if seen_indexes != set(range(1, len(pages) + 1)):
        raise ExtractionError("The Bilibili video page indexes are not contiguous.")
    if selected_page not in seen_indexes:
        raise ExtractionError("The selected Bilibili video page does not exist.")

    return MediaItem(
        ref=MediaRef(
            site=Site.BILIBILI,
            kind=MediaResourceKind.VIDEO,
            canonical_id=bvid,
            canonical_url=canonical_url,
            normalized_input=normalized_input,
            page_index=selected_page,
            avid=avid,
        ),
        title=title,
        duration_ms=duration * 1000,
        pages=tuple(pages),
        cover=cover,
    )
