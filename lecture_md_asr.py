import argparse
import base64
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import requests


DEFAULT_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
DEFAULT_MODEL = "mimo-v2.5-asr"


def timestamp_to_seconds(text: str) -> float:
    parts = [int(part) for part in text.strip().split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    raise ValueError(f"Unsupported timestamp: {text}")


def parse_sections(markdown: str) -> tuple[str, list[dict[str, Any]]]:
    matches = list(re.finditer(r'(?m)^<a name="(slide_\d+)"></a>\s*$', markdown))
    if not matches:
        raise ValueError("No slide anchors found.")
    header = markdown[: matches[0].start()]
    sections: list[dict[str, Any]] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(markdown)
        block = markdown[start:end]
        time_match = re.search(r"\*\*Time:\*\*\s*(\d+:\d+|\d+:\d+:\d+)\s*-\s*(\d+:\d+|\d+:\d+:\d+)", block)
        image_match = re.search(r"\[!\[Slide\]\(slides/([^)]+)\)\]\(slides/[^)]+\)", block)
        transcript_match = re.search(
            r"(?s)(### Transcript\s*\n\n)(.*?)(?=\n\n---\s*$|\n\n### |\Z)", block
        )
        if not time_match:
            raise ValueError(f"No time range found for {match.group(1)}")
        t_start = timestamp_to_seconds(time_match.group(1))
        t_end = timestamp_to_seconds(time_match.group(2))
        sections.append(
            {
                "slide_id": match.group(1),
                "block": block,
                "time": f"{time_match.group(1)} - {time_match.group(2)}",
                "start": t_start,
                "end": t_end,
                "image": image_match.group(1) if image_match else "",
                "original_transcript": transcript_match.group(2).strip() if transcript_match else "",
            }
        )
    return header, sections


def extract_audio(video: Path, start: float, end: float, out_wav: Path) -> None:
    duration = max(end - start, 0.1)
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(video),
        "-ar",
        "16000",
        "-ac",
        "1",
        "-acodec",
        "pcm_s16le",
        str(out_wav),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")


def call_mimo_asr(
    base_url: str,
    api_key: str,
    model: str,
    wav_path: Path,
    *,
    retries: int,
    retry_sleep: float,
) -> dict[str, Any]:
    data_url = "data:audio/wav;base64," + base64.b64encode(wav_path.read_bytes()).decode("ascii")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": data_url, "format": "wav"},
                    }
                ],
            }
        ],
        "max_tokens": 4096,
    }
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    response = None
    for attempt in range(retries + 1):
        response = requests.post(url, headers=headers, json=payload, timeout=300)
        if response.status_code not in {429, 500, 502, 503, 504}:
            break
        if attempt >= retries:
            break
        wait = retry_sleep * (attempt + 1)
        print(f"  HTTP {response.status_code}; retrying in {wait:.0f}s", flush=True)
        time.sleep(wait)
    assert response is not None
    if response.status_code >= 400:
        raise RuntimeError(f"MiMo ASR HTTP {response.status_code}: {response.text[:1000]}")
    result = response.json()
    content = result["choices"][0]["message"].get("content") or ""
    return {"transcript": content.strip(), "usage": result.get("usage", {}), "raw": result}


def merge_usage(usages: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for usage in usages:
        for key, value in usage.items():
            if isinstance(value, (int, float)):
                merged[key] = merged.get(key, 0) + value
            elif isinstance(value, dict):
                nested = merged.setdefault(key, {})
                if isinstance(nested, dict):
                    for nested_key, nested_value in value.items():
                        if isinstance(nested_value, (int, float)):
                            nested[nested_key] = nested.get(nested_key, 0) + nested_value
    return merged


def replace_transcript(block: str, transcript: str) -> str:
    if "### Transcript" not in block:
        insert_at = block.rfind("\n---")
        if insert_at == -1:
            return block.rstrip() + f"\n\n### Transcript\n\n{transcript}\n"
        return block[:insert_at].rstrip() + f"\n\n### Transcript\n\n{transcript}\n\n" + block[insert_at:]
    return re.sub(
        r"(?s)(### Transcript\s*\n\n)(.*?)(?=\n\n---\s*$|\n\n### |\Z)",
        lambda m: m.group(1) + transcript.strip(),
        block,
        count=1,
    )


def run_asr(
    *,
    video: Path,
    slides_md: Path,
    out_md: Path,
    out_json: Path,
    base_url: str = DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    padding: float = 2.0,
    max_chunk_seconds: float = 90.0,
    sleep: float = 5.0,
    retries: int = 12,
    retry_sleep: float = 30.0,
    resume: bool = True,
) -> None:
    api_key = os.environ.get("MIMO_API_KEY")
    if not api_key:
        raise RuntimeError("Set MIMO_API_KEY.")

    markdown = slides_md.read_text(encoding="utf-8")
    header, sections = parse_sections(markdown)
    records: list[dict[str, Any]] = []
    completed: dict[str, dict[str, Any]] = {}
    if resume and out_json.exists():
        previous = json.loads(out_json.read_text(encoding="utf-8"))
        if isinstance(previous, list):
            for item in previous:
                if isinstance(item, dict) and item.get("slide_id"):
                    completed[str(item["slide_id"])] = item
            records = [item for item in previous if isinstance(item, dict)]
            print(f"Resuming ASR with {len(completed)} completed slides", flush=True)

    blocks: list[str] = []
    with tempfile.TemporaryDirectory(prefix="mimo-slide-asr-") as temp_dir:
        temp = Path(temp_dir)
        for index, section in enumerate(sections, start=1):
            print(f"[ASR {index}/{len(sections)}] {section['slide_id']} {section['time']}", flush=True)
            if section["slide_id"] in completed:
                transcript = str(completed[section["slide_id"]].get("mimo_asr_transcript", "")).strip()
                blocks.append(replace_transcript(section["block"], transcript))
                continue

            padded_start = max(section["start"] - padding, 0.0)
            padded_end = section["end"] + padding
            chunk_start = padded_start
            chunk_transcripts: list[str] = []
            chunk_usages: list[dict[str, Any]] = []
            chunk_index = 0
            while chunk_start < padded_end - 0.05:
                chunk_end = min(chunk_start + max_chunk_seconds, padded_end)
                chunk_path = temp / f"{section['slide_id']}_{chunk_index:02d}.wav"
                extract_audio(video, chunk_start, chunk_end, chunk_path)
                asr = call_mimo_asr(
                    base_url,
                    api_key,
                    model,
                    chunk_path,
                    retries=retries,
                    retry_sleep=retry_sleep,
                )
                if asr["transcript"]:
                    chunk_transcripts.append(asr["transcript"])
                chunk_usages.append(asr["usage"])
                chunk_start = chunk_end
                chunk_index += 1
                time.sleep(sleep)

            transcript = " ".join(chunk_transcripts)
            blocks.append(replace_transcript(section["block"], transcript))
            records.append(
                {
                    "slide_id": section["slide_id"],
                    "time": section["time"],
                    "start": section["start"],
                    "end": section["end"],
                    "image": section["image"],
                    "previous_transcript": section["original_transcript"],
                    "mimo_asr_transcript": transcript,
                    "usage": merge_usage(chunk_usages),
                }
            )
            out_md.write_text(header + "".join(blocks), encoding="utf-8")
            out_json.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    out_md.write_text(header + "".join(blocks), encoding="utf-8")
    out_json.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--slides-md", required=True, type=Path)
    parser.add_argument("--out-md", required=True, type=Path)
    parser.add_argument("--out-json", required=True, type=Path)
    parser.add_argument("--padding", default=2.0, type=float)
    parser.add_argument("--max-chunk-seconds", default=90.0, type=float)
    parser.add_argument("--sleep", default=5.0, type=float)
    parser.add_argument("--retries", default=12, type=int)
    parser.add_argument("--retry-sleep", default=30.0, type=float)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    run_asr(**vars(args))


if __name__ == "__main__":
    main()

