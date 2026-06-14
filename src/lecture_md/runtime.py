"""Runtime helpers for frozen desktop builds and normal Python installs."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    return Path(sys.executable).resolve().parent if is_frozen() else Path(sys.executable).resolve().parent


def bundle_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", app_dir())).resolve()


def cli_command(*args: str) -> tuple[str, list[str]]:
    """Return a command that runs ``lecture_md.cli`` without opening another GUI."""
    if is_frozen():
        return str(sys.executable), ["--lecture-md-cli", *args]
    return str(sys.executable), ["-m", "lecture_md", *args]


def slidegeist_command(*args: str) -> tuple[str, list[str]]:
    """Return a command that runs Slidegeist without requiring a system script."""
    if is_frozen():
        return str(sys.executable), ["--slidegeist-cli", *args]
    script = shutil.which("slidegeist")
    if script:
        return script, list(args)
    return str(sys.executable), ["-c", "import sys; from slidegeist.cli import main; sys.argv=['slidegeist']+sys.argv[1:]; main()", *args]


def _bundled_executable_names(name: str) -> list[str]:
    suffix = ".exe" if os.name == "nt" else ""
    return [name + suffix]


def _candidate_dirs() -> list[Path]:
    dirs = [app_dir(), bundle_dir()]
    for parent in (app_dir(), bundle_dir()):
        dirs.extend(
            [
                parent / "_internal",
                parent / "bin",
                parent / "static_ffmpeg",
                parent / "static_ffmpeg" / "bin",
                parent / "static_ffmpeg" / "bin" / sys.platform,
            ]
        )
    return dirs


def resolve_executable(name: str, env_var: str | None = None) -> str:
    """Resolve an executable from env override, frozen bundle, static-ffmpeg, then PATH."""
    if env_var:
        override = os.environ.get(env_var, "").strip()
        if override:
            return override

    for directory in _candidate_dirs():
        for exe_name in _bundled_executable_names(name):
            candidate = directory / exe_name
            if candidate.exists():
                return str(candidate)

    if name in {"ffmpeg", "ffprobe"}:
        static_dir = static_ffmpeg_dir()
        if static_dir:
            candidate = Path(static_dir) / _bundled_executable_names(name)[0]
            if candidate.exists():
                return str(candidate)

    return shutil.which(name) or name


def static_ffmpeg_dir() -> str | None:
    """Directory of cached static-ffmpeg binaries, if available without downloading."""
    try:
        import static_ffmpeg
    except ImportError:
        return None

    exe_name = _bundled_executable_names("ffmpeg")[0]
    candidates: list[Path] = []
    try:
        from static_ffmpeg import run

        candidates.append(Path(run.get_platform_dir()))
    except Exception:
        pass

    base = Path(static_ffmpeg.__file__).resolve().parent / "bin"
    platform_name = {"win32": "win32", "darwin": "darwin"}.get(sys.platform, "linux")
    candidates.extend([base / platform_name, base])

    for directory in candidates:
        if (directory / exe_name).exists():
            return str(directory)
    return None


def prepend_runtime_paths(env_path: str) -> str:
    dirs: list[str] = []
    ffmpeg_dir = static_ffmpeg_dir()
    if ffmpeg_dir:
        dirs.append(ffmpeg_dir)
    for directory in _candidate_dirs():
        if directory.exists():
            dirs.append(str(directory))
    seen: set[str] = set()
    unique = [path for path in dirs if not (path in seen or seen.add(path))]
    return os.pathsep.join([*unique, env_path]) if unique else env_path
