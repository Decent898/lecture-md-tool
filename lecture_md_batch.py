import argparse
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from lecture_md_asr import DEFAULT_BASE_URL as DEFAULT_ASR_BASE_URL
from lecture_md_asr import run_asr
from lecture_md_correct import DEFAULT_BASE_URL as DEFAULT_OPTIMIZE_BASE_URL
from lecture_md_correct import DEFAULT_TERMS
from lecture_md_correct import run_correction
from lecture_md_dedupe import dedupe_slides


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
    parser.add_argument("--dedupe-slides", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dedupe-hash-distance", default=6, type=int)
    parser.add_argument("--dedupe-rms", default=4.0, type=float)
    parser.add_argument("--dedupe-min-slide-seconds", default=2.0, type=float)
    parser.add_argument("--dedupe-max-slide-seconds", default=300.0, type=float)
    parser.add_argument("--dedupe-crop-ratio", default=0.04, type=float)
    parser.add_argument("--asr", choices=["api", "local"], default="api", help="ASR backend: MiMo API or local Whisper.")
    parser.add_argument("--optimize", choices=["api", "none"], default="api", help="Language optimization backend.")
    parser.add_argument("--asr-base-url", default=DEFAULT_ASR_BASE_URL, help="ASR API base URL when --asr api.")
    parser.add_argument(
        "--optimize-base-url",
        default=DEFAULT_OPTIMIZE_BASE_URL,
        help="Optimization API base URL when --optimize api.",
    )
    parser.add_argument("--asr-model", default="mimo-v2.5-asr", help="MiMo ASR model when --asr api.")
    parser.add_argument("--optimize-model", default="mimo-v2.5-pro", help="MiMo text model when --optimize api.")
    parser.add_argument("--asr-language", default="zh", help="ASR language code, or auto for local auto-detect.")
    parser.add_argument("--local-asr-model", default="small", help="faster-whisper model name for --asr local.")
    parser.add_argument("--local-asr-device", default="cpu", help="faster-whisper device: cpu, cuda, or auto.")
    parser.add_argument("--local-asr-compute-type", default="int8", help="faster-whisper compute type.")
    parser.add_argument("--local-asr-beam-size", default=5, type=int)
    parser.add_argument("--max-chunk-seconds", default=90.0, type=float)
    parser.add_argument("--padding", default=2.0, type=float)
    parser.add_argument("--sleep", default=5.0, type=float)
    parser.add_argument("--retries", default=12, type=int)
    parser.add_argument("--retry-sleep", default=30.0, type=float)
    parser.add_argument("--timeout", default=600.0, type=float)
    parser.add_argument("--terms", default=DEFAULT_TERMS, help="Course/domain terms for API language optimization.")
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
        "slides",
        str(video),
        "--out",
        str(out_dir),
        "--scene-threshold",
        scene_threshold,
        "--min-scene-len",
        min_scene_len,
        "--start-offset",
        start_offset,
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
    asr_md = out_dir / "slides_asr.md"
    final_md = out_dir / ("slides_optimized.md" if args.optimize == "api" else "slides_asr.md")
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
    slides_md = out_dir / "slides.md"
    if args.dedupe_slides:
        summary = dedupe_slides(
            slides_md=slides_md,
            out_md=slides_md,
            out_json=out_dir / "slides_dedupe.json",
            max_hash_distance=args.dedupe_hash_distance,
            max_rms=args.dedupe_rms,
            min_slide_seconds=args.dedupe_min_slide_seconds,
            max_slide_seconds=args.dedupe_max_slide_seconds,
            crop_ratio=args.dedupe_crop_ratio,
            keep_raw=True,
        )
        with log_path.open("a", encoding="utf-8") as log:
            log.write(
                f"\nDeduped slides: {summary['input_slides']} -> {summary['output_slides']} "
                f"(merged {summary['merged_slides']})\n"
            )
        print(
            f"Deduped slides: {summary['input_slides']} -> {summary['output_slides']} "
            f"(merged {summary['merged_slides']})",
            flush=True,
        )
    run_asr(
        video=video,
        slides_md=slides_md,
        out_md=asr_md,
        out_json=out_dir / "asr.json",
        backend=args.asr,
        base_url=args.asr_base_url,
        model=args.asr_model,
        language=args.asr_language,
        local_model=args.local_asr_model,
        local_device=args.local_asr_device,
        local_compute_type=args.local_asr_compute_type,
        local_beam_size=args.local_asr_beam_size,
        padding=args.padding,
        max_chunk_seconds=args.max_chunk_seconds,
        sleep=args.sleep,
        retries=args.retries,
        retry_sleep=args.retry_sleep,
        resume=True,
    )
    if args.optimize == "api":
        run_correction(
            slides_md=asr_md,
            out_md=final_md,
            out_json=out_dir / "optimization.json",
            base_url=args.optimize_base_url,
            model=args.optimize_model,
            sleep=args.sleep,
            retries=args.retries,
            retry_sleep=args.retry_sleep,
            timeout=args.timeout,
            terms=args.terms,
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
        if record.get("final_md") and final_md.exists():
            link = final_md.relative_to(output_root).as_posix()
            lines.append(f"| {label} | {record['status']} | [{final_md.name}]({link}) |")
        else:
            lines.append(f"| {label} | {record['status']} |  |")
    output_root.joinpath("index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    if (args.asr == "api" or args.optimize == "api") and not os.environ.get("MIMO_API_KEY"):
        raise RuntimeError("Set MIMO_API_KEY, or use --asr local --optimize none.")

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
