import argparse
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageStat


TIMESTAMP_RE = r"(?:\d{1,2}:)?\d+:\d{2}"


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


def timestamp_to_seconds(text: str) -> float:
    parts = [int(part) for part in text.strip().split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    raise ValueError(f"Unsupported timestamp: {text}")


def seconds_to_timestamp(seconds: float) -> str:
    rounded = max(int(round(seconds)), 0)
    hours, remainder = divmod(rounded, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


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


def same_slide(
    current: ImageSignature,
    previous: ImageSignature,
    *,
    max_hash_distance: int,
    max_rms: float,
) -> bool:
    return hamming_distance(current.dhash, previous.dhash) <= max_hash_distance or rmsdiff(current.thumb, previous.thumb) <= max_rms


def format_slide_block(index: int, start: float, end: float, image_name: str) -> str:
    slide_id = f"slide_{index:03d}"
    return (
        f'<a name="{slide_id}"></a>\n'
        f"## Slide {index}\n\n"
        f"**Time:** {seconds_to_timestamp(start)} - {seconds_to_timestamp(end)}\n\n"
        f"[![Slide](slides/{image_name})](slides/{image_name})\n\n"
        "---\n\n"
    )


def dedupe_slides(
    *,
    slides_md: Path,
    out_md: Path,
    out_json: Path,
    max_hash_distance: int = 6,
    max_rms: float = 4.0,
    min_slide_seconds: float = 2.0,
    max_slide_seconds: float = 300.0,
    crop_ratio: float = 0.04,
    keep_raw: bool = True,
) -> dict[str, Any]:
    markdown = slides_md.read_text(encoding="utf-8")
    header, sections = parse_slides(markdown)
    if not sections:
        raise ValueError("No parseable slide sections found.")

    if keep_raw and slides_md == out_md:
        raw_md = slides_md.with_name("slides_raw.md")
        if not raw_md.exists():
            shutil.copy2(slides_md, raw_md)

    slides_dir = slides_md.parent / "slides"
    kept: list[dict[str, Any]] = []
    last_signature: ImageSignature | None = None
    last_kept: dict[str, Any] | None = None

    for section in sections:
        image_path = slides_dir / section.image_name
        if not image_path.exists():
            continue
        signature = image_signature(image_path, crop_ratio)
        duration = max(section.end_seconds - section.start_seconds, 0.0)
        should_merge = False
        if last_signature is not None and last_kept is not None:
            merged_duration = section.end_seconds - float(last_kept["start_seconds"])
            visually_same = same_slide(
                signature,
                last_signature,
                max_hash_distance=max_hash_distance,
                max_rms=max_rms,
            )
            too_short = duration < min_slide_seconds
            within_max_duration = max_slide_seconds <= 0 or merged_duration <= max_slide_seconds
            should_merge = (visually_same or too_short) and within_max_duration

        if should_merge and last_kept is not None:
            last_kept["end_seconds"] = max(float(last_kept["end_seconds"]), section.end_seconds)
            last_kept["merged_from"].append(section.slide_id)
            last_signature = signature
            continue

        last_kept = {
            "source_slide_id": section.slide_id,
            "image": section.image_name,
            "start_seconds": section.start_seconds,
            "end_seconds": section.end_seconds,
            "merged_from": [section.slide_id],
        }
        kept.append(last_kept)
        last_signature = signature

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
        "max_hash_distance": max_hash_distance,
        "max_rms": max_rms,
        "min_slide_seconds": min_slide_seconds,
        "max_slide_seconds": max_slide_seconds,
        "crop_ratio": crop_ratio,
        "slides": kept,
    }
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slides-md", required=True, type=Path)
    parser.add_argument("--out-md", required=True, type=Path)
    parser.add_argument("--out-json", required=True, type=Path)
    parser.add_argument("--max-hash-distance", default=6, type=int)
    parser.add_argument("--max-rms", default=4.0, type=float)
    parser.add_argument("--min-slide-seconds", default=2.0, type=float)
    parser.add_argument("--max-slide-seconds", default=300.0, type=float)
    parser.add_argument("--crop-ratio", default=0.04, type=float)
    parser.add_argument("--no-keep-raw", action="store_true")
    args = parser.parse_args()
    summary = dedupe_slides(
        slides_md=args.slides_md,
        out_md=args.out_md,
        out_json=args.out_json,
        max_hash_distance=args.max_hash_distance,
        max_rms=args.max_rms,
        min_slide_seconds=args.min_slide_seconds,
        max_slide_seconds=args.max_slide_seconds,
        crop_ratio=args.crop_ratio,
        keep_raw=not args.no_keep_raw,
    )
    print(f"Slides: {summary['input_slides']} -> {summary['output_slides']}", flush=True)


if __name__ == "__main__":
    main()
