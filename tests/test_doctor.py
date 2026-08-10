"""Tests for the intentionally small doctor service."""

from __future__ import annotations

import shutil

import pytest

import velafetch.application.doctor as doctor_module
from tests.http_fakes import FakeHttpClient, FakeResponse
from velafetch.application import DoctorCheck, DoctorReport, DoctorService


def test_report_fails_only_when_a_check_failed() -> None:
    passing = DoctorReport((DoctorCheck("network", "skipped", "Not requested."),))
    failing = DoctorReport((DoctorCheck("ffmpeg", "failed", "Missing."),))

    assert passing.ok is True
    assert failing.ok is False


@pytest.mark.asyncio
async def test_missing_ffmpeg_and_skipped_network_are_easy_to_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: None)

    report = await DoctorService().run(
        ffmpeg_path=None,
        check_network=False,
        timeout=1,
        proxy=None,
    )

    assert [(check.name, check.status) for check in report.checks] == [
        ("ffmpeg", "failed"),
        ("network", "skipped"),
    ]


@pytest.mark.asyncio
async def test_anonymous_nav_response_counts_as_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: None)
    monkeypatch.setattr(
        doctor_module,
        "create_http_client",
        lambda timeout, proxy: FakeHttpClient(
            lambda _: FakeResponse(200, payload={"code": -101, "data": {"isLogin": False}})
        ),
    )

    report = await DoctorService().run(
        ffmpeg_path=None,
        check_network=True,
        timeout=1,
        proxy=None,
    )

    assert report.checks[-1] == DoctorCheck("network", "ok", "Bilibili is reachable.")
