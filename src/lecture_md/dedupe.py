"""Slide cut cleanup: debounce or merge unstable slidegeist slide cuts."""

import argparse
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageStat

from lecture_md.slides_md import TIMESTAMP_RE, seconds_to_timestamp, timestamp_to_seconds


@dataclass
class SlideSection:
    slide_id: str
    title: str
    start_text: str
    end_text: str
    start_seconds: float
    end_seconds: float
    image_name: str


@dataclass
class ImageSignature:
    dhash: int
    thumb: Image.Image


def parse_slides(markdown: str) -> tuple[str, list[SlideSection]]:
    matches = list(re.finditer(r'(?m)^<a name="(slide_\d+)"></a>\s*$', markdown))
    if not matches:
        raise ValueError("No slide anchors found.")
    header = markdown[: matches[0].start()]
    sections: list[SlideSection] = []
    for idx, match in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(markdown)
        block = markdown[match.start() : end]
        title_match = re.search(r"(?m)^##\s+(.+?)\s*$", block)
        time_match = re.search(rf"\*\*Time:\*\*\s*({TIMESTAMP_RE})\s*-\s*({TIMESTAMP_RE})", block)
        image_match = re.search(r"\[!\[Slide\]\(slides/([^)]+)\)\]\(slides/[^)]+\)", block)
        if not time_match or not image_match:
            continue
        sections.append(
            SlideSection(
                slide_id=match.group(1),
                title=title_match.group(1).strip() if title_match else match.group(1),
                start_text=time_match.group(1),
                end_text=time_match.group(2),
                start_seconds=timestamp_to_seconds(time_match.group(1)),
                end_seconds=timestamp_to_seconds(time_match.group(2)),
                image_name=image_match.group(1),
            )
        )
    return header, sections


def image_signature(path: Path, crop_ratio: float) -> ImageSignature:
    with Image.open(path) as image:
        gray = image.convert("L")
        if 0 < crop_ratio < 0.45:
            width, height = gray.size
            dx = int(width * crop_ratio)
            dy = int(height * crop_ratio)
            gray = gray.crop((dx, dy, width - dx, height - dy))
        small = gray.resize((9, 8), Image.Resampling.LANCZOS)
        values = list(small.getdata())
        bits = 0
        for row in range(8):
            for col in range(8):
                left = values[row * 9 + col]
                right = values[row * 9 + col + 1]
                bits = (bits << 1) | int(left > right)
        thumb = gray.resize((64, 36), Image.Resampling.LANCZOS)
    return ImageSignature(dhash=bits, thumb=thumb)


def hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def rmsdiff(left: Image.Image, right: Image.Image) -> float:
    diff = ImageChops.difference(left, right)
    stat = ImageStat.Stat(diff)
    return sum(value * value for value in stat.rms) ** 0.5 / len(stat.rms)


def visual_metrics(current: ImageSignature, previous: ImageSignature) -> dict[str, float | int]:
    return {
        "hash_distance": hamming_distance(current.dhash, previous.dhash),
        "rms": rmsdiff(current.thumb, previous.thumb),
    }


def near_duplicate(metrics: dict[str, float | int], *, max_hash_distance: int, max_rms: float) -> bool:
    return int(metrics["hash_distance"]) <= max_hash_distance and float(metrics["rms"]) <= max_rms


def format_slide_block(index: int, start: float, end: float, image_name: str) -> str:
    slide_id = f"slide_{index:03d}"
    return (
        f'<a name="{slide_id}"></a>\n'
        f"## Slide {index}\n\n"
        f"**Time:** {seconds_to_timestamp(start)} - {seconds_to_timestamp(end)}\n\n"
        f"[![Slide](slides/{image_name})](slides/{image_name})\n\n"
        "---\n\n"
    )


def new_kept_slide(section: SlideSection, reason: str) -> dict[str, Any]:
    return {
        "source_slide_id": section.slide_id,
        "image": section.image_name,
        "start_seconds": section.start_seconds,
        "end_seconds": section.end_seconds,
        "original_duration_seconds": max(section.end_seconds - section.start_seconds, 0.0),
        "merged_from": [section.slide_id],
        "decision": reason,
        "merge_reasons": [],
    }


def can_extend_slide(last_kept: dict[str, Any], section: SlideSection, max_slide_seconds: float) -> bool:
    if max_slide_seconds <= 0:
        return True
    return section.end_seconds - float(last_kept["start_seconds"]) <= max_slide_seconds


def merge_slide(
    last_kept: dict[str, Any],
    section: SlideSection,
    *,
    reason: str,
    metrics: dict[str, float | int] | None = None,
) -> None:
    last_kept["end_seconds"] = max(float(last_kept["end_seconds"]), section.end_seconds)
    last_kept["merged_from"].append(section.slide_id)
    item: dict[str, Any] = {
        "slide_id": section.slide_id,
        "reason": reason,
        "duration_seconds": max(section.end_seconds - section.start_seconds, 0.0),
    }
    if metrics is not None:
        item["hash_distance"] = int(metrics["hash_distance"])
        item["rms"] = round(float(metrics["rms"]), 4)
    last_kept["merge_reasons"].append(item)


def run_merge_dedupe(
    *,
    sections: list[SlideSection],
    signatures: list[ImageSignature],
    max_hash_distance: int,
    max_rms: float,
    min_slide_seconds: float,
    max_slide_seconds: float,
) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    last_signature: ImageSignature | None = None
    last_kept: dict[str, Any] | None = None

    for section, signature in zip(sections, signatures, strict=True):
        duration = max(section.end_seconds - section.start_seconds, 0.0)
        should_merge = False
        metrics: dict[str, float | int] | None = None
        if last_signature is not None and last_kept is not None:
            metrics = visual_metrics(signature, last_signature)
            visually_same = int(metrics["hash_distance"]) <= max_hash_distance or float(metrics["rms"]) <= max_rms
            too_short = duration < min_slide_seconds
            should_merge = (visually_same or too_short) and can_extend_slide(last_kept, section, max_slide_seconds)

        if should_merge and last_kept is not None:
            merge_slide(last_kept, section, reason="merge_visual_or_short", metrics=metrics)
            last_signature = signature
            continue

        last_kept = new_kept_slide(section, "kept")
        kept.append(last_kept)
        last_signature = signature

    return kept


def run_debounce_dedupe(
    *,
    sections: list[SlideSection],
    signatures: list[ImageSignature],
    max_hash_distance: int,
    max_rms: float,
    min_slide_seconds: float,
    stable_seconds: float,
    max_slide_seconds: float,
) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    kept_signatures: list[ImageSignature] = []
    force_merge_return_indices: set[int] = set()

    for index, (section, signature) in enumerate(zip(sections, signatures, strict=True)):
        if not kept:
            kept.append(new_kept_slide(section, "kept_first"))
            kept_signatures.append(signature)
            continue

        last_kept = kept[-1]
        last_signature = kept_signatures[-1]
        duration = max(section.end_seconds - section.start_seconds, 0.0)
        unstable = stable_seconds > 0 and duration < stable_seconds
        too_short = min_slide_seconds > 0 and duration < min_slide_seconds
        metrics = visual_metrics(signature, last_signature)
        same_as_last_kept = near_duplicate(metrics, max_hash_distance=max_hash_distance, max_rms=max_rms)
        within_max_duration = can_extend_slide(last_kept, section, max_slide_seconds)

        next_returns_to_last_kept = False
        if index + 1 < len(sections):
            next_metrics = visual_metrics(signatures[index + 1], last_signature)
            next_returns_to_last_kept = near_duplicate(
                next_metrics,
                max_hash_distance=max_hash_distance,
                max_rms=max_rms,
            )

        merge_reason: str | None = None
        last_was_short_candidate = str(last_kept.get("decision", "")) == "kept_distinct_short"

        if index in force_merge_return_indices and same_as_last_kept:
            merge_reason = "debounce_return_to_saved_slide"
        elif same_as_last_kept and last_was_short_candidate:
            merge_reason = "debounce_confirm_short_candidate"
        elif same_as_last_kept and (too_short or unstable):
            merge_reason = "debounce_unstable_same_as_saved"
        elif unstable and next_returns_to_last_kept:
            merge_reason = "debounce_unstable_return_to_saved_slide"
            force_merge_return_indices.add(index + 1)

        if merge_reason and within_max_duration:
            merge_slide(last_kept, section, reason=merge_reason, metrics=metrics)
            continue

        kept.append(new_kept_slide(section, "kept_stable" if not unstable else "kept_distinct_short"))
        kept_signatures.append(signature)

    return kept


def dedupe_slides(
    *,
    slides_md: Path,
    out_md: Path,
    out_json: Path,
    mode: str = "debounce",
    max_hash_distance: int = 6,
    max_rms: float = 4.0,
    min_slide_seconds: float = 2.0,
    stable_seconds: float = 6.0,
    max_slide_seconds: float = 300.0,
    crop_ratio: float = 0.04,
    keep_raw: bool = True,
) -> dict[str, Any]:
    if mode not in {"debounce", "merge"}:
        raise ValueError("mode must be 'debounce' or 'merge'.")

    markdown = slides_md.read_text(encoding="utf-8")
    header, sections = parse_slides(markdown)
    if not sections:
        raise ValueError("No parseable slide sections found.")

    if keep_raw and slides_md == out_md:
        raw_md = slides_md.with_name("slides_raw.md")
        if not raw_md.exists():
            shutil.copy2(slides_md, raw_md)

    slides_dir = slides_md.parent / "slides"
    parseable_sections: list[SlideSection] = []
    signatures: list[ImageSignature] = []
    for section in sections:
        image_path = slides_dir / section.image_name
        if not image_path.exists():
            continue
        parseable_sections.append(section)
        signatures.append(image_signature(image_path, crop_ratio))

    if mode == "merge":
        kept = run_merge_dedupe(
            sections=parseable_sections,
            signatures=signatures,
            max_hash_distance=max_hash_distance,
            max_rms=max_rms,
            min_slide_seconds=min_slide_seconds,
            max_slide_seconds=max_slide_seconds,
        )
    else:
        kept = run_debounce_dedupe(
            sections=parseable_sections,
            signatures=signatures,
            max_hash_distance=max_hash_distance,
            max_rms=max_rms,
            min_slide_seconds=min_slide_seconds,
            stable_seconds=stable_seconds,
            max_slide_seconds=max_slide_seconds,
        )

    body = []
    for index, item in enumerate(kept, start=1):
        body.append(
            format_slide_block(
                index,
                float(item["start_seconds"]),
                float(item["end_seconds"]),
                str(item["image"]),
            )
        )
    out_md.write_text(header.rstrip() + "\n\n---\n\n" + "".join(body), encoding="utf-8")

    summary = {
        "input_slides": len(sections),
        "output_slides": len(kept),
        "merged_slides": len(sections) - len(kept),
        "mode": mode,
        "max_hash_distance": max_hash_distance,
        "max_rms": max_rms,
        "min_slide_seconds": min_slide_seconds,
        "stable_seconds": stable_seconds,
        "max_slide_seconds": max_slide_seconds,
        "crop_ratio": crop_ratio,
        "slides": kept,
    }
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--slides-md", required=True, type=Path)
    parser.add_argument("--out-md", required=True, type=Path)
    parser.add_argument("--out-json", required=True, type=Path)
    parser.add_argument("--mode", choices=["debounce", "merge"], default="debounce")
    parser.add_argument("--max-hash-distance", default=6, type=int)
    parser.add_argument("--max-rms", default=4.0, type=float)
    parser.add_argument("--min-slide-seconds", default=2.0, type=float)
    parser.add_argument("--stable-seconds", default=6.0, type=float)
    parser.add_argument("--max-slide-seconds", default=300.0, type=float)
    parser.add_argument("--crop-ratio", default=0.04, type=float)
    parser.add_argument("--no-keep-raw", action="store_true")


def run_cli(args: argparse.Namespace) -> None:
    summary = dedupe_slides(
        slides_md=args.slides_md,
        out_md=args.out_md,
        out_json=args.out_json,
        mode=args.mode,
        max_hash_distance=args.max_hash_distance,
        max_rms=args.max_rms,
        min_slide_seconds=args.min_slide_seconds,
        stable_seconds=args.stable_seconds,
        max_slide_seconds=args.max_slide_seconds,
        crop_ratio=args.crop_ratio,
        keep_raw=not args.no_keep_raw,
    )
    print(f"Slides: {summary['input_slides']} -> {summary['output_slides']}", flush=True)
