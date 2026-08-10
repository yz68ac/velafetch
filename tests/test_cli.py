"""A compact set of CLI behavior tests."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import velafetch.cli.commands.auth as auth_command
from velafetch import __version__
from velafetch.application import (
    DoctorCheck,
    DoctorReport,
    DownloadItemResult,
    DownloadResult,
    DownloadStatus,
    ProgressCallback,
    ProgressUpdate,
    SubtitleOutputFormat,
)
from velafetch.auth import AccountSummary, AuthStatus, QrRenderer, StatusReporter
from velafetch.cli.app import CliDependencies, app, create_app
from velafetch.domain.models import (
    CodecFamily,
    DynamicRange,
    MediaFormat,
    MediaItem,
    MediaKind,
    MediaPage,
    MediaRef,
    MediaResourceKind,
    MediaSource,
    SelectionPolicy,
    Site,
)
from velafetch.errors import ExtractionError
from velafetch.extractors import ResolvedMedia

runner = CliRunner()


class TtyBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


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


def _resolved() -> ResolvedMedia:
    item = _item()
    return ResolvedMedia(
        resource_kind=MediaResourceKind.VIDEO,
        source_id=item.ref.canonical_id,
        source_title=item.title,
        source_url=str(item.ref.canonical_url),
        item_index=1,
        item_count=1,
        item=item,
        page_index=1,
    )


class FakeMediaService:
    async def info(
        self,
        source: str,
        *,
        item_index: int | None,
        page_index: int | None,
        timeout: float,
        proxy: str | None,
        anonymous: bool,
    ) -> MediaItem:
        del source, item_index, page_index, timeout, proxy, anonymous
        return _item()

    async def formats(
        self,
        source: str,
        *,
        item_index: int | None,
        page_index: int | None,
        timeout: float,
        proxy: str | None,
        anonymous: bool,
    ) -> ResolvedMedia:
        del source, item_index, page_index, timeout, proxy, anonymous
        return _resolved()


class BrokenMediaService(FakeMediaService):
    async def info(
        self,
        source: str,
        *,
        item_index: int | None,
        page_index: int | None,
        timeout: float,
        proxy: str | None,
        anonymous: bool,
    ) -> MediaItem:
        del source, item_index, page_index, timeout, proxy, anonymous
        raise ExtractionError("The fixture is broken.")


class FakeDoctor:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok

    async def run(self, **kwargs: object) -> DoctorReport:
        del kwargs
        status = "ok" if self.ok else "failed"
        return DoctorReport((DoctorCheck("ffmpeg", status, "Synthetic check."),))


class FakeAuth:
    def __init__(self, status: AuthStatus | None = None, *, unexpected: bool = False) -> None:
        self.status_result = status or AuthStatus(
            True,
            True,
            AccountSummary(42, "Synthetic Pilot", 1, 2),
            "The stored Bilibili login is valid.",
        )
        self.unexpected = unexpected
        self.imported: str | None = None
        self.logged_out = False

    async def login(
        self,
        *,
        timeout: float,
        proxy: str | None,
        render_qr: QrRenderer,
        report_status: StatusReporter,
    ) -> AccountSummary:
        del timeout, proxy
        render_qr("https://passport.bilibili.com/scan?qrcode_key=synthetic-secret")
        report_status("Synthetic QR status.")
        return AccountSummary(42, "Synthetic Pilot", 1, 2)

    async def import_cookie(
        self,
        raw: str,
        *,
        timeout: float,
        proxy: str | None,
    ) -> AccountSummary:
        del timeout, proxy
        if self.unexpected:
            raise RuntimeError(f"failed with private Cookie {raw}")
        self.imported = raw
        return AccountSummary(42, "Synthetic Pilot", 1, 2)

    async def status(self, *, timeout: float, proxy: str | None) -> AuthStatus:
        del timeout, proxy
        return self.status_result

    def logout(self) -> bool:
        self.logged_out = True
        return True


class FakeDownload:
    def __init__(self, *, partial: bool = False) -> None:
        self.partial = partial
        self.received: dict[str, object] = {}

    async def download(
        self,
        source: str,
        *,
        output_dir: Path,
        policy: SelectionPolicy,
        item_index: int | None,
        page_index: int | None,
        all_items: bool,
        overwrite: bool,
        ffmpeg_path: Path | None,
        timeout: float,
        proxy: str | None,
        cover: bool,
        subtitles: str,
        subtitle_format: SubtitleOutputFormat,
        danmaku: bool,
        output_template: str | None,
        progress: ProgressCallback | None,
        anonymous: bool,
    ) -> DownloadResult:
        self.received = {
            "source": source,
            "policy": policy,
            "item": item_index,
            "page": page_index,
            "all": all_items,
            "overwrite": overwrite,
            "ffmpeg": ffmpeg_path,
            "timeout": timeout,
            "proxy": proxy,
            "cover": cover,
            "subtitles": subtitles,
            "subtitle_format": subtitle_format,
            "danmaku": danmaku,
            "output_template": output_template,
            "anonymous": anonymous,
        }
        output = output_dir.resolve() / "Vela Synthetic Flight.video.mp4"
        if progress is not None:
            progress(
                ProgressUpdate(
                    1,
                    1,
                    "Synthetic",
                    MediaKind.VIDEO,
                    3,
                    3,
                    quality="1080p",
                    codec="avc",
                    width=1920,
                    height=1080,
                    frame_rate_numerator=30,
                    frame_rate_denominator=1,
                    bitrate=5_000_000,
                    dynamic_range="sdr",
                )
            )
        return DownloadResult(
            (
                DownloadItemResult(
                    "BV1VF4111111",
                    "Vela Synthetic Flight",
                    1,
                    1,
                    DownloadStatus.PARTIAL if self.partial else DownloadStatus.SAVED,
                    (output,),
                    error="Synthetic subtitle failure." if self.partial else None,
                ),
            )
        )


def _app(
    *,
    broken: bool = False,
    doctor_ok: bool = True,
    download: FakeDownload | None = None,
    auth: FakeAuth | None = None,
):
    media = BrokenMediaService() if broken else FakeMediaService()
    return create_app(
        CliDependencies(
            media_service=media,
            doctor_service=FakeDoctor(doctor_ok),
            download_service=download or FakeDownload(),
            auth_service=auth or FakeAuth(),
        )
    )


def test_help_and_version() -> None:
    help_result = runner.invoke(app, ["--help"])
    version_result = runner.invoke(app, ["--version"])

    assert help_result.exit_code == 0
    assert "Usage:" in help_result.stdout
    assert "--timeout" in help_result.stdout
    assert all(command in help_result.stdout for command in ("auth", "info", "formats", "doctor"))
    assert "--anonymous" in help_result.stdout
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


def test_download_runs_and_rejects_invalid_modes() -> None:
    result = runner.invoke(_app(), ["download", "BV1Demo", "--video-only"])
    invalid = runner.invoke(_app(), ["download", "BV1Demo", "--video-only", "--audio-only"])

    assert result.exit_code == 0
    assert "Saved:" in result.stdout
    assert "Vela Synthetic Flight.video.mp4" in result.stdout
    assert "Video" in result.stderr
    assert "1080p" in result.stderr
    assert "1920×1080" in result.stderr
    assert "AVC" in result.stderr
    assert invalid.exit_code == 2
    assert "mutually exclusive" in invalid.stderr


def test_m6_download_options_reach_the_service_and_json_disables_progress() -> None:
    service = FakeDownload()
    result = runner.invoke(
        _app(download=service),
        [
            "download",
            "ss47200",
            "--video-only",
            "--all",
            "--no-cover",
            "--subtitles",
            "off",
            "--subtitle-format",
            "json",
            "--danmaku",
            "--output-template",
            "{item:02d}-{page:02d}",
            "--codec",
            "av1",
            "--dynamic-range",
            "hdr",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True and payload["aborted"] is False
    assert service.received["all"] is True
    assert service.received["cover"] is False
    assert service.received["subtitles"] == "off"
    assert service.received["subtitle_format"] is SubtitleOutputFormat.JSON
    assert service.received["danmaku"] is True
    assert service.received["output_template"] == "{item:02d}-{page:02d}"
    policy = service.received["policy"]
    assert isinstance(policy, SelectionPolicy)
    assert policy.codec.value == "av1" and policy.dynamic_range.value == "hdr"
    assert "\x1b[" not in result.stdout + result.stderr


def test_anonymous_root_option_reaches_media_commands() -> None:
    service = FakeDownload()
    result = runner.invoke(
        _app(download=service),
        ["--anonymous", "download", "BV1Demo", "--video-only"],
    )

    assert result.exit_code == 0
    assert service.received["anonymous"] is True


def test_batch_selection_conflicts_and_partial_json_result_contract() -> None:
    conflict = runner.invoke(_app(), ["download", "ss47200", "--all", "--item", "2"])
    partial = runner.invoke(
        _app(download=FakeDownload(partial=True)),
        ["download", "ss47200", "--json"],
    )

    assert conflict.exit_code == 2
    assert "--all cannot be combined" in conflict.stderr
    assert partial.exit_code == 1
    assert partial.stderr == ""
    payload = json.loads(partial.stdout)
    assert payload["ok"] is False
    assert payload["items"][0]["status"] == "partial"
    assert payload["items"][0]["error"] == "Synthetic subtitle failure."


def test_auth_status_import_and_logout_are_safe() -> None:
    service = FakeAuth()
    application = _app(auth=service)

    status = runner.invoke(application, ["auth", "status", "--json"])
    imported = runner.invoke(
        application,
        ["auth", "import-cookie", "--stdin"],
        input="SESSDATA=synthetic-cli-secret",
    )
    logout = runner.invoke(application, ["auth", "logout"])

    payload = json.loads(status.stdout)
    assert status.exit_code == 0 and payload["logged_in"] is True
    assert payload["account"]["username"] == "Synthetic Pilot"
    assert imported.exit_code == 0 and service.imported == "SESSDATA=synthetic-cli-secret"
    assert "synthetic-cli-secret" not in imported.stdout + imported.stderr
    assert logout.exit_code == 0 and service.logged_out is True


def test_invalid_auth_status_is_a_complete_json_result() -> None:
    service = FakeAuth(
        AuthStatus(
            True,
            False,
            AccountSummary(42, "Synthetic Pilot", 1, 2),
            "The stored Bilibili login is invalid or expired.",
        )
    )

    result = runner.invoke(_app(auth=service), ["auth", "status", "--json"])

    assert result.exit_code == 1 and result.stderr == ""
    assert json.loads(result.stdout)["logged_in"] is False


def test_qr_login_requires_a_terminal_and_success_never_prints_the_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rejected = runner.invoke(_app(), ["auth", "login"])
    monkeypatch.setattr(auth_command, "_interactive_terminal", lambda: True)
    monkeypatch.setattr(auth_command, "_render_qr", lambda _: None)

    success = runner.invoke(_app(), ["auth", "login"])

    assert rejected.exit_code == 1
    assert "interactive terminal" in rejected.stderr
    assert success.exit_code == 0 and "Logged in as Synthetic Pilot" in success.stdout
    assert "qrcode_key" not in success.stdout + success.stderr


def test_real_qr_renderer_emits_only_terminal_graphics(monkeypatch: pytest.MonkeyPatch) -> None:
    output = TtyBuffer()
    monkeypatch.setattr(auth_command.sys, "stdout", output)

    auth_command._render_qr("https://passport.bilibili.com/scan?qrcode_key=synthetic-render-secret")

    rendered = output.getvalue()
    assert rendered and "synthetic-render-secret" not in rendered
    assert "\x1b[" in rendered


def test_unexpected_auth_errors_do_not_echo_cookie_values() -> None:
    result = runner.invoke(
        _app(auth=FakeAuth(unexpected=True)),
        ["auth", "import-cookie", "--stdin"],
        input="SESSDATA=synthetic-cli-secret",
    )

    assert result.exit_code == 1
    assert "Unexpected internal error (RuntimeError)." in result.stderr
    assert "synthetic-cli-secret" not in result.stdout + result.stderr
