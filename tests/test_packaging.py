"""Offline tests for the pinned FFmpeg staging helper."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

import scripts.fetch_ffmpeg as ffmpeg_packaging


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_manifest(tmp_path: Path, archive: Path, source: Path) -> Path:
    manifest = tmp_path / "ffmpeg.json"
    entry = {
        "name": source.name,
        "url": "https://source.invalid/archive.tar.gz",
        "sha256": _sha256(source),
        "commit": "synthetic",
    }
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "provider": "Synthetic Builder",
                "release_tag": "synthetic-release",
                "license": "LGPL-3.0-or-later",
                "archive": {
                    "name": archive.name,
                    "url": "https://build.invalid/ffmpeg.zip",
                    "sha256": _sha256(archive),
                },
                "ffmpeg_source": entry,
                "build_scripts_source": entry,
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_offline_staging_copies_only_ffmpeg_dlls_license_and_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    archive = cache / "ffmpeg.zip"
    with zipfile.ZipFile(archive, "w") as value:
        value.writestr("ffmpeg-build/bin/ffmpeg.exe", b"synthetic executable")
        value.writestr("ffmpeg-build/bin/avcodec.dll", b"synthetic dll")
        value.writestr("ffmpeg-build/bin/ffprobe.exe", b"not distributed")
        value.writestr("ffmpeg-build/LICENSE.txt", "Synthetic LGPL")
    source = cache / "source.tar.gz"
    source.write_bytes(b"synthetic source")
    manifest = _write_manifest(tmp_path, archive, source)
    monkeypatch.setattr(
        ffmpeg_packaging,
        "_verify_build",
        lambda _: "ffmpeg synthetic --enable-shared --disable-static",
    )

    executable = ffmpeg_packaging.stage_ffmpeg(
        manifest,
        cache,
        tmp_path / "portable",
        offline=True,
        sources=tmp_path / "sources",
    )

    assert executable.read_bytes() == b"synthetic executable"
    assert executable.with_name("avcodec.dll").is_file()
    assert not executable.with_name("ffprobe.exe").exists()
    assert (tmp_path / "portable" / "ffmpeg" / "LICENSE.txt").is_file()
    assert (tmp_path / "sources" / source.name).read_bytes() == b"synthetic source"
    build_info = (tmp_path / "portable" / "FFMPEG_BUILD_INFO.txt").read_text()
    assert "Synthetic Builder" in build_info
    assert "https://build.invalid/ffmpeg.zip" in build_info


def test_offline_staging_rejects_a_missing_or_corrupt_cache(tmp_path: Path) -> None:
    archive = tmp_path / "ffmpeg.zip"
    archive.write_bytes(b"original")
    source = tmp_path / "source.tar.gz"
    source.write_bytes(b"source")
    manifest = _write_manifest(tmp_path, archive, source)
    archive.write_bytes(b"corrupt")

    with pytest.raises(RuntimeError, match="verified offline cache"):
        ffmpeg_packaging.stage_ffmpeg(
            manifest,
            tmp_path,
            tmp_path / "portable",
            offline=True,
            sources=None,
        )


def test_committed_manifest_is_pinned_to_a_versioned_lgpl_asset() -> None:
    manifest = json.loads(
        (Path(__file__).parents[1] / "packaging" / "ffmpeg-windows-x64.json").read_text()
    )
    archive = manifest["archive"]

    assert manifest["license"] == "LGPL-3.0-or-later"
    assert manifest["release_tag"].startswith("autobuild-")
    assert "/latest/" not in archive["url"]
    assert "lgpl-shared" in archive["name"]
    assert len(archive["sha256"]) == 64
