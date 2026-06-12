"""Environment detection and one-click install commands for the GUI.

No Qt imports here so the logic stays unit-testable.
"""

import importlib.util
import os
import shutil
import sys
from pathlib import Path


def static_ffmpeg_dir() -> str | None:
    """Directory of cached static-ffmpeg binaries, if any (never downloads)."""
    try:
        import static_ffmpeg
    except ImportError:
        return None
    exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    candidates: list[Path] = []
    try:
        from static_ffmpeg import run

        candidates.append(Path(run.get_platform_dir()))
    except Exception:
        pass
    base = Path(static_ffmpeg.__file__).parent / "bin"
    platform_name = {"win32": "win32", "darwin": "darwin"}.get(sys.platform, "linux")
    candidates.append(base / platform_name)
    for directory in candidates:
        if (directory / exe_name).exists():
            return str(directory)
    return None


def ffmpeg_status() -> tuple[bool, str]:
    """(installed, detail) for ffmpeg: system PATH first, then static-ffmpeg."""
    which = shutil.which("ffmpeg")
    if which:
        return True, which
    cached = static_ffmpeg_dir()
    if cached:
        return True, f"static-ffmpeg:{cached}"
    return False, ""


def slidegeist_status() -> tuple[bool, str]:
    which = shutil.which("slidegeist")
    if which:
        return True, which
    local = Path(sys.executable).parent / ("slidegeist.exe" if os.name == "nt" else "slidegeist")
    if local.exists():
        return True, str(local)
    return False, ""


def module_status(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


# Each entry: ordered list of commands (argv) executed with QProcess.
# sys.executable targets the same (virtual) environment the GUI runs in.
INSTALL_STEPS: dict[str, list[list[str]]] = {
    "ffmpeg": [
        [sys.executable, "-m", "pip", "install", "static-ffmpeg"],
        [
            sys.executable,
            "-c",
            "from static_ffmpeg import run; run.get_or_fetch_platform_executables_else_raise()",
        ],
    ],
    "slidegeist": [[sys.executable, "-m", "pip", "install", "slidegeist"]],
    "faster_whisper": [[sys.executable, "-m", "pip", "install", "faster-whisper"]],
    "rapidocr": [[sys.executable, "-m", "pip", "install", "rapidocr-onnxruntime"]],
}

INSTALL_NOTES = {
    "ffmpeg": "通过 static-ffmpeg 安装(含 ~80MB 二进制下载,稍等片刻)",
    "slidegeist": "pip install slidegeist",
    "faster_whisper": "pip install faster-whisper",
    "rapidocr": "pip install rapidocr-onnxruntime",
}
