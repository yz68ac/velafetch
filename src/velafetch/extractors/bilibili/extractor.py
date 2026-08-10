"""Public Bilibili resource inspection and playable-unit resolution."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode

from velafetch.domain.models import MediaCollection, MediaItem, MediaResourceKind
from velafetch.errors import (
    ExtractionError,
    NetworkOperationError,
    SelectionError,
    UnsupportedFeatureError,
)
from velafetch.extractors.bilibili.assets import MediaAssets, project_assets
from velafetch.extractors.bilibili.bangumi import (
    bangumi_entry_item,
    project_bangumi_collection,
)
from velafetch.extractors.bilibili.collections import fetch_ugc_collection
from velafetch.extractors.bilibili.input import (
    BilibiliInput,
    BilibiliInputKind,
    parse_bilibili_input,
)
from velafetch.extractors.bilibili.payload import (
    JsonMapping,
    api_code,
    api_data,
    api_result,
    mapping,
    read_json_response,
    required_string,
    sequence,
)
from velafetch.extractors.bilibili.projection import project_formats
from velafetch.extractors.bilibili.resources import (
    MediaResource,
    ResolvedMedia,
    choose_index,
)
from velafetch.extractors.bilibili.video import project_video_metadata
from velafetch.extractors.bilibili.wbi import (
    WBI_REJECTED_CODE,
    mixin_key_from_urls,
    sign_wbi_query,
)
from velafetch.transport import HttpClient, RequestError

Clock = Callable[[], int]
Sleep = Callable[[float], Awaitable[None]]

_VIEW_ENDPOINT = "https://api.bilibili.com/x/web-interface/view"
_NAV_ENDPOINT = "https://api.bilibili.com/x/web-interface/nav"
_PLAY_ENDPOINT = "https://api.bilibili.com/x/player/wbi/playurl"
_PLAYER_INFO_ENDPOINT = "https://api.bilibili.com/x/player/wbi/v2"
_SEASON_ENDPOINT = "https://api.bilibili.com/pgc/view/web/season"
_BANGUMI_PLAY_ENDPOINT = "https://api.bilibili.com/pgc/player/web/playurl"
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _retry_after(headers: Mapping[str, str], now: int) -> float | None:
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        delay = float(value)
    except ValueError:
        try:
            delay = parsedate_to_datetime(value).timestamp() - now
        except (TypeError, ValueError, OverflowError):
            return None
    return min(30.0, max(0.0, delay))


class BilibiliExtractor:
    """Inspect public resources and resolve concrete pages just before playback."""

    def __init__(
        self,
        http_client: HttpClient,
        *,
        clock: Clock | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._http_client = http_client
        self._clock = clock or (lambda: int(time.time()))
        self._sleep = sleep
        self._mixin_key: str | None = None
        self._key_lock = asyncio.Lock()

    async def _get_json(
        self,
        url: str,
        *,
        stage: str,
        headers: Mapping[str, str] | None = None,
    ) -> JsonMapping:
        last_status: int | None = None
        for attempt in range(3):
            try:
                response = await self._http_client.get(url, headers=headers)
            except RequestError:
                if attempt < 2:
                    await self._sleep(0.5 * (2**attempt))
                    continue
                raise NetworkOperationError(f"The Bilibili {stage} request failed.") from None
            try:
                last_status = response.status_code
                if 200 <= response.status_code < 300:
                    return read_json_response(response, stage=stage)
                if response.status_code not in _RETRYABLE_STATUS or attempt == 2:
                    raise NetworkOperationError(
                        f"The Bilibili {stage} request returned HTTP {response.status_code}."
                    )
                delay = _retry_after(response.headers, self._clock())
            finally:
                await response.aclose()
            await self._sleep(delay if delay is not None else 0.5 * (2**attempt))
        raise NetworkOperationError(f"The Bilibili {stage} request returned HTTP {last_status}.")

    async def _video_metadata(
        self,
        parsed: BilibiliInput,
        requested_page: int | None,
    ) -> MediaItem:
        parameter = ("bvid", parsed.bvid) if parsed.bvid is not None else ("aid", parsed.avid)
        payload = await self._get_json(
            f"{_VIEW_ENDPOINT}?{urlencode({parameter[0]: parameter[1]})}",
            stage="metadata",
        )
        data = api_data(payload, stage="metadata")
        pages = sequence(data.get("pages"), stage="metadata", field="pages")
        selected_page = choose_index(
            requested_page,
            parsed.selected_page,
            len(pages),
            label="page",
        )
        item = project_video_metadata(
            data,
            normalized_input=parsed.normalized_input,
            selected_page=selected_page,
        )
        if parsed.bvid is not None and item.ref.canonical_id != parsed.bvid:
            raise ExtractionError("The Bilibili metadata identity does not match the input.")
        if parsed.avid is not None and item.ref.avid != parsed.avid:
            raise ExtractionError("The Bilibili metadata identity does not match the input.")
        return item

    async def _bangumi_collection(
        self,
        parsed: BilibiliInput,
        requested_item: int | None,
    ) -> MediaCollection:
        name, identifier = (
            ("season_id", parsed.season_id)
            if parsed.season_id is not None
            else ("ep_id", parsed.episode_id)
        )
        payload = await self._get_json(
            f"{_SEASON_ENDPOINT}?{urlencode({name: identifier})}",
            stage="season",
        )
        return project_bangumi_collection(
            api_result(payload, stage="season"),
            normalized_input=parsed.normalized_input,
            requested_item=requested_item,
            requested_episode_id=parsed.episode_id,
        )

    async def _ugc_collection(
        self,
        parsed: BilibiliInput,
        requested_item: int | None,
    ) -> MediaCollection:
        return await fetch_ugc_collection(parsed, requested_item, self._get_json)

    async def _inspect_parsed(
        self,
        parsed: BilibiliInput,
        *,
        item_index: int | None,
        page_index: int | None,
    ) -> MediaResource:
        if parsed.kind is BilibiliInputKind.VIDEO:
            if item_index is not None:
                raise SelectionError("--item only applies to seasons and public collections.")
            return await self._video_metadata(parsed, page_index)
        if parsed.kind in {
            BilibiliInputKind.BANGUMI_SEASON,
            BilibiliInputKind.BANGUMI_EPISODE,
        }:
            if page_index not in {None, 1}:
                raise SelectionError("Bangumi episodes do not have selectable video pages.")
            return await self._bangumi_collection(parsed, item_index)
        collection = await self._ugc_collection(parsed, item_index)
        return collection.model_copy(update={"selected_page": page_index or 1})

    async def get_info(
        self,
        source: str,
        *,
        item_index: int | None = None,
        page_index: int | None = None,
    ) -> MediaResource:
        return await self._inspect_parsed(
            parse_bilibili_input(source),
            item_index=item_index,
            page_index=page_index,
        )

    async def resolve_many(
        self,
        source: str,
        *,
        item_index: int | None = None,
        page_index: int | None = None,
        all_items: bool = False,
    ) -> tuple[ResolvedMedia, ...]:
        if all_items and (item_index is not None or page_index is not None):
            raise SelectionError("--all cannot be combined with --item or --page.")
        parsed = parse_bilibili_input(source)
        resource = await self._inspect_parsed(
            parsed,
            item_index=None if all_items else item_index,
            page_index=None if all_items else page_index,
        )
        if isinstance(resource, MediaItem):
            pages = resource.pages if all_items else (resource.pages[resource.ref.page_index - 1],)
            return tuple(
                ResolvedMedia(
                    resource_kind=MediaResourceKind.VIDEO,
                    source_id=resource.ref.canonical_id,
                    source_title=resource.title,
                    source_url=resource.ref.canonical_url,
                    item_index=1,
                    item_count=1,
                    item=resource,
                    page_index=page.index,
                )
                for page in pages
            )

        entries = (
            resource.entries if all_items else (resource.entries[resource.selected_index - 1],)
        )
        resolved: list[ResolvedMedia] = []
        for entry in entries:
            if resource.ref.kind is MediaResourceKind.BANGUMI_SEASON:
                item = bangumi_entry_item(resource, entry)
                resolved.append(
                    ResolvedMedia(
                        resource_kind=resource.ref.kind,
                        source_id=resource.ref.canonical_id,
                        source_title=resource.title,
                        source_url=resource.ref.canonical_url,
                        item_index=entry.index,
                        item_count=len(resource.entries),
                        item=item,
                        page_index=1,
                    )
                )
                continue
            item_parsed = BilibiliInput(
                BilibiliInputKind.VIDEO,
                entry.canonical_url,
                bvid=entry.bvid,
                avid=entry.avid,
            )
            item = await self._video_metadata(
                item_parsed,
                None if all_items else page_index or resource.selected_page,
            )
            pages = item.pages if all_items else (item.pages[item.ref.page_index - 1],)
            resolved.extend(
                ResolvedMedia(
                    resource_kind=resource.ref.kind,
                    source_id=resource.ref.canonical_id,
                    source_title=resource.title,
                    source_url=resource.ref.canonical_url,
                    item_index=entry.index,
                    item_count=len(resource.entries),
                    item=item,
                    page_index=page.index,
                )
                for page in pages
            )
        return tuple(resolved)

    async def _wbi_key(self, *, refresh: bool = False) -> str:
        async with self._key_lock:
            if refresh:
                self._mixin_key = None
            if self._mixin_key is not None:
                return self._mixin_key
            payload = await self._get_json(_NAV_ENDPOINT, stage="wbi_key")
            data = (
                mapping(payload.get("data"), stage="wbi_key", field="data")
                if api_code(payload, stage="wbi_key") == -101
                else api_data(payload, stage="wbi_key")
            )
            wbi_img = mapping(data.get("wbi_img"), stage="wbi_key", field="wbi_img")
            image_url = required_string(wbi_img, "img_url", stage="wbi_key")
            sub_url = required_string(wbi_img, "sub_url", stage="wbi_key")
            self._mixin_key = mixin_key_from_urls(image_url, sub_url)
            return self._mixin_key

    async def _ordinary_play_data(self, resolved: ResolvedMedia) -> JsonMapping:
        page = resolved.page
        if page.avid is None:
            raise ExtractionError("The canonical Bilibili video identity is incomplete.")
        params: dict[str, str | int] = {
            "avid": page.avid,
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
        return await self._wbi_data(_PLAY_ENDPOINT, params, stage="formats")

    async def _wbi_data(
        self,
        endpoint: str,
        params: Mapping[str, str | int],
        *,
        stage: str,
        headers: Mapping[str, str] | None = None,
    ) -> JsonMapping:
        for attempt in range(2):
            key = await self._wbi_key(refresh=attempt == 1)
            query = sign_wbi_query(params, key, self._clock())
            payload = await self._get_json(
                f"{endpoint}?{query}",
                stage=stage,
                headers=headers,
            )
            code = api_code(payload, stage=stage)
            if code == WBI_REJECTED_CODE and attempt == 0:
                continue
            return api_data(payload, stage=stage)
        raise AssertionError("the bounded WBI refresh loop must return or raise")

    async def _bangumi_play_data(self, resolved: ResolvedMedia) -> JsonMapping:
        page = resolved.page
        if page.avid is None or page.episode_id is None:
            raise ExtractionError("The Bangumi episode identity is incomplete.")
        query = urlencode(
            {
                "ep_id": page.episode_id,
                "avid": page.avid,
                "cid": page.page_id,
                "qn": 127,
                "fnval": 4048,
                "fnver": 0,
                "fourk": 1,
            }
        )
        result = api_result(
            await self._get_json(
                f"{_BANGUMI_PLAY_ENDPOINT}?{query}",
                stage="formats",
                headers={"Referer": page.canonical_url or resolved.item.ref.canonical_url},
            ),
            stage="formats",
        )
        if result.get("is_drm") is True or result.get("is_drm") == 1:
            raise UnsupportedFeatureError("DRM-protected Bangumi playback is not supported.")
        if result.get("is_preview") is True or result.get("is_preview") == 1:
            raise UnsupportedFeatureError("Preview-only Bangumi playback is not supported.")
        internal_code = result.get("code")
        if isinstance(internal_code, int) and internal_code != 0:
            raise UnsupportedFeatureError("This Bangumi episode is not publicly playable.")
        return result

    async def load_formats(self, resolved: ResolvedMedia) -> ResolvedMedia:
        data = (
            await self._bangumi_play_data(resolved)
            if resolved.resource_kind is MediaResourceKind.BANGUMI_SEASON
            else await self._ordinary_play_data(resolved)
        )
        referer = resolved.page.canonical_url or resolved.item.ref.canonical_url
        formats = project_formats(data, referer)
        pages = tuple(
            page.model_copy(update={"formats": formats})
            if page.index == resolved.page_index
            else page
            for page in resolved.item.pages
        )
        return resolved.with_item(resolved.item.model_copy(update={"pages": pages}))

    async def get_formats(
        self,
        source: str,
        *,
        item_index: int | None = None,
        page_index: int | None = None,
    ) -> ResolvedMedia:
        resolved = (
            await self.resolve_many(
                source,
                item_index=item_index,
                page_index=page_index,
            )
        )[0]
        return await self.load_formats(resolved)

    async def get_assets(self, resolved: ResolvedMedia) -> MediaAssets:
        page = resolved.page
        if page.avid is None:
            raise ExtractionError("The media identity is incomplete for public assets.")
        referer = page.canonical_url or resolved.item.ref.canonical_url
        data = await self._wbi_data(
            _PLAYER_INFO_ENDPOINT,
            {"aid": page.avid, "cid": page.page_id},
            stage="assets",
            headers={"Referer": referer},
        )
        return project_assets(resolved, data)
