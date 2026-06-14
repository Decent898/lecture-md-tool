# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


ROOT = Path(SPECPATH).parents[1]
SRC = ROOT / "src"
ENTRY = ROOT / "packaging" / "pyinstaller" / "gui_entry.py"

datas = collect_data_files("lecture_md.gui")
hiddenimports = collect_submodules("lecture_md")


a = Analysis(
    [str(ENTRY)],
    pathex=[str(SRC)],
    binaries=[],
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
