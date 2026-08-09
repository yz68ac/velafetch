"""Small application service that owns one HTTP client per command."""

from __future__ import annotations

import httpx

from velafetch import __version__
from velafetch.domain.models import MediaItem
from velafetch.extractors import BilibiliExtractor


class MediaApplicationService:
    async def info(
        self,
        source: str,
        *,
        timeout: float = 30.0,
        proxy: str | None = None,
    ) -> MediaItem:
        async with self._client(timeout, proxy) as client:
            return await BilibiliExtractor(client).get_info(source)

    async def formats(
        self,
        source: str,
        *,
        timeout: float = 30.0,
        proxy: str | None = None,
    ) -> MediaItem:
        async with self._client(timeout, proxy) as client:
            return await BilibiliExtractor(client).get_formats(source)

    @staticmethod
    def _client(timeout: float, proxy: str | None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=timeout,
            proxy=proxy,
            follow_redirects=True,
            trust_env=False,
            headers={"User-Agent": f"VelaFetch/{__version__}"},
        )
