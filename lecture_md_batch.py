import argparse
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from lecture_md_asr import run_asr
from lecture_md_correct import run_correction


VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert lecture videos to slide-aligned Markdown notes.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--video", type=Path, help="Process one video file.")
    source.add_argument("--input-dir", type=Path, help="Process videos in a directory.")
    parser.add_argument("--today", action="store_true", help="Only process files modified today.")
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--scene-threshold", default="0.001")
    parser.add_argument("--min-scene-len", default="5")
    parser.add_argument("--start-offset", default="0")
    parser.add_argument("--max-chunk-seconds", default=90.0, type=float)
    parser.add_argument("--padding", default=2.0, type=float)
    parser.add_argument("--sleep", default=5.0, type=float)
    parser.add_argument("--retries", default=12, type=int)
    parser.add_argument("--retry-sleep", default=30.0, type=float)
    parser.add_argument("--timeout", default=600.0, type=float)
    parser.add_argument("--skip-existing", action="store_true")
    return parser.parse_args()


def safe_name(path: Path) -> str:
    name = re.sub(r"[\\/:*?\"<>|]+", "_", path.stem)
    name = re.sub(r"\s+", "_", name).strip("_")
    return name or "video"


def iter_videos(input_dir: Path, today_only: bool) -> list[Path]:
    today = datetime.now().date()
    videos: list[Path] = []
    for path in input_dir.iterdir():
        if not path.is_file() or path.suffix.lower() not in VIDEO_EXTS:
            continue
        if today_only and datetime.fromtimestamp(path.stat().st_mtime).date() != today:
            continue
        videos.append(path)
    return sorted(videos, key=lambda item: item.stat().st_mtime)


def run_slidegeist(
    *,
    video: Path,
    out_dir: Path,
    scene_threshold: str,
    min_scene_len: str,
    start_offset: str,
    log_path: Path,
) -> None:
    cmd = [
        "slidegeist",
        "process",
        str(video),
        "--out",
        str(out_dir),
        "--scene-threshold",
        scene_threshold,
        "--min-scene-len",
        min_scene_len,
        "--start-offset",
        start_offset,
        "--model",
        "base",
        "-v",
    ]
    with log_path.open("a", encoding="utf-8") as log:
        log.write("\n$ " + " ".join(cmd) + "\n")
        log.flush()
        subprocess.run(
            cmd,
            check=True,
            text=True,
            stdout=log,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
        )


def process_video(args: argparse.Namespace, video: Path) -> dict:
    out_dir = args.output_root / safe_name(video)
    final_md = out_dir / "slides_mimo_asr_corrected.md"
    if args.skip_existing and final_md.exists():
        return {"video": str(video), "output": str(out_dir), "final_md": str(final_md), "status": "skipped"}

    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "batch.log"
    print(f"Processing {video.name}", flush=True)

    run_slidegeist(
        video=video,
        out_dir=out_dir,
        scene_threshold=args.scene_threshold,
        min_scene_len=args.min_scene_len,
        start_offset=args.start_offset,
        log_path=log_path,
    )
    run_asr(
        video=video,
        slides_md=out_dir / "slides.md",
        out_md=out_dir / "slides_mimo_asr.md",
        out_json=out_dir / "mimo_asr.json",
        padding=args.padding,
        max_chunk_seconds=args.max_chunk_seconds,
        sleep=args.sleep,
        retries=args.retries,
        retry_sleep=args.retry_sleep,
        resume=True,
    )
    run_correction(
        slides_md=out_dir / "slides_mimo_asr.md",
        out_md=final_md,
        out_json=out_dir / "mimo_asr_corrections.json",
        sleep=args.sleep,
        retries=args.retries,
        retry_sleep=args.retry_sleep,
        timeout=args.timeout,
        resume=True,
    )
    return {"video": str(video), "output": str(out_dir), "final_md": str(final_md), "status": "ok"}


def write_index(output_root: Path, records: list[dict]) -> None:
    lines = [
        "# Lecture Markdown Outputs",
        "",
        "| Video | Status | Final Markdown |",
        "| --- | --- | --- |",
    ]
    for record in records:
        final_md = Path(record.get("final_md", ""))
        output = Path(record.get("output", ""))
        label = output.name or Path(record["video"]).stem
        if final_md.exists():
            link = final_md.relative_to(output_root).as_posix()
            lines.append(f"| {label} | {record['status']} | [{final_md.name}]({link}) |")
        else:
            lines.append(f"| {label} | {record['status']} |  |")
    output_root.joinpath("index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    if not os.environ.get("MIMO_API_KEY"):
        raise RuntimeError("Set MIMO_API_KEY before running.")

    args.output_root.mkdir(parents=True, exist_ok=True)
    videos = [args.video] if args.video else iter_videos(args.input_dir, args.today)
    records: list[dict] = []
    manifest_path = args.output_root / "manifest.json"

    for video in videos:
        try:
            record = process_video(args, video)
        except Exception as exc:
            record = {"video": str(video), "output": "", "final_md": "", "status": "failed", "error": str(exc)}
            print(f"Failed {video}: {exc}", flush=True)
        records.append(record)
        manifest_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    write_index(args.output_root, records)
    print(f"Wrote {manifest_path}", flush=True)
    print(f"Wrote {args.output_root / 'index.md'}", flush=True)


if __name__ == "__main__":
    main()

