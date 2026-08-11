# M8 implementation log

This is a curated record of what was actually done while implementing M8. It intentionally omits
credentials, signed media URLs, and noisy full command output.

## 2026-08-11: establish the release choices

The starting project built a wheel with Hatchling, but FFmpeg lookup was duplicated in `download`
and `doctor`, the version appeared in two files, and CI tested only the Linux source checkout.

The selected release shape is:

- VelaFetch 0.2.0 under MIT;
- a cross-platform wheel and source distribution;
- one unsigned Windows x64 PyInstaller onedir ZIP;
- a bundled BtbN LGPL shared FFmpeg;
- GitHub Release only, with no PyPI publication or automatic updater.

## Unify version and FFmpeg resolution

Hatchling now reads the version from `velafetch.__version__`, so one edit controls CLI output,
wheel metadata, portable filenames, and the release tag check.

A small FFmpeg resolver replaced the two direct `shutil.which()` calls. Its order is configured
path, frozen portable path, then PATH. Source runs deliberately ignore an adjacent bundle.

Verification:

```powershell
uv run pytest tests/test_ffmpeg.py tests/test_doctor.py tests/test_download.py tests/test_package.py
```

Result: 16 tests passed.

## Pin and inspect FFmpeg

The BtbN GitHub API was queried for a concrete release rather than using a floating `latest` URL:

```text
tag:       autobuild-2026-08-10-13-17
asset:     ffmpeg-n8.1.2-34-g9b6c8969e0-win64-lgpl-shared-8.1.zip
size:      70,708,851 bytes
SHA256:    bf54421a41a11eafdcff3241aeba812f5ab526d4d6942a5a83a9d4588b26cb6d
FFmpeg:    9b6c8969e05b4f0b29f0f85cd501be6b3e582e6b
BtbN:      2437e7b868da3c11872367b15f3c613b87c24819
```

The archive was downloaded into an ignored temporary directory and its hash matched. Inspection
confirmed one `ffmpeg.exe`, seven runtime DLLs, and LGPLv3 text. `ffmpeg -version` reported
`--enable-shared`, `--disable-static`, no `--enable-gpl`, and no `--enable-nonfree`.

The corresponding FFmpeg and BtbN source snapshots were also downloaded and hashed. These values
are committed in the vendor manifest; the binaries themselves are not committed.

## Build scripts and first portable artifact

`fetch_ffmpeg.py` verifies downloads, copies only `ffmpeg.exe` and DLLs, preserves the LGPL text,
rejects an unexpected GPL/nonfree/static build, and can stage source snapshots. `build_portable.py`
runs PyInstaller, collects CPython and dependency license files, assembles the directory, and
creates the ZIP. PyInstaller's broad curl_cffi collection initially pulled in an unused
`setuptools`; switching to data/DLL collection and explicitly excluding that module removed it.

The first real offline build produced:

```text
dist/VelaFetch-0.2.0-windows-x64/
dist/VelaFetch-0.2.0-windows-x64.zip
```

Observed prototype ZIP size: 79,153,077 bytes. The smoke commands succeeded:

```powershell
.\dist\VelaFetch-0.2.0-windows-x64\velafetch.exe --version
.\dist\VelaFetch-0.2.0-windows-x64\velafetch.exe --help
.\dist\VelaFetch-0.2.0-windows-x64\velafetch.exe doctor --json
```

`doctor` returned `FFmpeg is available (bundled).`

## Problems encountered

The sandbox could not reach PyPI during the first `uv lock`; rerunning with approved network access
and a workspace-local uv cache resolved it. The unconstrained resolver initially selected
PyInstaller 6.22.0, so the project was changed to the planned exact `6.21.0` before synchronization.

## Automation and final verification

CI now has a Linux test/wheel job and a Windows portable job. A separate tag workflow verifies that
the Git tag matches the package version before creating a Release with checksums and source assets.
During review, the Release asset layout was found to contain an `ffmpeg-sources/` directory. The
initial `sha256sum *` command would have treated that directory as a file, so checksum generation
and Release upload were changed to enumerate regular files recursively.

The final local verification was:

```powershell
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
uv lock --check
uv build
python scripts/build_portable.py --offline
```

Results:

- Ruff format and lint passed; Pyright reported 0 errors and 0 warnings.
- All 131 offline tests passed.
- The lock file check passed.
- A clean temporary environment installed the wheel and ran both `velafetch --version` and
  `python -m velafetch --version` as 0.2.0; direct help output also succeeded.
- The final portable directory contained 125 files, the CPython license, and license directories
  for 19 Python distributions. Its version, help, bundled-FFmpeg doctor check, and
  `ffmpeg -version` all passed. An offline failed-proxy doctor run also instantiated the real
  curl_cffi client successfully after `setuptools` was excluded.

Observed local artifacts (hashes may differ after a later rebuild because archive timestamps are
not normalized):

```text
velafetch-0.2.0-py3-none-any.whl   66,923 bytes
SHA256 1932050cf850c5e7604f9dac34968cef2b7d3a20a6832129834c9ffd45436d88

VelaFetch-0.2.0-windows-x64.zip    78,007,169 bytes
SHA256 0ad4448a268df221d5c092adfe49ca8208407e5a015497026c817652a85f89a8
```

The sdist contains this implementation log, so embedding the sdist's own hash here would change
the archive on the next build. Its final hash is intentionally generated outside the archive in
the Release's `SHA256SUMS.txt`.

Two local environment details were intentionally kept visible: isolated wheel construction and a
fresh wheel install needed temporary PyPI access because the workspace uv cache did not yet contain
all packages, and piping Rich help into `Select-Object` exposed a legacy Windows console error while
direct terminal help worked normally.

## First GitHub run and publish correction

After the implementation commit was pushed, the main-branch CI passed. The first `v0.2.0` Release
run also built and smoke-tested both Python packages and the Windows portable archive, but its final
`gh release create` command failed because the isolated publish job had no Git checkout from which
GitHub CLI could infer the repository. No partial GitHub Release was created.

The workflow now passes the Actions-provided `GITHUB_REPOSITORY` explicitly with `--repo`. The tag
is moved to this corrective commit before the authoritative Release run, so the published source
and workflow remain consistent.
