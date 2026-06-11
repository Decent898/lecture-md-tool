"""ASR correction: OCR each slide, then fix transcripts with a chat model."""

import argparse
import json
import time
from pathlib import Path
from typing import Any

from lecture_md import config
from lecture_md.client import chat_completions, message_content
from lecture_md.slides_md import extract_json_object, parse_sections, replace_transcript


def ocr_image(ocr: Any, image_path: Path) -> str:
    if not image_path.exists():
        return ""
    result, _ = ocr(str(image_path))
    if not result:
        return ""
    lines: list[str] = []
    for item in result:
        if len(item) >= 2 and item[1]:
            text = str(item[1]).strip()
            if text:
                lines.append(text)
    return "\n".join(lines)


def load_ocr_engine() -> Any:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        raise RuntimeError(
            "OCR-assisted correction requires rapidocr-onnxruntime. "
            "Install it with: pip install rapidocr-onnxruntime"
        ) from exc
    return RapidOCR()


def call_correction(
    *,
    base_url: str,
    api_key: str,
    model: str,
    slide_id: str,
    slide_time: str,
    ocr_text: str,
    transcript: str,
    terms: str,
    retries: int,
    retry_sleep: float,
    timeout: float,
) -> dict[str, Any]:
    system = (
        "你是课堂讲义转写校对助手。你会根据 PPT 页面 OCR 文本和原始 ASR 转写，"
        "逐页修正老师讲课内容中的识别错误。只做校正，不总结、不扩写、不编造。"
        "保留老师讲课的原有信息顺序，重点修正中英混合技术术语、同音错字、标点和断句。"
        "如果 OCR 和 ASR 冲突，以 ASR 表达的语义为主，以 OCR 作为术语和页面上下文参考。"
        "只输出严格 JSON。"
    )
    terms_text = terms.strip()
    terms_section = f"固定术语参考：\n{terms_text}\n\n" if terms_text else ""
    user = f"""请校正这一页的课堂转写。

{terms_section}页码：{slide_id}
时间：{slide_time}

PPT OCR 文本：
{ocr_text or "(OCR 未提取到文字)"}

原始 ASR 转写：
{transcript or "(本页没有原始转写)"}

输出严格 JSON，格式如下：
{{
  "corrected_transcript": "校正后的逐字讲课内容",
  "notes": ["只列出关键修正点，最多 5 条"]
}}
"""
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
        "max_tokens": 8192,
    }
    data = chat_completions(
        base_url=base_url,
        api_key=api_key,
        payload=payload,
        retries=retries,
        retry_sleep=retry_sleep,
        timeout=timeout,
    )
    content = message_content(data)
    if not content:
        snippet = json.dumps(data, ensure_ascii=False)[:500]
        raise ValueError(f"Empty model content for {slide_id}: {snippet}")
    try:
        parsed = extract_json_object(content)
        corrected = str(parsed.get("corrected_transcript", "")).strip()
        if not corrected and transcript:
            corrected = transcript
        notes = parsed.get("notes", [])
        if not isinstance(notes, list):
            notes = [str(notes)]
    except Exception as exc:
        corrected = content.strip()
        notes = [f"模型未返回严格 JSON，已按纯文本校正版保存：{exc}"]
    return {
        "corrected_transcript": corrected,
        "notes": [str(note).strip() for note in notes if str(note).strip()],
        "raw_response": content,
    }


def run_correction(
    *,
    slides_md: Path,
    out_md: Path,
    out_json: Path,
    base_url: str | None = None,
    model: str | None = None,
    sleep: float = 5.0,
    retries: int = 12,
    retry_sleep: float = 30.0,
    timeout: float = 600.0,
    terms: str | None = None,
    resume: bool = True,
) -> None:
    api_key = config.require_api_key()
    base_url = base_url or config.default_base_url()
    model = model or config.default_chat_model()
    terms = terms if terms is not None else config.default_terms()

    markdown = slides_md.read_text(encoding="utf-8")
    header, sections = parse_sections(markdown)
    output_dir = slides_md.parent
    slides_dir = output_dir / "slides"
    ocr = load_ocr_engine()

    corrections: list[dict[str, Any]] = []
    completed: dict[str, dict[str, Any]] = {}
    if resume and out_json.exists():
        previous = json.loads(out_json.read_text(encoding="utf-8"))
        if isinstance(previous, list):
            for item in previous:
                if isinstance(item, dict) and item.get("slide_id"):
                    completed[str(item["slide_id"])] = item
            corrections = [item for item in previous if isinstance(item, dict)]
            print(f"Resuming correction with {len(completed)} completed slides", flush=True)

    corrected_blocks: list[str] = []
    for index, section in enumerate(sections, start=1):
        slide_id = section["slide_id"]
        print(f"[Optimize {index}/{len(sections)}] {slide_id}", flush=True)
        transcript = section["transcript"]
        if slide_id in completed:
            corrected = str(completed[slide_id].get("corrected_transcript", "")).strip()
            corrected_blocks.append(replace_transcript(section["block"], corrected))
            continue

        image_path = slides_dir / section["image"] if section["image"] else Path()
        ocr_text = ocr_image(ocr, image_path) if section["image"] else ""
        if transcript:
            result = call_correction(
                base_url=base_url,
                api_key=api_key,
                model=model,
                slide_id=slide_id,
                slide_time=section["time"],
                ocr_text=ocr_text,
                transcript=transcript,
                terms=terms,
                retries=retries,
                retry_sleep=retry_sleep,
                timeout=timeout,
            )
            corrected = result["corrected_transcript"] or transcript
            notes = result["notes"]
        else:
            corrected = ""
            notes = ["原始 ASR 为空，未校正。"]

        corrected_blocks.append(replace_transcript(section["block"], corrected) if corrected else section["block"])
        corrections.append(
            {
                "slide_id": slide_id,
                "time": section["time"],
                "image": section["image"],
                "ocr_text": ocr_text,
                "original_transcript": transcript,
                "corrected_transcript": corrected,
                "notes": notes,
            }
        )
        out_md.write_text(header + "".join(corrected_blocks), encoding="utf-8")
        out_json.write_text(json.dumps(corrections, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(sleep)

    out_md.write_text(header + "".join(corrected_blocks), encoding="utf-8")
    out_json.write_text(json.dumps(corrections, ensure_ascii=False, indent=2), encoding="utf-8")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--slides-md", required=True, type=Path)
    parser.add_argument("--out-md", required=True, type=Path)
    parser.add_argument("--out-json", required=True, type=Path)
    parser.add_argument("--base-url", default=None, help="OpenAI-compatible API base URL.")
    parser.add_argument("--model", default=None, help="Chat model name.")
    parser.add_argument("--sleep", default=5.0, type=float)
    parser.add_argument("--retries", default=12, type=int)
    parser.add_argument("--retry-sleep", default=30.0, type=float)
    parser.add_argument("--timeout", default=600.0, type=float)
    parser.add_argument("--terms", default=None, help="Comma-separated domain terms.")
    parser.add_argument("--resume", action="store_true")


def run_cli(args: argparse.Namespace) -> None:
    run_correction(
        slides_md=args.slides_md,
        out_md=args.out_md,
        out_json=args.out_json,
        base_url=args.base_url,
        model=args.model,
        sleep=args.sleep,
        retries=args.retries,
        retry_sleep=args.retry_sleep,
        timeout=args.timeout,
        terms=args.terms,
        resume=args.resume,
    )
