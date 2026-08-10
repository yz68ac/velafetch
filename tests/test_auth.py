"""Offline M7 credential and QR login behavior."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.http_fakes import FakeHttpClient, FakeRequest, FakeResponse
from velafetch.application import MediaApplicationService
from velafetch.auth import (
    AccountSummary,
    AuthService,
    Credentials,
    CredentialStore,
    parse_cookie_input,
    parse_qr_cookie_url,
)
from velafetch.errors import AuthenticationError
from velafetch.transport import HttpClient, RequestError

_ACCOUNT = AccountSummary(42, "Synthetic Pilot", 1, 2)
_COOKIES = (
    ("SESSDATA", "synthetic%2Csession"),
    ("bili_jct", "synthetic-csrf"),
    ("DedeUserID", "42"),
)


def _nav(*, logged_in: bool = True) -> dict[str, object]:
    return {
        "code": 0 if logged_in else -101,
        "message": "OK" if logged_in else "not logged in",
        "data": (
            {
                "isLogin": True,
                "mid": 42,
                "uname": "Synthetic Pilot",
                "vipStatus": 1,
                "vipType": 2,
            }
            if logged_in
            else {}
        ),
    }


def test_cookie_parsers_allowlist_fields_and_preserve_encoding() -> None:
    parsed = parse_cookie_input(
        "Cookie: tracking=ignored; SESSDATA=synthetic%2Csession; "
        "bili_jct=synthetic-csrf; DedeUserID=42"
    )
    qr_parsed = parse_qr_cookie_url(
        "https://passport.biligame.com/crossDomain?DedeUserID=42&"
        "Expires=1999999999&SESSDATA=synthetic%2Csession&"
        "bili_jct=synthetic-csrf&gourl=https%3A%2F%2Fwww.bilibili.com"
    )
    credentials = Credentials(_ACCOUNT, parsed)

    assert parsed == qr_parsed == _COOKIES
    assert credentials.cookie_mapping()["SESSDATA"] == "synthetic%2Csession"
    assert "synthetic" not in repr(credentials)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "sid=only",
        "SESSDATA=one; SESSDATA=two",
        "SESSDATA",
        "SESSDATA=value\nInjected=value",
        "SESSDATA=" + "x" * (16 * 1024),
    ],
)
def test_invalid_cookie_inputs_are_rejected(value: str) -> None:
    with pytest.raises(AuthenticationError):
        parse_cookie_input(value)


@pytest.mark.parametrize(
    ("url", "message"),
    [
        (
            "https://www.bilibili.com.evil.invalid/?SESSDATA=hidden",
            "callback host",
        ),
        (
            "https://passport.biligame.com.evil.invalid/crossDomain?SESSDATA=hidden",
            "callback host",
        ),
        (
            "http://passport.biligame.com/crossDomain?SESSDATA=hidden",
            "must use HTTPS",
        ),
        (
            "https://passport.biligame.com:443/crossDomain?SESSDATA=hidden",
            "explicit port",
        ),
        (
            "https://user@passport.biligame.com/crossDomain?SESSDATA=hidden",
            "user information",
        ),
        (
            "https://passport.biligame.com/crossDomain?SESSDATA=hidden&broken",
            "callback query",
        ),
    ],
)
def test_qr_cookie_result_requires_a_safe_callback_url(url: str, message: str) -> None:
    with pytest.raises(AuthenticationError, match=message) as captured:
        parse_qr_cookie_url(url)
    assert "hidden" not in str(captured.value)


@pytest.mark.parametrize("path", ["/crossDomain", "/crossdomain/", "/updated/login/callback"])
def test_qr_cookie_result_accepts_callback_path_variations(path: str) -> None:
    parsed = parse_qr_cookie_url(
        f"https://passport.biligame.com{path}?SESSDATA=synthetic%2Csession"
    )

    assert parsed == (("SESSDATA", "synthetic%2Csession"),)


def test_credential_store_round_trip_is_strict_and_logout_preserves_parts(tmp_path: Path) -> None:
    path = tmp_path / ".velafetch" / "credentials.json"
    part = path.parent / "BV1Synthetic" / "video.part"
    part.parent.mkdir(parents=True)
    part.write_bytes(b"partial")
    store = CredentialStore(path)

    store.save(Credentials(_ACCOUNT, _COOKIES))
    loaded = store.load()

    assert loaded == Credentials(_ACCOUNT, _COOKIES)
    assert "synthetic%2Csession" in path.read_text(encoding="utf-8")
    assert store.clear() is True
    assert store.clear() is False
    assert part.read_bytes() == b"partial"


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        '{"schema_version": 2, "site": "bilibili", "cookies": {}, "account": {}}',
        (
            '{"schema_version": 1, "site": "bilibili", '
            '"cookies": {"SESSDATA": "x", "unknown": "y"}, "account": {}}'
        ),
    ],
)
def test_credential_store_rejects_corrupt_or_unknown_data(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "credentials.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(AuthenticationError):
        CredentialStore(path).load()


@pytest.mark.asyncio
async def test_qr_login_polls_validates_then_atomically_saves(tmp_path: Path) -> None:
    path = tmp_path / ".velafetch" / "credentials.json"
    responses: list[FakeResponse] = []
    poll_states = iter((86101, 86090, 0))
    clients: list[Mapping[str, str] | None] = []
    now = [0.0]

    def response(payload: object) -> FakeResponse:
        item = FakeResponse(200, payload=payload)
        responses.append(item)
        return item

    def handler(request: FakeRequest) -> FakeResponse:
        if request.url.path.endswith("/generate"):
            return response(
                {
                    "code": 0,
                    "data": {
                        "qrcode_key": "synthetic-qr-key",
                        "url": "https://passport.bilibili.com/scan?qrcode_key=synthetic-qr-key",
                    },
                }
            )
        if request.url.path.endswith("/poll"):
            state = next(poll_states)
            data: dict[str, object] = {"code": state}
            if state == 0:
                data.update(
                    {
                        "url": (
                            "https://passport.biligame.com/x/passport-login/web/crossDomain?"
                            "ticket=synthetic-ticket&"
                            "gourl=https%3A%2F%2Fwww.bilibili.com&first_domain=.bilibili.com"
                        ),
                        "refresh_token": "synthetic-refresh-token",
                    }
                )
            return response({"code": 0, "data": data})
        assert request.url.path.endswith("/nav")
        return response(_nav())

    def factory(
        timeout: float,
        proxy: str | None,
        cookies: Mapping[str, str] | None,
    ) -> HttpClient:
        del timeout, proxy
        clients.append(cookies)
        session_cookies = dict(_COOKIES) if cookies is None else cookies
        return FakeHttpClient(handler, session_cookies)

    async def sleep(delay: float) -> None:
        now[0] += delay

    service = AuthService(
        CredentialStore(path),
        factory,
        sleep=sleep,
        monotonic=lambda: now[0],
    )
    rendered: list[str] = []
    statuses: list[str] = []

    account = await service.login(
        timeout=5,
        proxy=None,
        render_qr=rendered.append,
        report_status=statuses.append,
    )

    assert account == _ACCOUNT
    assert len(rendered) == 1 and "synthetic-qr-key" in rendered[0]
    assert statuses == [
        "Waiting for the QR code to be scanned...",
        "QR code scanned. Confirm the login on your device...",
    ]
    assert clients == [None, dict(_COOKIES)]
    assert all(item.closed for item in responses)
    stored_text = path.read_text(encoding="utf-8")
    assert "synthetic%2Csession" in stored_text
    assert "synthetic-qr-key" not in stored_text
    assert "synthetic-refresh-token" not in stored_text
    assert "synthetic-ticket" not in stored_text


@pytest.mark.asyncio
async def test_expired_qr_and_invalid_import_do_not_replace_existing_login(
    tmp_path: Path,
) -> None:
    path = tmp_path / "credentials.json"
    store = CredentialStore(path)
    store.save(Credentials(_ACCOUNT, _COOKIES))
    original = path.read_bytes()

    def handler(request: FakeRequest) -> FakeResponse:
        if request.url.path.endswith("/generate"):
            return FakeResponse(
                200,
                payload={
                    "code": 0,
                    "data": {
                        "qrcode_key": "synthetic-qr-key",
                        "url": "https://passport.bilibili.com/scan?qrcode_key=synthetic-qr-key",
                    },
                },
            )
        if request.url.path.endswith("/poll"):
            return FakeResponse(200, payload={"code": 0, "data": {"code": 86038}})
        return FakeResponse(200, payload=_nav(logged_in=False))

    def factory(
        timeout: float,
        proxy: str | None,
        cookies: Mapping[str, str] | None,
    ) -> HttpClient:
        del timeout, proxy, cookies
        return FakeHttpClient(handler)

    async def no_wait(delay: float) -> None:
        del delay

    service = AuthService(store, factory, sleep=no_wait)
    with pytest.raises(AuthenticationError, match="expired"):
        await service.login(
            timeout=5,
            proxy=None,
            render_qr=lambda _: None,
            report_status=lambda _: None,
        )
    with pytest.raises(AuthenticationError, match="invalid or expired"):
        await service.import_cookie("SESSDATA=replacement", timeout=5, proxy=None)

    assert path.read_bytes() == original


@pytest.mark.asyncio
async def test_auth_request_retries_and_status_reports_invalid_login(tmp_path: Path) -> None:
    attempts = 0
    store = CredentialStore(tmp_path / "credentials.json")
    store.save(Credentials(_ACCOUNT, _COOKIES))

    def handler(request: FakeRequest) -> FakeResponse:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RequestError("synthetic URL with SESSDATA=must-not-leak")
        return FakeResponse(200, payload=_nav(logged_in=False))

    def factory(
        timeout: float,
        proxy: str | None,
        cookies: Mapping[str, str] | None,
    ) -> HttpClient:
        del timeout, proxy, cookies
        return FakeHttpClient(handler)

    async def no_wait(delay: float) -> None:
        del delay

    status = await AuthService(store, factory, sleep=no_wait).status(timeout=5, proxy=None)

    assert attempts == 3
    assert status.stored is True and status.logged_in is False
    assert "SESSDATA" not in status.message


@pytest.mark.asyncio
async def test_auth_retry_after_is_used_for_retryable_http_status(tmp_path: Path) -> None:
    attempts = 0
    delays: list[float] = []
    responses: list[FakeResponse] = []
    store = CredentialStore(tmp_path / "credentials.json")
    store.save(Credentials(_ACCOUNT, _COOKIES))

    def handler(request: FakeRequest) -> FakeResponse:
        nonlocal attempts
        del request
        attempts += 1
        response = (
            FakeResponse(429, headers={"Retry-After": "1"})
            if attempts == 1
            else FakeResponse(200, payload=_nav())
        )
        responses.append(response)
        return response

    def factory(
        timeout: float,
        proxy: str | None,
        cookies: Mapping[str, str] | None,
    ) -> HttpClient:
        del timeout, proxy, cookies
        return FakeHttpClient(handler)

    async def sleep(delay: float) -> None:
        delays.append(delay)

    status = await AuthService(store, factory, sleep=sleep).status(timeout=5, proxy=None)

    assert status.logged_in is True
    assert attempts == 2 and delays == [1.0]
    assert all(response.closed for response in responses)


@pytest.mark.asyncio
async def test_qr_timeout_and_cancellation_never_create_credentials(tmp_path: Path) -> None:
    def handler(request: FakeRequest) -> FakeResponse:
        if request.url.path.endswith("/generate"):
            return FakeResponse(
                200,
                payload={
                    "code": 0,
                    "data": {
                        "qrcode_key": "synthetic-qr-key",
                        "url": "https://passport.bilibili.com/scan?qrcode_key=synthetic-qr-key",
                    },
                },
            )
        return FakeResponse(200, payload={"code": 0, "data": {"code": 86101}})

    def factory(
        timeout: float,
        proxy: str | None,
        cookies: Mapping[str, str] | None,
    ) -> HttpClient:
        del timeout, proxy, cookies
        return FakeHttpClient(handler)

    timeout_path = tmp_path / "timeout.json"
    now = [0.0]

    async def pass_deadline(delay: float) -> None:
        now[0] += delay + 180.0

    timeout_service = AuthService(
        CredentialStore(timeout_path),
        factory,
        sleep=pass_deadline,
        monotonic=lambda: now[0],
    )
    with pytest.raises(AuthenticationError, match="timed out"):
        await timeout_service.login(
            timeout=5,
            proxy=None,
            render_qr=lambda _: None,
            report_status=lambda _: None,
        )
    assert not timeout_path.exists()

    cancel_path = tmp_path / "cancel.json"

    async def cancel(delay: float) -> None:
        del delay
        raise asyncio.CancelledError

    cancel_service = AuthService(CredentialStore(cancel_path), factory, sleep=cancel)
    with pytest.raises(asyncio.CancelledError):
        await cancel_service.login(
            timeout=5,
            proxy=None,
            render_qr=lambda _: None,
            report_status=lambda _: None,
        )
    assert not cancel_path.exists()


@pytest.mark.asyncio
async def test_media_service_loads_credentials_unless_anonymous(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "credentials.json")
    store.save(Credentials(_ACCOUNT, _COOKIES))
    sessions: list[Mapping[str, str] | None] = []

    def handler(request: FakeRequest) -> FakeResponse:
        assert request.url.path.endswith("/view")
        return FakeResponse(
            200,
            payload={
                "code": 0,
                "data": {
                    "aid": 100000001,
                    "bvid": "BV1VF4111111",
                    "title": "Synthetic Authenticated Video",
                    "duration": 1,
                    "pages": [{"page": 1, "cid": 900000001, "part": "P1", "duration": 1}],
                },
            },
        )

    def factory(
        timeout: float,
        proxy: str | None,
        cookies: Mapping[str, str] | None,
    ) -> HttpClient:
        del timeout, proxy
        sessions.append(cookies)
        return FakeHttpClient(handler)

    service = MediaApplicationService(factory, store)
    await service.info("BV1VF4111111")
    await service.info("BV1VF4111111", anonymous=True)

    assert sessions == [dict(_COOKIES), None]
