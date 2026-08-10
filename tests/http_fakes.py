"""Small in-memory HTTP objects for offline tests."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit

from velafetch.transport import HttpClient, HttpResponse


@dataclass(frozen=True, slots=True)
class FakeRequest:
    method: str
    url: SplitResult
    headers: Mapping[str, str]


class FakeResponse(HttpResponse):
    def __init__(
        self,
        status_code: int,
        *,
        payload: object | None = None,
        content: bytes | None = None,
        chunks: tuple[bytes, ...] | None = None,
        headers: Mapping[str, str] | None = None,
        stream_error: BaseException | None = None,
        wait_after_chunks: asyncio.Event | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self._content = content
        self._chunks = chunks if chunks is not None else (() if content is None else (content,))
        self._stream_error = stream_error
        self._wait_after_chunks = wait_after_chunks
        self.headers: Mapping[str, str] = {
            key.casefold(): value for key, value in (headers or {}).items()
        }
        self.closed = False

    def json(self) -> object:
        if self._content is not None:
            return json.loads(self._content)
        return self._payload

    async def aiter_content(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk
        if self._wait_after_chunks is not None:
            await self._wait_after_chunks.wait()
        if self._stream_error is not None:
            raise self._stream_error

    async def aclose(self) -> None:
        self.closed = True


Handler = Callable[[FakeRequest], FakeResponse]


class FakeHttpClient(HttpClient):
    def __init__(self, handler: Handler) -> None:
        self._handler = handler

    async def __aenter__(self) -> FakeHttpClient:
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: object | None,
    ) -> None:
        return None

    @staticmethod
    def _request(method: str, url: str, headers: Mapping[str, str] | None) -> FakeRequest:
        normalized_headers = {key.casefold(): value for key, value in (headers or {}).items()}
        return FakeRequest(method, urlsplit(url), normalized_headers)

    async def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        return self._handler(self._request("GET", url, headers))

    def stream(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> AbstractAsyncContextManager[HttpResponse]:
        return self._stream(method, url, headers=headers)

    @asynccontextmanager
    async def _stream(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> AsyncIterator[HttpResponse]:
        response = self._handler(self._request(method, url, headers))
        try:
            yield response
        finally:
            await response.aclose()
