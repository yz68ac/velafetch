"""High-level orchestration for public single-page Bilibili inspection."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import cast
from urllib.parse import urlencode

import httpx

from velafetch.domain.models import MediaItem, MediaPage, MediaRef, Site
from velafetch.errors import ExtractionError, NetworkOperationError, UnsupportedFeatureError
from velafetch.extractors.bilibili.input import (
    BilibiliInput,
    is_bvid,
    parse_bilibili_input,
)
from velafetch.extractors.bilibili.payload import (
    JsonMapping,
    api_code,
    api_data,
    mapping,
    read_json_response,
    required_int,
    required_string,
    sequence,
)
from velafetch.extractors.bilibili.projection import project_formats
from velafetch.extractors.bilibili.wbi import (
    WBI_REJECTED_CODE,
    mixin_key_from_urls,
    sign_wbi_query,
)

Clock = Callable[[], int]

_VIEW_ENDPOINT = "https://api.bilibili.com/x/web-interface/view"
_NAV_ENDPOINT = "https://api.bilibili.com/x/web-interface/nav"
_PLAY_ENDPOINT = "https://api.bilibili.com/x/player/wbi/playurl"


class BilibiliExtractor:
    """Fetch and project public single-page Bilibili responses."""

    def __init__(self, http_client: httpx.AsyncClient, *, clock: Clock | None = None) -> None:
        self._http_client = http_client
        self._clock = clock or (lambda: int(time.time()))
        self._mixin_key: str | None = None
        self._key_lock = asyncio.Lock()

    async def _get_json(self, url: str, *, stage: str) -> JsonMapping:
        try:
            response = await self._http_client.get(url)
        except httpx.HTTPError as error:
            raise NetworkOperationError(f"The Bilibili {stage} request failed.") from error
        try:
            if not 200 <= response.status_code < 300:
                raise NetworkOperationError(
                    f"The Bilibili {stage} request returned HTTP {response.status_code}."
                )
            return read_json_response(response, stage=stage)
        finally:
            await response.aclose()

    async def _metadata(self, parsed: BilibiliInput) -> MediaItem:
        parameter = ("bvid", parsed.bvid) if parsed.bvid is not None else ("aid", parsed.avid)
        query = urlencode({parameter[0]: parameter[1]})
        payload = await self._get_json(f"{_VIEW_ENDPOINT}?{query}", stage="metadata")
        data = api_data(payload, stage="metadata")

        redirect_url = data.get("redirect_url")
        if isinstance(redirect_url, str) and "/bangumi/" in redirect_url:
            raise UnsupportedFeatureError(
                "Bangumi content is not supported by the public MVP.",
                {"reason": "bangumi"},
            )
        rights_value = data.get("rights")
        if isinstance(rights_value, dict):
            rights = cast("JsonMapping", rights_value)
            if any(rights.get(name) == 1 for name in ("pay", "arc_pay", "is_stein_gate")):
                raise UnsupportedFeatureError(
                    "This Bilibili content type is not supported by the public MVP.",
                    {"reason": "restricted_content"},
                )

        pages = sequence(data.get("pages"), stage="metadata", field="pages")
        if len(pages) != 1:
            raise UnsupportedFeatureError(
                "Multi-page Bilibili videos are not supported until M6.",
                {"reason": "multi_page"},
            )
        page_data = mapping(pages[0], stage="metadata", field="pages[0]")
        page_index = required_int(page_data, "page", stage="metadata", minimum=1)
        if page_index != 1:
            raise UnsupportedFeatureError(
                "Multi-page Bilibili videos are not supported until M6.",
                {"reason": "multi_page"},
            )

        bvid = required_string(data, "bvid", stage="metadata")
        if not is_bvid(bvid):
            raise ExtractionError(
                "The Bilibili API returned an invalid canonical identifier.",
                {"stage": "metadata", "field": "bvid"},
            )
        avid = required_int(data, "aid", stage="metadata", minimum=1)
        cid = required_int(page_data, "cid", stage="metadata", minimum=1)
        title = required_string(data, "title", stage="metadata").strip()
        duration = required_int(data, "duration", stage="metadata")
        page_duration = required_int(page_data, "duration", stage="metadata")
        part = required_string(page_data, "part", stage="metadata").strip() or title
        canonical_url = f"https://www.bilibili.com/video/{bvid}"
        ref = MediaRef.model_validate(
            {
                "site": Site.BILIBILI,
                "canonical_id": bvid,
                "canonical_url": canonical_url,
                "normalized_input": parsed.normalized_input,
                "page_index": 1,
                "avid": avid,
            }
        )
        page = MediaPage(
            index=1,
            page_id=str(cid),
            title=part,
            duration_ms=page_duration * 1000,
            formats=(),
        )
        return MediaItem(
            ref=ref,
            title=title,
            duration_ms=duration * 1000,
            pages=(page,),
        )

    async def _wbi_key(self, *, refresh: bool = False) -> str:
        async with self._key_lock:
            if refresh:
                self._mixin_key = None
            if self._mixin_key is not None:
                return self._mixin_key
            payload = await self._get_json(_NAV_ENDPOINT, stage="wbi_key")
            data = api_data(payload, stage="wbi_key")
            wbi_img = mapping(data.get("wbi_img"), stage="wbi_key", field="wbi_img")
            image_url = required_string(wbi_img, "img_url", stage="wbi_key")
            sub_url = required_string(wbi_img, "sub_url", stage="wbi_key")
            self._mixin_key = mixin_key_from_urls(image_url, sub_url)
            return self._mixin_key

    async def _play_data(self, item: MediaItem) -> JsonMapping:
        ref = item.ref
        page = item.pages[0]
        if ref.avid is None:
            raise ExtractionError(
                "The canonical Bilibili identifier is incomplete.",
                {"stage": "formats", "field": "aid"},
            )
        params: dict[str, str | int] = {
            "avid": ref.avid,
            "cid": page.page_id,
            "fnval": 4048,
            "fnver": 0,
            "fourk": 1,
            "from_client": "BROWSER",
            "otype": "json",
            "qn": 127,
            "support_multi_audio": "true",
            "try_look": 1,
        }
        for attempt in range(2):
            key = await self._wbi_key(refresh=attempt == 1)
            query = sign_wbi_query(params, key, self._clock())
            payload = await self._get_json(f"{_PLAY_ENDPOINT}?{query}", stage="formats")
            code = api_code(payload, stage="formats")
            if code == WBI_REJECTED_CODE and attempt == 0:
                continue
            return api_data(payload, stage="formats")
        raise AssertionError("the bounded WBI refresh loop must return or raise")

    async def get_info(self, source: str) -> MediaItem:
        """Return normalized metadata without requesting play information."""

        return await self._metadata(parse_bilibili_input(source))

    async def get_formats(self, source: str) -> MediaItem:
        """Return normalized metadata and all representable DASH tracks."""

        item = await self._metadata(parse_bilibili_input(source))
        data = await self._play_data(item)
        formats = project_formats(data, str(item.ref.canonical_url))
        page = item.pages[0].model_copy(update={"formats": formats})
        return MediaItem(
            ref=item.ref,
            title=item.title,
            duration_ms=item.duration_ms,
            pages=(page,),
        )
