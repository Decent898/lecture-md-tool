# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules


ROOT = Path(SPECPATH).parents[1]
SRC = ROOT / "src"
ENTRY = ROOT / "packaging" / "pyinstaller" / "gui_entry.py"

datas = collect_data_files("lecture_md.gui")
binaries = []
hiddenimports = collect_submodules("lecture_md")

for package in ("slidegeist", "static_ffmpeg", "rapidocr_onnxruntime", "onnxruntime"):
    try:
        hiddenimports += collect_submodules(package)
        datas += collect_data_files(package)
        binaries += collect_dynamic_libs(package)
    except Exception:
        pass

try:
    from static_ffmpeg import run as static_ffmpeg_run

    ffmpeg_dir = Path(static_ffmpeg_run.get_platform_dir())
    platform_name = {"win32": "win32", "darwin": "darwin"}.get(sys.platform, "linux")
    for item in ffmpeg_dir.iterdir():
        if item.is_file():
            binaries.append((str(item), f"static_ffmpeg/bin/{platform_name}"))
except Exception:
    pass


a = Analysis(
    [str(ENTRY)],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="lecture-md-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="lecture-md-gui",
)

app = BUNDLE(
    coll,
    name="lecture-md-gui.app",
    icon=None,
    bundle_identifier="io.github.decent898.lecture-md-tool",
    info_plist={
        "CFBundleName": "lecture-md-tool",
        "CFBundleDisplayName": "lecture-md-tool",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "NSHighResolutionCapable": True,
    },
)
