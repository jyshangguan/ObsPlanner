# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
    copy_metadata,
)

project_root = Path(SPECPATH).parents[1]
source_root = project_root / "src"

datas = [
    (str(project_root / "app.py"), "."),
    (str(project_root / "assets" / "ObsPlanner.png"), "assets"),
    (str(project_root / "assets" / "obsplanner-open-app.png"), "assets"),
    (str(project_root / "data" / "observatories.yaml"), "data"),
]
for package in ("astroplan", "matplotlib", "streamlit", "webview"):
    datas += collect_data_files(package)
datas += collect_data_files(
    "astropy",
    excludes=["**/tests/**", "**/*.pyi", "**/*.pyx", "**/*.c", "**/include/**"],
)
datas += collect_data_files(
    "astroquery",
    includes=["CITATION", "simbad/data/*.json"],
)
datas += collect_data_files(
    "pyvo",
    includes=["samp/data/*"],
)
for distribution in (
    "astroplan",
    "astropy",
    "astroquery",
    "matplotlib",
    "obsplanner",
    "platformdirs",
    "pyvo",
    "pywebview",
    "streamlit",
):
    datas += copy_metadata(distribution)

hidden_imports = []
for package in ("obsplanner",):
    hidden_imports += collect_submodules(package)
hidden_imports += [
    "webview.platforms.cocoa",
    "matplotlib.backends.backend_agg",
    "matplotlib.backends.backend_svg",
    "streamlit.hello",
    "streamlit.runtime.scriptrunner.magic_funcs",
    "zoneinfo",
]

analysis = Analysis(
    [str(project_root / "desktop_launcher.py")],
    pathex=[str(source_root), str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[str(project_root / "packaging" / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib.backends.backend_qt5agg",
        "matplotlib.backends.backend_qtagg",
        "matplotlib.backends.backend_tkagg",
        "pyarrow._acero",
        "pyarrow._azurefs",
        "pyarrow._csv",
        "pyarrow._dataset",
        "pyarrow._dataset_orc",
        "pyarrow._dataset_parquet",
        "pyarrow._dataset_parquet_encryption",
        "pyarrow._feather",
        "pyarrow._flight",
        "pyarrow._fs",
        "pyarrow._gcsfs",
        "pyarrow._hdfs",
        "pyarrow._json",
        "pyarrow._orc",
        "pyarrow._parquet",
        "pyarrow._parquet_encryption",
        "pyarrow._s3fs",
        "pyarrow._substrait",
        "streamlit.testing",
        "webview.platforms.android",
        "webview.platforms.cef",
        "webview.platforms.edgechromium",
        "webview.platforms.gtk",
        "webview.platforms.mshtml",
        "webview.platforms.qt",
    ],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="ObsPlanner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
    target_arch="arm64",
    codesign_identity=None,
    entitlements_file=None,
)

collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="ObsPlanner",
)

application = BUNDLE(
    collection,
    name="ObsPlanner.app",
    icon=str(project_root / "assets" / "ObsPlanner.icns"),
    bundle_identifier="com.jyshangguan.obsplanner",
    version="0.2.1",
    info_plist={
        "CFBundleDisplayName": "ObsPlanner",
        "CFBundleName": "ObsPlanner",
        "CFBundleShortVersionString": "0.2.1",
        "CFBundleVersion": "9",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "Copyright © 2026 ObsPlanner contributors",
        "NSPrincipalClass": "NSApplication",
    },
)
