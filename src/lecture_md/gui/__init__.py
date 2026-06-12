"""lecture-md desktop GUI (PyQt6).

This package is imported lazily by the CLI: nothing here pulls in PyQt6 at
module import time, so ``lecture-md --help`` keeps working without the
``[gui]`` extra installed.
"""

import argparse
import sys

INSTALL_HINT = (
    "未安装 PyQt6,无法启动桌面界面。\n\n"
    "请先安装 GUI 依赖:\n"
    "    pip install \"lecture-md-tool[gui]\"\n"
    "或:\n"
    "    pip install PyQt6\n"
)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--output-root",
        default=None,
        help="Preset the output root directory shown in the GUI.",
    )


def main(output_root: str | None = None) -> None:
    try:
        import PyQt6  # noqa: F401
    except ImportError:
        print(INSTALL_HINT, file=sys.stderr)
        raise SystemExit(1)
    from lecture_md.gui.app import launch

    launch(output_root=output_root)


def run_cli(args: argparse.Namespace) -> None:
    main(output_root=getattr(args, "output_root", None))
