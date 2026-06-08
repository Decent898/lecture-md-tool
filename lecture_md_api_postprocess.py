import argparse
import json
import os
import re
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path
from typing import Any

from lecture_md_correct import DEFAULT_BASE_URL, DEFAULT_MODEL, DEFAULT_TERMS, run_correction
from lecture_md_notes import run_notes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Post-process completed slide ASR outputs with MiMo optimization and lecture-note generation."
    )
    parser.add_argument("--output-root", required=True, type=Path, help="Batch output root containing per-video folders.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--terms", default=DEFAULT_TERMS)
    parser.add_argument("--jobs", default=2, type=int, help="Number of video folders to process in parallel.")
    parser.add_argument("--sleep", default=0.0, type=float, help="Delay between API calls inside each video.")
    parser.add_argument("--retries", default=12, type=int)
    parser.add_argument("--retry-sleep", default=30.0, type=float)
    parser.add_argument("--timeout", default=600.0, type=float)
    parser.add_argument(
        "--stable-seconds",
        default=90.0,
        type=float,
        help="Only process slides_asr.md files whose mtime has been stable for this many seconds.",
    )
    parser.add_argument("--watch", action="store_true", help="Keep watching for new slides_asr.md files.")
    parser.add_argument("--poll-seconds", default=60.0, type=float)
    parser.add_argument("--keep-asr-md", action="store_true", help="Keep raw slides_asr.md after successful postprocess.")
    parser.add_argument("--overwrite", action="store_true", help="Regenerate optimized and lecture-note files.")
    parser.add_argument("--once", action="store_true", help="Exit after one scan even if --watch is set.")
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def file_ready(path: Path, stable_seconds: float) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    age = time.time() - path.stat().st_mtime
    return age >= stable_seconds


def has_good_file(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def json_record_count(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return len(data) if isinstance(data, list) else None


def slide_anchor_count(path: Path) -> int | None:
    if not path.exists():
        return None
    markdown = path.read_text(encoding="utf-8", errors="replace")
    return len(re.findall(r'(?m)^<a name="slide_\d+"></a>\s*$', markdown))


def postprocess_complete(out_dir: Path) -> bool:
    optimized_md = out_dir / "slides_optimized.md"
    notes_md = out_dir / "slides_lecture_notes.md"
    anchors = slide_anchor_count(optimized_md)
    optimization_records = json_record_count(out_dir / "optimization.json")
    lecture_note_records = json_record_count(out_dir / "lecture_notes.json")
    return (
        anchors is not None
        and anchors > 0
        and optimization_records == anchors
        and lecture_note_records == anchors
        and has_good_file(optimized_md)
        and has_good_file(notes_md)
    )


def find_candidates(root: Path, stable_seconds: float, overwrite: bool, in_flight: set[Path]) -> list[Path]:
    candidates: list[Path] = []
    for asr_md in sorted(root.glob("*/slides_asr.md"), key=lambda item: item.stat().st_mtime):
        out_dir = asr_md.parent
        if out_dir in in_flight:
            continue
        if not file_ready(asr_md, stable_seconds):
            continue
        optimized_md = out_dir / "slides_optimized.md"
        notes_md = out_dir / "slides_lecture_notes.md"
        if not overwrite and has_good_file(optimized_md) and has_good_file(notes_md) and postprocess_complete(out_dir):
            continue
        if not has_good_file(out_dir / "asr.json"):
            continue
        candidates.append(out_dir)
    return candidates


def load_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def write_manifest(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def append_manifest(path: Path, record: dict[str, Any]) -> None:
    records = load_manifest(path)
    records.append(record)
    write_manifest(path, records)


def process_dir(args: argparse.Namespace, out_dir: Path) -> dict[str, Any]:
    asr_md = out_dir / "slides_asr.md"
    optimized_md = out_dir / "slides_optimized.md"
    optimization_json = out_dir / "optimization.json"
    notes_md = out_dir / "slides_lecture_notes.md"
    lecture_notes_json = out_dir / "lecture_notes.json"
    asr_json = out_dir / "asr.json"

    record: dict[str, Any] = {
        "video_dir": str(out_dir),
        "started_at": now_iso(),
        "status": "running",
    }
    print(f"[Postprocess] {out_dir.name}", flush=True)

    if args.overwrite:
        for path in (optimized_md, optimization_json, notes_md, lecture_notes_json):
            path.unlink(missing_ok=True)

    run_correction(
        slides_md=asr_md,
        out_md=optimized_md,
        out_json=optimization_json,
        base_url=args.base_url,
        model=args.model,
        sleep=args.sleep,
        retries=args.retries,
        retry_sleep=args.retry_sleep,
        timeout=args.timeout,
        terms=args.terms,
        resume=True,
    )
    run_notes(
        slides_md=optimized_md,
        out_md=notes_md,
        out_json=lecture_notes_json,
        asr_json=asr_json,
        optimization_json=optimization_json,
        base_url=args.base_url,
        model=args.model,
        sleep=args.sleep,
        retries=args.retries,
        retry_sleep=args.retry_sleep,
        timeout=args.timeout,
        terms=args.terms,
        resume=True,
    )

    if not postprocess_complete(out_dir):
        anchors = slide_anchor_count(optimized_md)
        optimization_records = json_record_count(optimization_json)
        lecture_note_records = json_record_count(lecture_notes_json)
        raise RuntimeError(
            "Postprocess output is incomplete: "
            f"slides={anchors}, optimization_records={optimization_records}, "
            f"lecture_note_records={lecture_note_records}"
        )
    if not args.keep_asr_md:
        asr_md.unlink(missing_ok=True)

    record.update(
        {
            "finished_at": now_iso(),
            "status": "ok",
            "optimized_md": str(optimized_md),
            "lecture_notes_md": str(notes_md),
            "kept_asr_md": args.keep_asr_md,
        }
    )
    return record


def main() -> None:
    args = parse_args()
    if not os.environ.get("MIMO_API_KEY"):
        raise RuntimeError("Set MIMO_API_KEY before running API postprocess.")
    if args.jobs < 1:
        raise ValueError("--jobs must be at least 1")
    root = args.output_root
    root.mkdir(parents=True, exist_ok=True)
    manifest = root / "api_postprocess_manifest.json"

    in_flight: dict[Future[dict[str, Any]], Path] = {}
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        while True:
            candidates = find_candidates(root, args.stable_seconds, args.overwrite, set(in_flight.values()))
            for out_dir in candidates:
                if len(in_flight) >= args.jobs:
                    break
                future = executor.submit(process_dir, args, out_dir)
                in_flight[future] = out_dir

            if in_flight:
                done, _ = wait(in_flight.keys(), timeout=args.poll_seconds if args.watch else None, return_when=FIRST_COMPLETED)
                for future in done:
                    out_dir = in_flight.pop(future)
                    try:
                        record = future.result()
                    except Exception as exc:
                        record = {
                            "video_dir": str(out_dir),
                            "finished_at": now_iso(),
                            "status": "failed",
                            "error": str(exc),
                        }
                        print(f"[Postprocess failed] {out_dir.name}: {exc}", flush=True)
                    else:
                        print(f"[Postprocess ok] {out_dir.name}", flush=True)
                    append_manifest(manifest, record)
            elif args.watch and not args.once:
                print(f"[Postprocess] no ready ASR files; sleeping {args.poll_seconds:.0f}s", flush=True)
                time.sleep(args.poll_seconds)
            else:
                break

            if args.once:
                break

    print(f"Wrote {manifest}", flush=True)


if __name__ == "__main__":
    main()
