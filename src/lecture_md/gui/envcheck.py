"""Environment detection and optional install commands for the GUI."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

from lecture_md.runtime import is_frozen, resolve_executable, slidegeist_command, static_ffmpeg_dir


def ffmpeg_status() -> tuple[bool, str]:
    """Return ``(installed, detail)`` for ffmpeg."""
    resolved = resolve_executable("ffmpeg", "LECTURE_MD_FFMPEG")
    if resolved != "ffmpeg" and Path(resolved).exists():
        if "static_ffmpeg" in resolved.replace("\\", "/"):
            return True, f"static-ffmpeg:{Path(resolved).parent}"
        return True, resolved

    which = shutil.which("ffmpeg")
    if which:
        return True, which

    cached = static_ffmpeg_dir()
    if cached:
        return True, f"static-ffmpeg:{cached}"
    return False, ""


def slidegeist_status() -> tuple[bool, str]:
    if is_frozen():
        if module_status("slidegeist"):
            program, args = slidegeist_command("--version")
            return True, "内置: " + " ".join([program, *args])
        return False, ""

    which = shutil.which("slidegeist")
    if which:
        return True, which

    local = Path(sys.executable).parent / ("slidegeist.exe" if sys.platform == "win32" else "slidegeist")
    if local.exists():
        return True, str(local)
    return False, ""


def module_status(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


PIP = [sys.executable, "-m", "pip"]

# In frozen apps dependencies should be bundled. Running ``app.exe -m pip`` would
# relaunch the GUI, so install buttons are intentionally disabled there.
INSTALL_STEPS: dict[str, list[list[str]]] = (
    {}
    if is_frozen()
    else {
        "ffmpeg": [
            [*PIP, "install", "static-ffmpeg"],
            [
                sys.executable,
                "-c",
                "from static_ffmpeg import run; run.get_or_fetch_platform_executables_else_raise()",
            ],
        ],
        "slidegeist": [[*PIP, "install", "slidegeist"]],
        "faster_whisper": [[*PIP, "install", "faster-whisper"]],
        "rapidocr": [[*PIP, "install", "rapidocr-onnxruntime"]],
    }
)

INSTALL_NOTES = {
    "ffmpeg": "通过 static-ffmpeg 安装(含约 80MB 二进制下载,请稍等片刻)",
    "slidegeist": "pip install slidegeist",
    "faster_whisper": "pip install faster-whisper",
    "rapidocr": "pip install rapidocr-onnxruntime",
}
