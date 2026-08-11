# M8: Windows portable distribution

M8 turns the source-tree application into installable Python packages and a Windows x64 portable
ZIP. VelaFetch moves to version 0.2.0 and the MIT License. PyPI, installers, code signing, automatic
updates, and non-Windows portable builds remain outside this milestone.

The Python wheel stays platform-neutral and does not contain FFmpeg. The portable ZIP uses
PyInstaller 6.21 onedir and bundles the exact BtbN Windows x64 LGPL shared build described by
`packaging/ffmpeg-windows-x64.json`. FFmpeg resolution is explicit `--ffmpeg`, then the frozen
bundle, then PATH.

Every vendor download is pinned by immutable tag and SHA256. The portable package contains FFmpeg
and Python license material plus build provenance; the GitHub Release also carries the matching
FFmpeg and BtbN build-script source snapshots.

CI verifies formatting, lint, types, offline tests, wheel installation, PyInstaller collection,
bundled FFmpeg discovery, and ZIP creation. A matching `v0.2.0` tag is required before the Release
workflow publishes wheel, sdist, portable ZIP, source snapshots, and `SHA256SUMS.txt`.

See [m8-implementation-log.md](m8-implementation-log.md) for the commands, failures, fixes, and
observed artifacts from the implementation.
