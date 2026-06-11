"""Unified ``lecture-md`` command line interface."""

import argparse

from lecture_md import __version__, asr, correct, dedupe, hls, notes, pdf, pipeline, postprocess


SUBCOMMANDS = [
    (
        "process",
        pipeline,
        "Run the full pipeline: slide extraction, dedupe, ASR, correction, notes.",
    ),
    (
        "postprocess",
        postprocess,
        "Watch finished ASR folders and run API correction + note generation.",
    ),
    ("asr", asr, "Transcribe one video's slide audio (single step)."),
    ("optimize", correct, "Correct an ASR Markdown file with OCR + chat model (single step)."),
    ("notes", notes, "Generate handout-style lecture notes (single step)."),
    ("dedupe", dedupe, "Clean unstable slide cuts in a slides.md file (single step)."),
    ("merge-hls", hls, "Merge local HLS .ts segment folders into .mp4 files."),
    ("to-pdf", pdf, "Render note Markdown files to PDF with a headless browser."),
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lecture-md",
        description="Turn lecture screen-recording videos into slide-aligned Markdown notes.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, module, help_text in SUBCOMMANDS:
        subparser = subparsers.add_parser(name, help=help_text, description=help_text)
        module.add_arguments(subparser)
        subparser.set_defaults(handler=module.run_cli)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.handler(args)


if __name__ == "__main__":
    main()
