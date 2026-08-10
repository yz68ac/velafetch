"""A few helpers for reading Bilibili's loosely typed JSON."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from velafetch.errors import AuthenticationError, ExtractionError, UnsupportedFeatureError
from velafetch.transport import HttpResponse

JsonMapping = dict[str, object]


def read_json_response(response: HttpResponse, *, stage: str) -> JsonMapping:
    try:
        payload = cast("object", response.json())
    except ValueError as error:
        raise ExtractionError(f"Bilibili returned invalid JSON while reading {stage}.") from error
    return mapping(payload, stage=stage, field="root")


def mapping(value: object, *, stage: str, field: str) -> JsonMapping:
    if not isinstance(value, dict):
        raise ExtractionError(f"Bilibili returned an invalid {field} object during {stage}.")
    return cast("JsonMapping", value)


def sequence(value: object, *, stage: str, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ExtractionError(f"Bilibili returned an invalid {field} list during {stage}.")
    return cast("list[object]", value)


def required_string(values: Mapping[str, object], name: str, *, stage: str) -> str:
    value = values.get(name)
    if not isinstance(value, str):
        raise ExtractionError(f"Bilibili omitted {name} during {stage}.")
    return value


def required_int(
    values: Mapping[str, object],
    name: str,
    *,
    stage: str,
    minimum: int = 0,
) -> int:
    value = values.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ExtractionError(f"Bilibili returned an invalid {name} during {stage}.")
    return value


def optional_value(values: Mapping[str, object], *names: str) -> object | None:
    return next((values[name] for name in names if name in values), None)


def optional_positive_int(values: Mapping[str, object], *names: str) -> int | None:
    value = optional_value(values, *names)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ExtractionError(f"Bilibili returned an invalid {names[0]} track value.")
    return value


def api_code(payload: Mapping[str, object], *, stage: str) -> int:
    return required_int(payload, "code", stage=stage, minimum=-1_000_000_000)


def api_data(payload: JsonMapping, *, stage: str) -> JsonMapping:
    code = api_code(payload, stage=stage)
    if code != 0:
        message = str(payload.get("message", ""))
        if code == -101:
            raise AuthenticationError(
                "A valid Bilibili login is required. Run 'velafetch auth login'."
            )
        if code == -10403 or any(word in message.casefold() for word in ("login", "vip", "region")):
            raise UnsupportedFeatureError(
                "The current account is not authorized to access this video."
            )
        raise ExtractionError(f"Bilibili API error {code} during {stage}.")
    return mapping(payload.get("data"), stage=stage, field="data")


def api_result(payload: JsonMapping, *, stage: str) -> JsonMapping:
    code = api_code(payload, stage=stage)
    if code != 0:
        message = str(payload.get("message", ""))
        if code == -101:
            raise AuthenticationError(
                "A valid Bilibili login is required. Run 'velafetch auth login'."
            )
        if code == -10403 or any(
            word in message.casefold() for word in ("login", "vip", "region", "pay")
        ):
            raise UnsupportedFeatureError(
                "The current account is not authorized to access this content."
            )
        raise ExtractionError(f"Bilibili API error {code} during {stage}.")
    return mapping(payload.get("result"), stage=stage, field="result")
