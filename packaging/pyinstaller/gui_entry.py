"""PyInstaller entry point for the lecture-md desktop app."""

from __future__ import annotations

import os
import subprocess
import sys
from functools import wraps

from lecture_md.runtime import prepend_runtime_paths


def force_utf8_runtime() -> None:
    """Keep frozen Windows child-process output away from the system ANSI codec."""
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    os.environ.setdefault("PYTHONLEGACYWINDOWSSTDIO", "0")
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def patch_subprocess_text_encoding() -> None:
    """Default text-mode subprocess decoding to UTF-8 with replacement.

    Some bundled dependencies, notably slidegeist's ffmpeg scene detection path,
    use ``text=True``/``universal_newlines=True`` without an explicit encoding.
    On Windows that falls back to the active ANSI code page (often GBK), which
    can crash on arbitrary ffmpeg bytes. Only text-mode calls are touched.
    """

    def needs_encoding(kwargs: dict) -> bool:
        if kwargs.get("encoding") or kwargs.get("errors"):
            return False
        return bool(kwargs.get("text") or kwargs.get("universal_newlines"))

    original_run = subprocess.run
    original_popen = subprocess.Popen

    @wraps(original_run)
    def run_utf8(*args, **kwargs):
        if needs_encoding(kwargs):
            kwargs.setdefault("encoding", "utf-8")
            kwargs.setdefault("errors", "replace")
        return original_run(*args, **kwargs)

    class PopenUtf8(original_popen):
        def __init__(self, *args, **kwargs):
            if needs_encoding(kwargs):
                kwargs.setdefault("encoding", "utf-8")
                kwargs.setdefault("errors", "replace")
            super().__init__(*args, **kwargs)

    subprocess.run = run_utf8
    subprocess.Popen = PopenUtf8


if __name__ == "__main__":
    force_utf8_runtime()
    patch_subprocess_text_encoding()
    os.environ["PATH"] = prepend_runtime_paths(os.environ.get("PATH", ""))
    if len(sys.argv) > 1 and sys.argv[1] == "--lecture-md-cli":
        from lecture_md.cli import main

        main(sys.argv[2:])
    elif len(sys.argv) > 1 and sys.argv[1] == "--slidegeist-cli":
        from slidegeist.cli import main

        sys.argv = ["slidegeist", *sys.argv[2:]]
        main()
    else:
        from lecture_md.gui import main

        main()
