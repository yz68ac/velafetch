"""A compact set of CLI behavior tests."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from velafetch import __version__
from velafetch.application import DoctorCheck, DoctorReport
from velafetch.cli.app import CliDependencies, app, create_app
from velafetch.domain.models import (
    CodecFamily,
    DynamicRange,
    MediaFormat,
    MediaItem,
    MediaKind,
    MediaPage,
    MediaRef,
    MediaSource,
    Site,
)
from velafetch.errors import ExtractionError

runner = CliRunner()


def _item() -> MediaItem:
    source = MediaSource(urls=("https://media.invalid/video.m4s?token=hidden",))
    track = MediaFormat(
        format_id="video-80-avc-demo",
        kind=MediaKind.VIDEO,
        container="mp4",
        codec="avc1.640028",
        codec_family=CodecFamily.AVC,
        bitrate=5_000_000,
        source=source,
        quality_label="1080p",
        width=1920,
        height=1080,
        frame_rate_numerator=30,
        frame_rate_denominator=1,
        dynamic_range=DynamicRange.SDR,
    )
    return MediaItem(
        ref=MediaRef(
            site=Site.BILIBILI,
            canonical_id="BV1VF4111111",
            canonical_url="https://www.bilibili.com/video/BV1VF4111111",
            normalized_input="BV1VF4111111",
            avid=100000001,
        ),
        title="Vela Synthetic Flight",
        duration_ms=65_000,
        pages=(
            MediaPage(
                index=1,
                page_id="900000001",
                title="Synthetic Page",
                duration_ms=65_000,
                formats=(track,),
            ),
        ),
    )


class FakeMediaService:
    async def info(self, source: str, *, timeout: float, proxy: str | None) -> MediaItem:
        del source, timeout, proxy
        return _item()

    async def formats(self, source: str, *, timeout: float, proxy: str | None) -> MediaItem:
        del source, timeout, proxy
        return _item()


class BrokenMediaService(FakeMediaService):
    async def info(self, source: str, *, timeout: float, proxy: str | None) -> MediaItem:
        del source, timeout, proxy
        raise ExtractionError("The fixture is broken.")


class FakeDoctor:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok

    async def run(self, **kwargs: object) -> DoctorReport:
        del kwargs
        status = "ok" if self.ok else "failed"
        return DoctorReport((DoctorCheck("ffmpeg", status, "Synthetic check."),))


def _app(*, broken: bool = False, doctor_ok: bool = True):
    media = BrokenMediaService() if broken else FakeMediaService()
    return create_app(CliDependencies(media_service=media, doctor_service=FakeDoctor(doctor_ok)))


def test_help_and_version() -> None:
    help_result = runner.invoke(app, ["--help"])
    version_result = runner.invoke(app, ["--version"])

    assert help_result.exit_code == 0
    assert "Usage:" in help_result.stdout
    assert "--timeout" in help_result.stdout
    assert all(command in help_result.stdout for command in ("info", "formats", "doctor"))
    assert "--config" not in help_result.stdout
    assert version_result.stdout.strip() == f"velafetch {__version__}"


def test_info_and_formats_support_human_and_small_json_outputs() -> None:
    human = runner.invoke(_app(), ["info", "BV1Demo"])
    info_json = runner.invoke(_app(), ["info", "BV1Demo", "--json"])
    formats_json = runner.invoke(_app(), ["formats", "BV1Demo", "--json"])

    assert human.exit_code == 0
    assert "Vela Synthetic Flight" in human.stdout
    assert json.loads(info_json.stdout)["id"] == "BV1VF4111111"
    formats = json.loads(formats_json.stdout)
    assert formats["formats"][0]["quality"] == "1080p"
    assert "media.invalid" not in formats_json.stdout
    assert "schema_version" not in formats_json.stdout


def test_expected_errors_are_plain_json() -> None:
    result = runner.invoke(_app(broken=True), ["info", "BV1Demo", "--json"])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert json.loads(result.stderr) == {"error": "The fixture is broken."}


def test_doctor_reports_success_and_failure() -> None:
    success = runner.invoke(_app(), ["doctor", "--json"])
    failure = runner.invoke(_app(doctor_ok=False), ["doctor", "--json"])

    assert success.exit_code == 0
    assert json.loads(success.stdout)["ok"] is True
    assert failure.exit_code == 1
    assert json.loads(failure.stdout)["ok"] is False


def test_download_remains_a_small_m4_placeholder() -> None:
    result = runner.invoke(_app(), ["download", "BV1Demo", "--video-only"])
    invalid = runner.invoke(_app(), ["download", "BV1Demo", "--video-only", "--audio-only"])

    assert result.exit_code == 1
    assert "planned for M4" in result.stderr
    assert invalid.exit_code == 2
    assert "mutually exclusive" in invalid.stderr
