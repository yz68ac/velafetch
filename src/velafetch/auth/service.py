"""Bilibili Web QR login and credential validation."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from email.utils import parsedate_to_datetime
from typing import cast
from urllib.parse import urlencode

from velafetch.auth.credentials import (
    AccountSummary,
    AuthStatus,
    Credentials,
    CredentialStore,
    parse_cookie_input,
    parse_cookie_mapping,
    parse_qr_cookie_url,
)
from velafetch.errors import AuthenticationError
from velafetch.transport import HttpClient, HttpClientFactory, RequestError, create_http_client

Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]
QrRenderer = Callable[[str], None]
StatusReporter = Callable[[str], None]

_GENERATE_ENDPOINT = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
_POLL_ENDPOINT = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
_NAV_ENDPOINT = "https://api.bilibili.com/x/web-interface/nav"
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _mapping(value: object, *, stage: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AuthenticationError(f"Bilibili returned an invalid {stage} response.")
    return cast("dict[str, object]", value)


def _integer(value: object, *, stage: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AuthenticationError(f"Bilibili returned an invalid {stage} response.")
    return value


def _data(payload: Mapping[str, object], *, stage: str) -> dict[str, object]:
    if _integer(payload.get("code"), stage=stage) != 0:
        raise AuthenticationError(f"Bilibili rejected the {stage} request.")
    return _mapping(payload.get("data"), stage=stage)


def _retry_after(headers: Mapping[str, str], wall_clock: Clock) -> float | None:
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        delay = float(value)
    except ValueError:
        try:
            delay = parsedate_to_datetime(value).timestamp() - wall_clock()
        except (TypeError, ValueError, OverflowError):
            return None
    return min(30.0, max(0.0, delay))


def _session_login_cookies(client: HttpClient) -> tuple[tuple[str, str], ...] | None:
    values = {
        cookie.name: cookie.value
        for cookie in client.cookies.jar
        if isinstance(cookie.name, str)
        and isinstance(cookie.value, str)
        and cookie.domain.lstrip(".").casefold() == "bilibili.com"
        and cookie.path == "/"
        and cookie.secure
    }
    if "SESSDATA" not in values:
        return None
    return parse_cookie_mapping(values)


class AuthService:
    """Manage one local Bilibili Web login without exposing its secrets."""

    def __init__(
        self,
        store: CredentialStore | None = None,
        client_factory: HttpClientFactory = create_http_client,
        *,
        sleep: Sleep = asyncio.sleep,
        monotonic: Clock = time.monotonic,
        wall_clock: Clock = time.time,
    ) -> None:
        self._store = store or CredentialStore()
        self._client_factory = client_factory
        self._sleep = sleep
        self._monotonic = monotonic
        self._wall_clock = wall_clock

    async def _request_json(
        self,
        client: HttpClient,
        url: str,
        *,
        stage: str,
    ) -> dict[str, object]:
        for attempt in range(3):
            try:
                response = await client.get(url)
            except RequestError:
                if attempt < 2:
                    await self._sleep(0.5 * (2**attempt))
                    continue
                raise AuthenticationError(f"The Bilibili {stage} request failed.") from None
            try:
                if 200 <= response.status_code < 300:
                    try:
                        return _mapping(response.json(), stage=stage)
                    except ValueError:
                        raise AuthenticationError(
                            f"Bilibili returned invalid JSON during {stage}."
                        ) from None
                if response.status_code not in _RETRYABLE_STATUS or attempt == 2:
                    raise AuthenticationError(
                        f"The Bilibili {stage} request returned HTTP {response.status_code}."
                    )
                retry_delay = _retry_after(response.headers, self._wall_clock)
            finally:
                await response.aclose()
            await self._sleep(retry_delay if retry_delay is not None else 0.5 * (2**attempt))
        raise AssertionError("the bounded authentication retry loop must return or raise")

    async def _validate(
        self,
        cookies: tuple[tuple[str, str], ...],
        *,
        timeout: float,
        proxy: str | None,
    ) -> AccountSummary | None:
        async with self._client_factory(timeout, proxy, dict(cookies)) as client:
            payload = await self._request_json(client, _NAV_ENDPOINT, stage="login validation")
        code = _integer(payload.get("code"), stage="login validation")
        if code == -101:
            return None
        if code != 0:
            raise AuthenticationError("Bilibili rejected the login validation request.")
        data = _mapping(payload.get("data"), stage="login validation")
        if data.get("isLogin") is not True:
            return None
        user_id = _integer(data.get("mid"), stage="login validation")
        username = data.get("uname")
        if user_id <= 0 or not isinstance(username, str) or not username:
            raise AuthenticationError("Bilibili returned an invalid account profile.")
        vip_status = data.get("vipStatus", 0)
        vip_type = data.get("vipType", 0)
        return AccountSummary(
            user_id=user_id,
            username=username,
            vip_status=_integer(vip_status, stage="login validation"),
            vip_type=_integer(vip_type, stage="login validation"),
        )

    async def import_cookie(
        self,
        raw: str,
        *,
        timeout: float,
        proxy: str | None,
    ) -> AccountSummary:
        cookies = parse_cookie_input(raw)
        account = await self._validate(cookies, timeout=timeout, proxy=proxy)
        if account is None:
            raise AuthenticationError("The supplied Cookie is invalid or expired.")
        self._store.save(Credentials(account=account, cookies=cookies))
        return account

    async def status(self, *, timeout: float, proxy: str | None) -> AuthStatus:
        credentials = self._store.load()
        if credentials is None:
            return AuthStatus(False, False, message="No Bilibili login is stored.")
        account = await self._validate(
            credentials.cookies,
            timeout=timeout,
            proxy=proxy,
        )
        if account is None:
            return AuthStatus(
                True,
                False,
                credentials.account,
                "The stored Bilibili login is invalid or expired.",
            )
        return AuthStatus(True, True, account, "The stored Bilibili login is valid.")

    def logout(self) -> bool:
        return self._store.clear()

    async def login(
        self,
        *,
        timeout: float,
        proxy: str | None,
        render_qr: QrRenderer,
        report_status: StatusReporter,
    ) -> AccountSummary:
        async with self._client_factory(timeout, proxy, None) as client:
            generate_query = urlencode({"source": "main-fe-header"})
            generate = _data(
                await self._request_json(
                    client,
                    f"{_GENERATE_ENDPOINT}?{generate_query}",
                    stage="QR generation",
                ),
                stage="QR generation",
            )
            qr_url = generate.get("url")
            qr_key = generate.get("qrcode_key")
            if (
                not isinstance(qr_url, str)
                or not qr_url
                or not isinstance(qr_key, str)
                or not qr_key
            ):
                raise AuthenticationError("Bilibili returned an invalid QR login response.")
            try:
                render_qr(qr_url)
            except Exception:
                raise AuthenticationError("The QR code could not be rendered.") from None

            deadline = self._monotonic() + 180.0
            last_state: int | None = None
            while self._monotonic() < deadline:
                await self._sleep(min(2.0, max(0.0, deadline - self._monotonic())))
                poll_query = urlencode({"qrcode_key": qr_key, "source": "main-fe-header"})
                poll = _data(
                    await self._request_json(
                        client,
                        f"{_POLL_ENDPOINT}?{poll_query}",
                        stage="QR polling",
                    ),
                    stage="QR polling",
                )
                state = _integer(poll.get("code"), stage="QR polling")
                if state != last_state:
                    if state == 86101:
                        report_status("Waiting for the QR code to be scanned...")
                    elif state == 86090:
                        report_status("QR code scanned. Confirm the login on your device...")
                    last_state = state
                if state == 86038:
                    raise AuthenticationError("The QR code expired. Run auth login again.")
                if state in {86101, 86090}:
                    continue
                if state != 0:
                    raise AuthenticationError("Bilibili returned an unknown QR login state.")
                redirect_url = poll.get("url")
                if not isinstance(redirect_url, str) or not redirect_url:
                    raise AuthenticationError("Bilibili returned an invalid QR login result.")
                cookies = _session_login_cookies(client) or parse_qr_cookie_url(redirect_url)
                account = await self._validate(cookies, timeout=timeout, proxy=proxy)
                if account is None:
                    raise AuthenticationError("The new Bilibili login could not be validated.")
                self._store.save(Credentials(account=account, cookies=cookies))
                return account
        raise AuthenticationError("The QR login timed out. Run auth login again.")
