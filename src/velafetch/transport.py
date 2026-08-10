"""The tiny HTTP boundary shared by extraction and downloading."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from typing import Protocol, Self, cast

from curl_cffi import CurlOpt
from curl_cffi.requests import AsyncSession, Cookies
from curl_cffi.requests.exceptions import RequestException as RequestError

__all__ = [
    "HttpClient",
    "HttpClientFactory",
    "HttpResponse",
    "RequestError",
    "create_http_client",
]


class HttpResponse(Protocol):
    status_code: int
    headers: Mapping[str, str]

    def json(self) -> object: ...

    def aiter_content(self) -> AsyncIterator[bytes]: ...

    async def aclose(self) -> None: ...


class HttpClient(Protocol):
    cookies: Cookies

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: object | None,
    ) -> None: ...

    async def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse: ...

    def stream(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> AbstractAsyncContextManager[HttpResponse]: ...


HttpClientFactory = Callable[[float, str | None, Mapping[str, str] | None], HttpClient]


def create_http_client(
    timeout: float,
    proxy: str | None,
    bilibili_cookies: Mapping[str, str] | None = None,
) -> HttpClient:
    """Create one sequential session with curl_cffi's bundled Chrome profile."""

    cookie_jar = Cookies()
    for name, value in (bilibili_cookies or {}).items():
        cookie_jar.set(name, value, domain=".bilibili.com", path="/", secure=True)
    session = AsyncSession(
        timeout=timeout,
        proxy=proxy,
        trust_env=False,
        impersonate="chrome",
        default_headers=True,
        allow_redirects=True,
        max_redirects=10,
        max_clients=1,
        verify=True,
        cookies=cookie_jar,
        curl_options=None if proxy else {CurlOpt.PROXY: ""},
    )
    return cast("HttpClient", session)
