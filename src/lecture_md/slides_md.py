"""Parsing and editing helpers for slidegeist-style slide Markdown files."""

import json
import re
from typing import Any


TIMESTAMP_RE = r"(?:\d{1,2}:)?\d+:\d{2}"
ANCHOR_RE = re.compile(r'(?m)^<a name="(slide_\d+)"></a>\s*$')
TRANSCRIPT_RE = re.compile(r"(?ms)^(### Transcript\s*\n+)(.*?)(?=^---\s*$|^### |\Z)")
IMAGE_RE = re.compile(r"\[!\[Slide\]\(slides/([^)]+)\)\]\(slides/[^)]+\)")


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


def parse_sections(markdown: str, *, require_time_range: bool = False) -> tuple[str, list[dict[str, Any]]]:
    """Split slide Markdown into a header and per-slide section dicts."""
    matches = list(ANCHOR_RE.finditer(markdown))
    if not matches:
        raise ValueError("No slide anchors found.")
    header = markdown[: matches[0].start()]
    sections: list[dict[str, Any]] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(markdown)
        block = markdown[start:end]
        range_match = re.search(rf"\*\*Time:\*\*\s*({TIMESTAMP_RE})\s*-\s*({TIMESTAMP_RE})", block)
        time_match = re.search(r"\*\*Time:\*\*\s*([^\n]+)", block)
        image_match = IMAGE_RE.search(block)
        transcript_match = TRANSCRIPT_RE.search(block)
        if require_time_range and not range_match:
            raise ValueError(f"No time range found for {match.group(1)}")
        sections.append(
            {
                "slide_id": match.group(1),
                "block": block,
                "time": time_match.group(1).strip() if time_match else "",
                "start": timestamp_to_seconds(range_match.group(1)) if range_match else 0.0,
                "end": timestamp_to_seconds(range_match.group(2)) if range_match else 0.0,
                "image": image_match.group(1) if image_match else "",
                "transcript": transcript_match.group(2).strip() if transcript_match else "",
            }
        )
    return header, sections


def replace_transcript(block: str, transcript: str) -> str:
    """Replace (or insert) the ``### Transcript`` section of a slide block."""
    if "### Transcript" not in block:
        insert_at = block.rfind("\n---")
        if insert_at == -1:
            return block.rstrip() + f"\n\n### Transcript\n\n{transcript}\n"
        return block[:insert_at].rstrip() + f"\n\n### Transcript\n\n{transcript}\n\n" + block[insert_at:]
    return TRANSCRIPT_RE.sub(lambda m: m.group(1) + transcript.strip() + "\n\n", block, count=1)


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse the first JSON object out of a model response."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        raise ValueError(f"No JSON object found in response: {text[:200]}")
    return json.loads(match.group(0))


def load_json_records(path: Any) -> dict[str, dict[str, Any]]:
    """Load a JSON list file into a slide_id-keyed dict (tolerates absence)."""
    if not path or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return {}
    records: dict[str, dict[str, Any]] = {}
    for item in data:
        if isinstance(item, dict) and item.get("slide_id"):
            records[str(item["slide_id"])] = item
    return records
