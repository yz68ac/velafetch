"""Small application service that owns one HTTP client per command."""

from __future__ import annotations

from velafetch.extractors import BilibiliExtractor, MediaResource, ResolvedMedia
from velafetch.transport import HttpClient, create_http_client


class MediaApplicationService:
    async def info(
        self,
        source: str,
        *,
        item_index: int | None = None,
        page_index: int | None = None,
        timeout: float = 30.0,
        proxy: str | None = None,
    ) -> MediaResource:
        async with self._client(timeout, proxy) as client:
            return await BilibiliExtractor(client).get_info(
                source,
                item_index=item_index,
                page_index=page_index,
            )

    async def formats(
        self,
        source: str,
        *,
        item_index: int | None = None,
        page_index: int | None = None,
        timeout: float = 30.0,
        proxy: str | None = None,
    ) -> ResolvedMedia:
        async with self._client(timeout, proxy) as client:
            return await BilibiliExtractor(client).get_formats(
                source,
                item_index=item_index,
                page_index=page_index,
            )

    @staticmethod
    def _client(timeout: float, proxy: str | None) -> HttpClient:
        return create_http_client(timeout, proxy)
