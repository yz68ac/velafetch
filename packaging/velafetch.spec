"""PyInstaller onedir specification for the Windows portable release."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

project_root = Path.cwd()
curl_datas = collect_data_files("curl_cffi")
curl_binaries = collect_dynamic_libs("curl_cffi")

analysis = Analysis(
    [str(project_root / "src" / "velafetch" / "__main__.py")],
    pathex=[str(project_root / "src")],
    binaries=curl_binaries,
    datas=curl_datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["setuptools"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)
executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="velafetch",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VelaFetch",
)
