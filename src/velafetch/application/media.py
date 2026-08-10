"""Small application service that owns one HTTP client per command."""

from __future__ import annotations

from velafetch.auth import CredentialStore
from velafetch.extractors import BilibiliExtractor, MediaResource, ResolvedMedia
from velafetch.transport import HttpClient, HttpClientFactory, create_http_client


class MediaApplicationService:
    def __init__(
        self,
        client_factory: HttpClientFactory = create_http_client,
        credential_store: CredentialStore | None = None,
    ) -> None:
        self._client_factory = client_factory
        self._credential_store = credential_store or CredentialStore()

    async def info(
        self,
        source: str,
        *,
        item_index: int | None = None,
        page_index: int | None = None,
        timeout: float = 30.0,
        proxy: str | None = None,
        anonymous: bool = False,
    ) -> MediaResource:
        async with self._client(timeout, proxy, anonymous) as client:
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
        anonymous: bool = False,
    ) -> ResolvedMedia:
        async with self._client(timeout, proxy, anonymous) as client:
            return await BilibiliExtractor(client).get_formats(
                source,
                item_index=item_index,
                page_index=page_index,
            )

    def _client(self, timeout: float, proxy: str | None, anonymous: bool) -> HttpClient:
        credentials = None if anonymous else self._credential_store.load()
        cookies = None if credentials is None else credentials.cookie_mapping()
        return self._client_factory(timeout, proxy, cookies)
