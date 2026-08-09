"""Tests for the intentionally small doctor service."""

from __future__ import annotations

import shutil

import pytest

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
