"""Small set of errors that the CLI can show without a traceback."""

from __future__ import annotations

from collections.abc import Mapping


class VelaFetchError(Exception):
    """An expected error with an optional bit of debugging context."""

    def __init__(
        self,
        message: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.details = dict(details or {})


class UnsupportedFeatureError(VelaFetchError):
    """The input or feature is outside the current learning project."""


class NetworkOperationError(VelaFetchError):
    """A request failed before useful API data was obtained."""


class ExtractionError(VelaFetchError):
    """A Bilibili response could not be understood."""


class SelectionError(VelaFetchError):
    """No track matched the requested selection."""


class DownloadError(VelaFetchError):
    """A media transfer, FFmpeg run, or output operation failed."""


class AuthenticationError(VelaFetchError):
    """A local credential or Bilibili login operation failed safely."""
