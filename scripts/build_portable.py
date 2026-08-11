"""Build the Windows x64 PyInstaller onedir release and ZIP archive."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from fetch_ffmpeg import stage_ffmpeg

from velafetch import __version__

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DISTRIBUTIONS = (
    "annotated-doc",
    "annotated-types",
    "certifi",
    "cffi",
    "colorama",
    "curl-cffi",
    "markdown-it-py",
    "mdurl",
    "pydantic",
    "pydantic-core",
    "pygments",
    "pyinstaller",
    "pycparser",
    "qrcode",
    "rich",
    "shellingham",
    "typer",
    "typing-extensions",
    "typing-inspection",
)


def _run(*arguments: str) -> None:
    subprocess.run(arguments, cwd=PROJECT_ROOT, check=True)


def _copy_license_files(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in RUNTIME_DISTRIBUTIONS:
        distribution = importlib.metadata.distribution(name)
        license_files = [
            file
            for file in distribution.files or ()
            if any(part.lower().startswith(("license", "copying")) for part in file.parts)
        ]
        if not license_files:
            raise RuntimeError(f"No license file was found for runtime distribution {name}.")
        package_root = destination / f"{name}-{distribution.version}"
        for file in license_files:
            source = Path(str(distribution.locate_file(file)))
            if source.is_file():
                package_root.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, package_root / source.name)


def _copy_python_license(destination: Path) -> None:
    source = Path(sys.base_prefix) / "LICENSE.txt"
    if not source.is_file():
        raise RuntimeError(f"The Python runtime license was not found at {source}.")
    version = ".".join(str(part) for part in sys.version_info[:3])
    target = destination / f"Python-{version}"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target / source.name)


def _create_zip(source: Path, destination: Path) -> None:
    destination.unlink(missing_ok=True)
    with zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, Path(source.name) / path.relative_to(source))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(*, offline: bool) -> Path:
    dist = PROJECT_ROOT / "dist"
    work = PROJECT_ROOT / "build" / "pyinstaller"
    pyinstaller_output = dist / "VelaFetch"
    portable = dist / f"VelaFetch-{__version__}-windows-x64"
    cache = PROJECT_ROOT / "build" / "vendor-cache"
    for path in (work, pyinstaller_output, portable):
        if path.exists():
            shutil.rmtree(path)

    _run(
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(dist),
        "--workpath",
        str(work),
        str(PROJECT_ROOT / "packaging" / "velafetch.spec"),
    )
    pyinstaller_output.replace(portable)

    stage_ffmpeg(
        PROJECT_ROOT / "packaging" / "ffmpeg-windows-x64.json",
        cache,
        portable,
        offline=offline,
        sources=dist / "ffmpeg-sources",
    )
    for name in ("LICENSE", "README.md", "README.zh-CN.md", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(PROJECT_ROOT / name, portable / name)
    _copy_license_files(portable / "licenses" / "python")
    _copy_python_license(portable / "licenses" / "python-runtime")

    archive = dist / f"VelaFetch-{__version__}-windows-x64.zip"
    _create_zip(portable, archive)
    print(f"Built {archive} ({_sha256(archive)})")
    return archive


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    arguments = parser.parse_args()
    build(offline=arguments.offline)


if __name__ == "__main__":
    main()
