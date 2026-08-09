"""Anonymous WBI key derivation and deterministic query signing."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from urllib.parse import quote, urlencode, urlsplit

from velafetch.errors import ExtractionError

WBI_REJECTED_CODE = -352
_FORBIDDEN_VALUE_CHARS = str.maketrans("", "", "!'()*")
_MIXIN_KEY_ENC_TAB = (
    46,
    47,
    18,
    2,
    53,
    8,
    23,
    32,
    15,
    50,
    10,
    31,
    58,
    3,
    45,
    35,
    27,
    43,
    5,
    49,
    33,
    9,
    42,
    19,
    29,
    28,
    14,
    39,
    12,
    38,
    41,
    13,
    37,
    48,
    7,
    16,
    24,
    55,
    40,
    61,
    26,
    17,
    0,
    1,
    60,
    51,
    30,
    4,
    22,
    25,
    54,
    21,
    56,
    59,
    6,
    63,
    57,
    62,
    11,
    36,
    20,
    34,
    44,
    52,
)


def mixin_key_from_urls(image_url: str, sub_url: str) -> str:
    """Derive the 32-character mixin key from anonymous nav image names."""

    def stem(url: str) -> str:
        path = urlsplit(url).path
        filename = path.rsplit("/", 1)[-1]
        return filename.split(".", 1)[0]

    original = stem(image_url) + stem(sub_url)
    if len(original) < 64:
        raise ExtractionError(
            "The Bilibili WBI key response is malformed.",
            {"stage": "wbi_key"},
        )
    return "".join(original[index] for index in _MIXIN_KEY_ENC_TAB)[:32]


def sign_wbi_query(params: Mapping[str, str | int], mixin_key: str, timestamp: int) -> str:
    """Return the deterministic query string expected by the anonymous WBI endpoint."""

    values = {key: str(value).translate(_FORBIDDEN_VALUE_CHARS) for key, value in params.items()}
    values["wts"] = str(timestamp)
    query = urlencode(sorted(values.items()), quote_via=quote)
    signature = hashlib.md5(f"{query}{mixin_key}".encode(), usedforsecurity=False).hexdigest()
    return f"{query}&w_rid={signature}"
