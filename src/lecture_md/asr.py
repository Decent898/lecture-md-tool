"""Per-slide ASR: cut audio with ffmpeg, transcribe via API or local Whisper."""

import argparse
import base64
import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from requests.exceptions import ConnectionError as RequestsConnectionError

from lecture_md import config
from lecture_md.client import chat_completions, message_content
from lecture_md.runtime import resolve_executable
from lecture_md.slides_md import parse_sections, replace_transcript


def extract_audio(video: Path, start: float, end: float, out_wav: Path) -> None:
    duration = max(end - start, 0.1)
    cmd = [
        resolve_executable("ffmpeg", "LECTURE_MD_FFMPEG"),
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


def call_api_asr(
    base_url: str,
    api_key: str,
    model: str,
    wav_path: Path,
    *,
    retries: int,
    retry_sleep: float,
) -> dict[str, Any]:
    """Transcribe one audio chunk through a chat model that accepts input_audio."""
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
    result = chat_completions(
        base_url=base_url,
        api_key=api_key,
        payload=payload,
        retries=retries,
        retry_sleep=retry_sleep,
        timeout=300,
    )
    return {"transcript": message_content(result), "metadata": result.get("usage", {}), "raw": result}


def load_local_whisper(model_name: str, device: str, compute_type: str) -> Any:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "Local ASR requires faster-whisper. Install it with: pip install 'lecture-md-tool[local]'"
        ) from exc
    try:
        return WhisperModel(model_name, device=device, compute_type=compute_type)
    except Exception as exc:
        text = str(exc)
        if (
            "Connection refused" in text
            or "ConnectError" in text
            or "locate the files on the Hub" in text
            or isinstance(exc, RequestsConnectionError)
        ):
            raise RuntimeError(
                "本地 Whisper 模型加载失败: 需要从 Hugging Face 下载模型,但当前网络无法连接。"
                "可改用「全 API」方案,或提前下载 faster-whisper 模型后在设置页"
                "「本地 Whisper 模型」里填写本地模型目录。"
            ) from exc
        raise


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
    # Legacy key names are still read so old runs can be resumed.
    for key in ("asr_transcript", "api_asr_transcript", "mimo_asr_transcript", "local_asr_transcript"):
        transcript = str(record.get(key, "")).strip()
        if transcript:
            return transcript
    return ""


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
    base_url: str | None = None,
    model: str | None = None,
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
    base_url = base_url or config.default_base_url()
    model = model or config.default_asr_model()
    api_key = config.require_api_key() if backend == "api" else None

    whisper_model = None
    if backend == "local":
        print(f"Loading local ASR model {local_model} ({local_device}, {local_compute_type})", flush=True)
        whisper_model = load_local_whisper(local_model, local_device, local_compute_type)

    markdown = slides_md.read_text(encoding="utf-8")
    header, sections = parse_sections(markdown, require_time_range=True)
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
                    asr = call_api_asr(
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
                "previous_transcript": section["transcript"],
                "asr_transcript": transcript,
                "chunk_metadata": chunk_metadata,
                "metadata": merge_numeric_metadata(chunk_metadata),
            }
            if backend == "api":
                record["api_asr_model"] = model
                record["api_asr_transcript"] = transcript
            else:
                record["local_asr_model"] = local_model
                record["local_asr_language"] = language
                record["local_asr_transcript"] = transcript
            records.append(record)
            out_md.write_text(header + "".join(blocks), encoding="utf-8")
            out_json.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    out_md.write_text(header + "".join(blocks), encoding="utf-8")
    out_json.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--slides-md", required=True, type=Path)
    parser.add_argument("--out-md", required=True, type=Path)
    parser.add_argument("--out-json", required=True, type=Path)
    parser.add_argument("--asr", choices=["api", "local"], default="api")
    parser.add_argument("--base-url", default=None, help="OpenAI-compatible API base URL.")
    parser.add_argument("--model", default=None, help="Audio-capable chat model name.")
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


def run_cli(args: argparse.Namespace) -> None:
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
