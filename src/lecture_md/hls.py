"""Merge local HLS .ts segment folders into .mp4 files with ffmpeg."""

import argparse
import re
import subprocess
import tempfile
from pathlib import Path

from lecture_md.runtime import resolve_executable


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--glob", default="*.m3u8")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")


def numeric_key(path: Path) -> tuple[int, str]:
    match = re.fullmatch(r"(\d+)\.ts", path.name)
    if match:
        return int(match.group(1)), path.name
    return 10**12, path.name


def quote_concat_path(path: Path) -> str:
    text = path.resolve().as_posix().replace("'", r"'\''")
    return f"file '{text}'"


def merge_playlist(playlist: Path, ffmpeg: str, overwrite: bool, dry_run: bool) -> tuple[str, Path, int]:
    ffmpeg = resolve_executable("ffmpeg", "LECTURE_MD_FFMPEG") if ffmpeg == "ffmpeg" else ffmpeg
    segment_dir = playlist.with_suffix("")
    output = playlist.with_suffix(".mp4")
    if output.exists() and not overwrite:
        return "skipped", output, 0
    if not segment_dir.is_dir():
        raise FileNotFoundError(f"Missing segment directory: {segment_dir}")
    segments = sorted(segment_dir.glob("*.ts"), key=numeric_key)
    if not segments:
        raise FileNotFoundError(f"No .ts segments in: {segment_dir}")

    if dry_run:
        return "dry-run", output, len(segments)

    with tempfile.TemporaryDirectory(prefix="hls-concat-") as temp_dir:
        concat_file = Path(temp_dir) / "segments.txt"
        concat_file.write_text("\n".join(quote_concat_path(path) for path in segments), encoding="utf-8")
        cmd = [
            ffmpeg,
            "-y" if overwrite else "-n",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output),
        ]
        subprocess.run(cmd, check=True)
    return "merged", output, len(segments)


def run_cli(args: argparse.Namespace) -> None:
    playlists = sorted(args.input_dir.glob(args.glob), key=lambda path: path.name)
    if not playlists:
        raise SystemExit(f"No playlists matched {args.glob} under {args.input_dir}")

    for playlist in playlists:
        status, output, count = merge_playlist(playlist, args.ffmpeg, args.overwrite, args.dry_run)
        print(f"{status}: {playlist.name} -> {output.name} ({count} segments)", flush=True)
