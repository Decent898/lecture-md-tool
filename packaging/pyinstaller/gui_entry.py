"""PyInstaller entry point for the lecture-md desktop app."""

from __future__ import annotations

import os
import sys

from lecture_md.runtime import prepend_runtime_paths


if __name__ == "__main__":
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
