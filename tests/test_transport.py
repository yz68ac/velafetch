"""The real transport is configured without making a network request."""

from __future__ import annotations

from typing import cast

import pytest
from curl_cffi import CurlOpt
from curl_cffi.requests import AsyncSession

from velafetch.transport import create_http_client

pytestmark = pytest.mark.filterwarnings("ignore::curl_cffi.utils.CurlCffiWarning")


@pytest.mark.asyncio
async def test_client_uses_one_fixed_chrome_profile() -> None:
    client = cast("AsyncSession", create_http_client(12, None))
    try:
        assert client.impersonate == "chrome"
        assert client.default_headers is True
        assert client.timeout == 12
        assert client.max_clients == 1
        assert client.trust_env is False
        assert client.curl_options[CurlOpt.PROXY] == ""
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_explicit_proxy_is_passed_to_curl() -> None:
    client = cast("AsyncSession", create_http_client(12, "http://proxy.invalid:8080"))
    try:
        assert client.proxies == {"all": "http://proxy.invalid:8080"}
        assert CurlOpt.PROXY not in client.curl_options
    finally:
        await client.close()
