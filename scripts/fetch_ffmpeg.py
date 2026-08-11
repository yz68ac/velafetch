"""Fetch, verify, and stage the pinned Windows FFmpeg distribution."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import urllib.request
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import cast


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"FFmpeg manifest field {name!r} must be an object.")
    return cast("Mapping[str, object]", value)


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"FFmpeg manifest field {name!r} must be a non-empty string.")
    return value


def _load_manifest(path: Path) -> Mapping[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    manifest = _mapping(value, "root")
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported FFmpeg manifest schema version.")
    return manifest


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verified_download(entry: Mapping[str, object], cache: Path, *, offline: bool) -> Path:
    name = _text(entry.get("name"), "name")
    url = _text(entry.get("url"), "url")
    expected = _text(entry.get("sha256"), "sha256").lower()
    destination = cache / name
    if destination.is_file() and _sha256(destination) == expected:
        return destination
    if offline:
        raise RuntimeError(f"The verified offline cache is missing {name}.")

    cache.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".download")
    temporary.unlink(missing_ok=True)
    try:
        with (
            urllib.request.urlopen(url, timeout=60) as response,  # noqa: S310
            temporary.open("wb") as output,
        ):
            shutil.copyfileobj(response, output)
        actual = _sha256(temporary)
        if actual != expected:
            raise RuntimeError(f"SHA256 mismatch for {name}: {actual}.")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _copy_member(archive: zipfile.ZipFile, member: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(member) as source, destination.open("wb") as output:
        shutil.copyfileobj(source, output)


def _stage_binary(archive_path: Path, output: Path) -> Path:
    ffmpeg_root = output / "ffmpeg"
    if ffmpeg_root.exists():
        shutil.rmtree(ffmpeg_root)
    binary_root = ffmpeg_root / "bin"

    with zipfile.ZipFile(archive_path) as archive:
        executable_members = [
            name for name in archive.namelist() if name.lower().endswith("/bin/ffmpeg.exe")
        ]
        if len(executable_members) != 1:
            raise RuntimeError("The FFmpeg archive does not contain exactly one ffmpeg.exe.")
        executable_member = executable_members[0]
        member_bin = executable_member.rsplit("/", 1)[0] + "/"
        dll_members = [
            name
            for name in archive.namelist()
            if name.startswith(member_bin) and name.lower().endswith(".dll")
        ]
        if not dll_members:
            raise RuntimeError("The shared FFmpeg archive does not contain DLLs.")
        _copy_member(archive, executable_member, binary_root / "ffmpeg.exe")
        for member in dll_members:
            _copy_member(archive, member, binary_root / Path(member).name)

        license_members = [
            name for name in archive.namelist() if name.lower().endswith("/license.txt")
        ]
        if len(license_members) != 1:
            raise RuntimeError("The FFmpeg archive does not contain exactly one LICENSE.txt.")
        _copy_member(archive, license_members[0], ffmpeg_root / "LICENSE.txt")
    return binary_root / "ffmpeg.exe"


def _verify_build(executable: Path) -> str:
    result = subprocess.run(
        [str(executable), "-version"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = result.stdout
    if "--enable-gpl" in output or "--enable-nonfree" in output:
        raise RuntimeError("The pinned FFmpeg build is not an LGPL redistributable build.")
    if "--enable-shared" not in output or "--disable-static" not in output:
        raise RuntimeError("The pinned FFmpeg build is not the expected shared build.")
    return output.strip()


def _build_info(manifest: Mapping[str, object], version_output: str) -> str:
    archive = _mapping(manifest.get("archive"), "archive")
    ffmpeg_source = _mapping(manifest.get("ffmpeg_source"), "ffmpeg_source")
    scripts = _mapping(manifest.get("build_scripts_source"), "build_scripts_source")
    return "\n".join(
        (
            "FFmpeg bundled with VelaFetch",
            "",
            f"Provider: {_text(manifest.get('provider'), 'provider')}",
            f"License: {_text(manifest.get('license'), 'license')}",
            f"Release tag: {_text(manifest.get('release_tag'), 'release_tag')}",
            f"Binary archive: {_text(archive.get('name'), 'archive.name')}",
            f"Binary URL: {_text(archive.get('url'), 'archive.url')}",
            f"Binary SHA256: {_text(archive.get('sha256'), 'archive.sha256')}",
            f"FFmpeg source: {_text(ffmpeg_source.get('url'), 'ffmpeg_source.url')}",
            f"FFmpeg source SHA256: {_text(ffmpeg_source.get('sha256'), 'ffmpeg_source.sha256')}",
            f"Build scripts: {_text(scripts.get('url'), 'build_scripts_source.url')}",
            f"Build scripts SHA256: {_text(scripts.get('sha256'), 'build_scripts_source.sha256')}",
            "",
            version_output,
            "",
        )
    )


def stage_ffmpeg(
    manifest_path: Path,
    cache: Path,
    output: Path,
    *,
    offline: bool,
    sources: Path | None,
) -> Path:
    manifest = _load_manifest(manifest_path)
    archive = _verified_download(
        _mapping(manifest.get("archive"), "archive"), cache, offline=offline
    )
    executable = _stage_binary(archive, output)
    version_output = _verify_build(executable)
    (output / "FFMPEG_BUILD_INFO.txt").write_text(
        _build_info(manifest, version_output), encoding="utf-8"
    )

    if sources is not None:
        sources.mkdir(parents=True, exist_ok=True)
        for field in ("ffmpeg_source", "build_scripts_source"):
            entry = _mapping(manifest.get(field), field)
            source = _verified_download(entry, cache, offline=offline)
            shutil.copy2(source, sources / _text(entry.get("name"), f"{field}.name"))
    return executable


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sources", type=Path)
    parser.add_argument("--offline", action="store_true")
    arguments = parser.parse_args()
    executable = stage_ffmpeg(
        arguments.manifest,
        arguments.cache,
        arguments.output,
        offline=arguments.offline,
        sources=arguments.sources,
    )
    print(executable)


if __name__ == "__main__":
    main()
