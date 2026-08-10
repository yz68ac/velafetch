"""Local Bilibili credential parsing and storage."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast
from urllib.parse import unquote_plus, urlsplit

from velafetch.errors import AuthenticationError

_SCHEMA_VERSION = 1
_MAX_COOKIE_BYTES = 16 * 1024
_COOKIE_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_CONTROL_CHARACTER = re.compile(r"[\x00-\x1f\x7f]")
_SAFE_HOSTNAME = re.compile(r"^[a-z0-9.-]{1,253}$")
_ALLOWED_COOKIE_NAMES = (
    "SESSDATA",
    "bili_jct",
    "DedeUserID",
    "DedeUserID__ckMd5",
    "sid",
)


@dataclass(frozen=True, slots=True)
class AccountSummary:
    user_id: int
    username: str
    vip_status: int
    vip_type: int

    def __post_init__(self) -> None:
        numbers = (self.user_id, self.vip_status, self.vip_type)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in numbers):
            raise AuthenticationError("Bilibili returned an invalid account profile.")
        if self.user_id <= 0 or self.vip_status < 0 or self.vip_type < 0:
            raise AuthenticationError("Bilibili returned an invalid account profile.")
        if (
            not self.username
            or len(self.username.encode("utf-8")) > 256
            or _CONTROL_CHARACTER.search(self.username)
        ):
            raise AuthenticationError("Bilibili returned an invalid account profile.")


@dataclass(frozen=True, slots=True)
class Credentials:
    account: AccountSummary
    cookies: tuple[tuple[str, str], ...] = field(repr=False)

    def cookie_mapping(self) -> dict[str, str]:
        return dict(self.cookies)


@dataclass(frozen=True, slots=True)
class AuthStatus:
    stored: bool
    logged_in: bool
    account: AccountSummary | None = None
    message: str = ""


def _cookie_pairs(values: list[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    seen: set[str] = set()
    allowed: dict[str, str] = {}
    for name, value in values:
        folded = name.casefold()
        if folded in seen:
            raise AuthenticationError("The Cookie contains a duplicate field.")
        seen.add(folded)
        if not _COOKIE_NAME.fullmatch(name) or not value:
            raise AuthenticationError("The Cookie contains an invalid field.")
        if _CONTROL_CHARACTER.search(name) or _CONTROL_CHARACTER.search(value):
            raise AuthenticationError("The Cookie contains a control character.")
        if name in _ALLOWED_COOKIE_NAMES:
            allowed[name] = value
    if "SESSDATA" not in allowed:
        raise AuthenticationError("The Cookie does not contain SESSDATA.")
    return tuple((name, allowed[name]) for name in _ALLOWED_COOKIE_NAMES if name in allowed)


def parse_cookie_input(raw: str) -> tuple[tuple[str, str], ...]:
    """Parse a hidden Cookie input while ignoring unrelated browser cookies."""

    if len(raw.encode("utf-8")) > _MAX_COOKIE_BYTES:
        raise AuthenticationError("The Cookie input is too large.")
    text = raw.strip()
    if text[:7].casefold() == "cookie:":
        text = text[7:].strip()
    if not text:
        raise AuthenticationError("The Cookie input is empty.")
    if _CONTROL_CHARACTER.search(text):
        raise AuthenticationError("The Cookie contains a control character.")

    pairs: list[tuple[str, str]] = []
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        name, separator, value = part.partition("=")
        if not separator:
            raise AuthenticationError("The Cookie contains an invalid field.")
        pairs.append((name.strip(), value.strip()))
    return _cookie_pairs(pairs)


def parse_cookie_mapping(values: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    """Validate Cookie values already stored in an HTTP session."""

    return _cookie_pairs(list(values.items()))


def parse_qr_cookie_url(url: str) -> tuple[tuple[str, str], ...]:
    """Extract allowlisted cookies from Bilibili's QR login callback URL."""

    if len(url.encode("utf-8")) > _MAX_COOKIE_BYTES:
        raise AuthenticationError("Bilibili returned an oversized QR login callback.")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        raise AuthenticationError("Bilibili returned a malformed QR login callback URL.") from None
    hostname = (parsed.hostname or "").casefold()
    is_bilibili_url = hostname == "bilibili.com" or hostname.endswith(".bilibili.com")
    is_biligame_url = hostname == "passport.biligame.com"
    if parsed.scheme.casefold() != "https":
        raise AuthenticationError("The Bilibili QR login callback must use HTTPS.")
    if parsed.username is not None or parsed.password is not None:
        raise AuthenticationError("The Bilibili QR login callback contains user information.")
    if port is not None:
        raise AuthenticationError("The Bilibili QR login callback contains an explicit port.")
    if not (is_bilibili_url or is_biligame_url):
        safe_hostname = hostname if _SAFE_HOSTNAME.fullmatch(hostname) else "<invalid>"
        raise AuthenticationError(
            f"Bilibili returned an unexpected QR login callback host: {safe_hostname}."
        )

    pairs: list[tuple[str, str]] = []
    for query_field in parsed.query.split("&"):
        if not query_field:
            continue
        raw_name, separator, raw_value = query_field.partition("=")
        if not separator:
            raise AuthenticationError("Bilibili returned a malformed QR login callback query.")
        pairs.append((unquote_plus(raw_name), raw_value))
    return _cookie_pairs(pairs)


def _integer(value: object, *, field_name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise AuthenticationError(f"The credential file has an invalid {field_name} field.")
    return value


class CredentialStore:
    """Store one active account in the current working directory."""

    def __init__(self, path: Path | None = None) -> None:
        self._configured_path = path

    @property
    def path(self) -> Path:
        return (
            self._configured_path
            if self._configured_path is not None
            else Path.cwd() / ".velafetch" / "credentials.json"
        )

    def load(self) -> Credentials | None:
        path = self.path
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError:
            raise AuthenticationError("The credential file could not be read.") from None
        try:
            value = cast("object", json.loads(raw))
        except (json.JSONDecodeError, UnicodeError):
            raise AuthenticationError("The credential file is not valid JSON.") from None
        if not isinstance(value, dict) or set(value) != {
            "schema_version",
            "site",
            "cookies",
            "account",
        }:
            raise AuthenticationError("The credential file has an invalid structure.")
        if value.get("schema_version") != _SCHEMA_VERSION or value.get("site") != "bilibili":
            raise AuthenticationError("The credential file has an unsupported schema.")

        cookie_value = value.get("cookies")
        if not isinstance(cookie_value, dict) or any(
            not isinstance(name, str) or not isinstance(cookie, str)
            for name, cookie in cookie_value.items()
        ):
            raise AuthenticationError("The credential file has an invalid cookies field.")
        if not set(cookie_value).issubset(_ALLOWED_COOKIE_NAMES):
            raise AuthenticationError("The credential file contains an unknown cookie field.")
        cookies = _cookie_pairs(list(cast("dict[str, str]", cookie_value).items()))

        account_value = value.get("account")
        if not isinstance(account_value, dict) or set(account_value) != {
            "user_id",
            "username",
            "vip_status",
            "vip_type",
        }:
            raise AuthenticationError("The credential file has an invalid account field.")
        username = account_value.get("username")
        if not isinstance(username, str) or not username:
            raise AuthenticationError("The credential file has an invalid username field.")
        account = AccountSummary(
            user_id=_integer(account_value.get("user_id"), field_name="user_id", minimum=1),
            username=username,
            vip_status=_integer(account_value.get("vip_status"), field_name="vip_status"),
            vip_type=_integer(account_value.get("vip_type"), field_name="vip_type"),
        )
        return Credentials(account=account, cookies=cookies)

    def save(self, credentials: Credentials) -> None:
        path = self.path
        payload = {
            "schema_version": _SCHEMA_VERSION,
            "site": "bilibili",
            "cookies": dict(credentials.cookies),
            "account": {
                "user_id": credentials.account.user_id,
                "username": credentials.account.username,
                "vip_status": credentials.account.vip_status,
                "vip_type": credentials.account.vip_type,
            },
        }
        temporary: Path | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".credentials-",
                suffix=".tmp",
                dir=path.parent,
            )
            temporary = Path(temporary_name)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            if os.name != "nt":
                os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        except OSError:
            raise AuthenticationError("The credential file could not be saved.") from None
        finally:
            if temporary is not None:
                with suppress(OSError):
                    temporary.unlink(missing_ok=True)

    def clear(self) -> bool:
        try:
            self.path.unlink()
        except FileNotFoundError:
            return False
        except OSError:
            raise AuthenticationError("The credential file could not be removed.") from None
        return True
