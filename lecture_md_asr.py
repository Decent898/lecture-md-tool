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
TIMESTAMP_RE = r"(?:\d{1,2}:)?\d+:\d{2}"
TRANSCRIPT_RE = re.compile(r"(?ms)^(### Transcript\s*\n+)(.*?)(?=^---\s*$|^### |\Z)")


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
        time_match = re.search(rf"\*\*Time:\*\*\s*({TIMESTAMP_RE})\s*-\s*({TIMESTAMP_RE})", block)
        image_match = re.search(r"\[!\[Slide\]\(slides/([^)]+)\)\]\(slides/[^)]+\)", block)
        transcript_match = TRANSCRIPT_RE.search(block)
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
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=300)
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt >= retries:
                raise
            wait = retry_sleep * (attempt + 1)
            print(f"  request failed ({exc}); retrying in {wait:.0f}s", flush=True)
            time.sleep(wait)
            continue
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
    return {"transcript": content.strip(), "metadata": result.get("usage", {}), "raw": result}


def load_local_whisper(model_name: str, device: str, compute_type: str) -> Any:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Local ASR requires faster-whisper. Install it with: pip install faster-whisper") from exc
    return WhisperModel(model_name, device=device, compute_type=compute_type)


def call_local_asr(
    whisper_model: Any,
    wav_path: Path,
    *,
    language: str,
    beam_size: int,
) -> dict[str, Any]:
    language_arg = None if language.lower() in {"", "auto"} else language
    segments, info = whisper_model.transcribe(str(wav_path), language=language_arg, beam_size=beam_size)
    transcript = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
    return {
        "transcript": transcript.strip(),
        "metadata": {
            "language": getattr(info, "language", None),
            "language_probability": getattr(info, "language_probability", None),
            "duration": getattr(info, "duration", None),
        },
    }


def merge_numeric_metadata(items: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for item in items:
        for key, value in item.items():
            if isinstance(value, (int, float)):
                merged[key] = merged.get(key, 0) + value
            elif isinstance(value, dict):
                nested = merged.setdefault(key, {})
                if isinstance(nested, dict):
                    for nested_key, nested_value in value.items():
                        if isinstance(nested_value, (int, float)):
                            nested[nested_key] = nested.get(nested_key, 0) + nested_value
    return merged


def record_transcript(record: dict[str, Any]) -> str:
    for key in ("asr_transcript", "mimo_asr_transcript", "local_asr_transcript"):
        transcript = str(record.get(key, "")).strip()
        if transcript:
            return transcript
    return ""


def replace_transcript(block: str, transcript: str) -> str:
    if "### Transcript" not in block:
        insert_at = block.rfind("\n---")
        if insert_at == -1:
            return block.rstrip() + f"\n\n### Transcript\n\n{transcript}\n"
        return block[:insert_at].rstrip() + f"\n\n### Transcript\n\n{transcript}\n\n" + block[insert_at:]
    return TRANSCRIPT_RE.sub(lambda m: m.group(1) + transcript.strip() + "\n\n", block, count=1)


def normalize_backend(backend: str) -> str:
    normalized = backend.lower()
    if normalized in {"api", "mimo"}:
        return "api"
    if normalized in {"local", "whisper"}:
        return "local"
    raise ValueError(f"Unsupported ASR backend: {backend}")


def run_asr(
    *,
    video: Path,
    slides_md: Path,
    out_md: Path,
    out_json: Path,
    backend: str = "api",
    base_url: str = DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    language: str = "zh",
    local_model: str = "small",
    local_device: str = "cpu",
    local_compute_type: str = "int8",
    local_beam_size: int = 5,
    padding: float = 2.0,
    max_chunk_seconds: float = 90.0,
    sleep: float = 5.0,
    retries: int = 12,
    retry_sleep: float = 30.0,
    resume: bool = True,
) -> None:
    backend = normalize_backend(backend)
    api_key = os.environ.get("MIMO_API_KEY") if backend == "api" else None
    if backend == "api" and not api_key:
        raise RuntimeError("Set MIMO_API_KEY or use --asr local.")

    whisper_model = None
    if backend == "local":
        print(f"Loading local ASR model {local_model} ({local_device}, {local_compute_type})", flush=True)
        whisper_model = load_local_whisper(local_model, local_device, local_compute_type)

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
    with tempfile.TemporaryDirectory(prefix="lecture-md-asr-") as temp_dir:
        temp = Path(temp_dir)
        for index, section in enumerate(sections, start=1):
            print(f"[ASR {index}/{len(sections)}] {section['slide_id']} {section['time']}", flush=True)
            if section["slide_id"] in completed:
                transcript = record_transcript(completed[section["slide_id"]])
                blocks.append(replace_transcript(section["block"], transcript))
                continue

            padded_start = max(section["start"] - padding, 0.0)
            padded_end = section["end"] + padding
            chunk_start = padded_start
            chunk_transcripts: list[str] = []
            chunk_metadata: list[dict[str, Any]] = []
            chunk_index = 0
            while chunk_start < padded_end - 0.05:
                chunk_end = min(chunk_start + max_chunk_seconds, padded_end)
                chunk_path = temp / f"{section['slide_id']}_{chunk_index:02d}.wav"
                extract_audio(video, chunk_start, chunk_end, chunk_path)
                if backend == "api":
                    assert api_key is not None
                    asr = call_mimo_asr(
                        base_url,
                        api_key,
                        model,
                        chunk_path,
                        retries=retries,
                        retry_sleep=retry_sleep,
                    )
                    time.sleep(sleep)
                else:
                    assert whisper_model is not None
                    asr = call_local_asr(
                        whisper_model,
                        chunk_path,
                        language=language,
                        beam_size=local_beam_size,
                    )
                if asr["transcript"]:
                    chunk_transcripts.append(asr["transcript"])
                chunk_metadata.append(asr["metadata"])
                chunk_start = chunk_end
                chunk_index += 1

            transcript = " ".join(chunk_transcripts).strip()
            blocks.append(replace_transcript(section["block"], transcript))
            record: dict[str, Any] = {
                "slide_id": section["slide_id"],
                "time": section["time"],
                "start": section["start"],
                "end": section["end"],
                "image": section["image"],
                "asr_backend": backend,
                "previous_transcript": section["original_transcript"],
                "asr_transcript": transcript,
                "chunk_metadata": chunk_metadata,
                "metadata": merge_numeric_metadata(chunk_metadata),
            }
            if backend == "api":
                record["mimo_asr_model"] = model
                record["mimo_asr_transcript"] = transcript
            else:
                record["local_asr_model"] = local_model
                record["local_asr_language"] = language
                record["local_asr_transcript"] = transcript
            records.append(record)
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
    parser.add_argument("--asr", choices=["api", "local"], default="api")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--asr-language", default="zh")
    parser.add_argument("--local-asr-model", default="small")
    parser.add_argument("--local-asr-device", default="cpu")
    parser.add_argument("--local-asr-compute-type", default="int8")
    parser.add_argument("--local-asr-beam-size", default=5, type=int)
    parser.add_argument("--padding", default=2.0, type=float)
    parser.add_argument("--max-chunk-seconds", default=90.0, type=float)
    parser.add_argument("--sleep", default=5.0, type=float)
    parser.add_argument("--retries", default=12, type=int)
    parser.add_argument("--retry-sleep", default=30.0, type=float)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    run_asr(
        video=args.video,
        slides_md=args.slides_md,
        out_md=args.out_md,
        out_json=args.out_json,
        backend=args.asr,
        base_url=args.base_url,
        model=args.model,
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
        resume=args.resume,
    )


if __name__ == "__main__":
    main()
