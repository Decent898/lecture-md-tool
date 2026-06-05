import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests

from lecture_md_correct import DEFAULT_BASE_URL, DEFAULT_MODEL, DEFAULT_TERMS
from lecture_md_correct import extract_json_object, parse_sections
from lecture_md_correct import TRANSCRIPT_RE


def load_json_records(path: Path | None) -> dict[str, dict[str, Any]]:
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


def asr_text(record: dict[str, Any]) -> str:
    for key in ("asr_transcript", "local_asr_transcript", "mimo_asr_transcript"):
        value = str(record.get(key, "")).strip()
        if value:
            return value
    return ""


def call_mimo_note(
    *,
    base_url: str,
    api_key: str,
    model: str,
    slide_id: str,
    slide_time: str,
    ocr_text: str,
    corrected_transcript: str,
    original_asr: str,
    terms: str,
    retries: int,
    retry_sleep: float,
    timeout: float,
) -> dict[str, Any]:
    system = (
        "你是中文课程讲义整理助手。你的任务是把逐页课堂转写整理成适合复习的讲义稿。"
        "去掉口头禅、重复、自我修正和课堂杂音，但保留老师讲解中的推理顺序和关键限定。"
        "不要编造 PPT 和转写之外的信息；如果信息不足，要明确保持简略。"
        "数学符号、文法产生式、项目、集合、表项和算法符号必须用 Markdown/LaTeX 格式表达。"
        "只输出 JSON。"
    )
    user = f"""请把这一页整理成精炼讲义稿。

要求：
- 输出的是“讲义稿”，不要写成逐字稿，也不要写“老师说”。
- 删除口语化重复，例如“好”“然后呢”“大家看”“这个这个”等。
- 公式、文法、项目和表项用 Markdown/LaTeX：例如 `$S \\to L = R$`、`$FIRST(\\alpha)$`、`ACTION[i, a]`。
- 字母、状态号、非终结符、终结符要尽量按 PPT OCR 和上下文校正。
- 每页控制在 1 到 4 个短段落或项目符号；复杂页可以稍长。
- 如果本页没有有效讲解内容，`lecture_note_md` 置为空字符串。
- 保留原义，不额外扩展知识点。

课程术语：
{terms.strip() or DEFAULT_TERMS}

页码：{slide_id}
时间：{slide_time}

PPT OCR 文本：
{ocr_text or "(OCR 未提取到文字)"}

校正转写：
{corrected_transcript or "(无校正转写)"}

本地 ASR 原文：
{original_asr or "(无 ASR 原文)"}

严格输出 JSON：
{{
  "lecture_note_md": "去口语化、公式 Markdown 化后的本页讲义稿",
  "notes": ["可选：说明关键整理点，最多 3 条"]
}}
"""
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
        "max_tokens": 8192,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = f"{base_url.rstrip('/')}/chat/completions"
    response = None
    for attempt in range(retries + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
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
    response.raise_for_status()
    data = response.json()
    content = (data["choices"][0]["message"].get("content") or "").strip()
    if not content:
        raise ValueError(f"Empty MiMo content for {slide_id}")
    try:
        parsed = extract_json_object(content)
        lecture_note_md = str(parsed.get("lecture_note_md", "")).strip()
        notes = parsed.get("notes", [])
        if not isinstance(notes, list):
            notes = [str(notes)]
    except Exception as exc:
        lecture_note_md = content
        notes = [f"模型未返回严格 JSON，已按纯文本讲义稿保存：{exc}"]
    return {
        "lecture_note_md": lecture_note_md.strip(),
        "notes": [str(note).strip() for note in notes if str(note).strip()],
        "raw_response": content,
    }


def strip_section_trailer(block: str) -> str:
    return re.sub(r"(?ms)\n---\s*$", "", block).rstrip()


def remove_transcript_section(block: str) -> str:
    block = TRANSCRIPT_RE.sub("", block, count=1)
    return re.sub(r"(?ms)^### Transcript\s*\n*\s*$", "", block).rstrip()


def normalize_embedded_headings(markdown: str) -> str:
    def replace_heading(match: re.Match[str]) -> str:
        return f"**{match.group(2).strip()}**"

    return re.sub(r"(?m)^(#{2,6})\s+(.+?)\s*$", replace_heading, markdown.strip())


def append_note_sections(block: str, lecture_note: str, corrected: str, raw_asr: str) -> str:
    base = remove_transcript_section(strip_section_trailer(block))
    lecture_note = normalize_embedded_headings(lecture_note)
    parts = [base]
    parts.append("\n\n### 讲义稿\n")
    parts.append("\n" + (lecture_note.strip() or "_本页无有效讲解内容。_") + "\n")
    parts.append("\n### 校正转写\n")
    parts.append("\n" + (corrected.strip() or "_本页无校正转写。_") + "\n")
    parts.append("\n### ASR 原文\n")
    parts.append("\n" + (raw_asr.strip() or "_本页无 ASR 原文。_") + "\n")
    parts.append("\n---\n\n")
    return "".join(parts)


def run_notes(
    *,
    slides_md: Path,
    out_md: Path,
    out_json: Path,
    asr_json: Path | None = None,
    optimization_json: Path | None = None,
    base_url: str = DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    sleep: float = 5.0,
    retries: int = 12,
    retry_sleep: float = 30.0,
    timeout: float = 600.0,
    terms: str = DEFAULT_TERMS,
    resume: bool = True,
) -> None:
    api_key = os.environ.get("MIMO_API_KEY")
    if not api_key:
        raise RuntimeError("Set MIMO_API_KEY.")

    terms = os.environ.get("LECTURE_MD_TERMS", terms)
    markdown = slides_md.read_text(encoding="utf-8")
    header, sections = parse_sections(markdown)
    asr_records = load_json_records(asr_json)
    optimization_records = load_json_records(optimization_json)

    records: list[dict[str, Any]] = []
    completed: dict[str, dict[str, Any]] = {}
    if resume and out_json.exists():
        previous = json.loads(out_json.read_text(encoding="utf-8"))
        if isinstance(previous, list):
            for item in previous:
                if isinstance(item, dict) and item.get("slide_id"):
                    completed[str(item["slide_id"])] = item
            records = [item for item in previous if isinstance(item, dict)]
            print(f"Resuming lecture-note generation with {len(completed)} completed slides", flush=True)

    blocks: list[str] = []
    for index, section in enumerate(sections, start=1):
        slide_id = section["slide_id"]
        print(f"[Notes {index}/{len(sections)}] {slide_id}", flush=True)
        optimization = optimization_records.get(slide_id, {})
        asr = asr_records.get(slide_id, {})
        corrected = str(optimization.get("corrected_transcript") or section["transcript"]).strip()
        raw_asr = asr_text(asr) or str(optimization.get("original_transcript", "")).strip()
        ocr_text = str(optimization.get("ocr_text", "")).strip()

        if slide_id in completed:
            lecture_note = str(completed[slide_id].get("lecture_note_md", "")).strip()
            blocks.append(append_note_sections(section["block"], lecture_note, corrected, raw_asr))
            continue

        if corrected or raw_asr or ocr_text:
            result = call_mimo_note(
                base_url=base_url,
                api_key=api_key,
                model=model,
                slide_id=slide_id,
                slide_time=section["time"],
                ocr_text=ocr_text,
                corrected_transcript=corrected,
                original_asr=raw_asr,
                terms=terms,
                retries=retries,
                retry_sleep=retry_sleep,
                timeout=timeout,
            )
            lecture_note = result["lecture_note_md"]
            notes = result["notes"]
            raw_response = result["raw_response"]
        else:
            lecture_note = ""
            notes = ["本页没有有效 OCR、校正转写或 ASR 原文。"]
            raw_response = ""

        blocks.append(append_note_sections(section["block"], lecture_note, corrected, raw_asr))
        records.append(
            {
                "slide_id": slide_id,
                "time": section["time"],
                "image": section["image"],
                "ocr_text": ocr_text,
                "corrected_transcript": corrected,
                "original_asr": raw_asr,
                "lecture_note_md": lecture_note,
                "notes": notes,
                "raw_response": raw_response,
            }
        )
        out_md.write_text(header + "".join(blocks), encoding="utf-8")
        out_json.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(sleep)

    out_md.write_text(header + "".join(blocks), encoding="utf-8")
    out_json.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slides-md", required=True, type=Path)
    parser.add_argument("--out-md", required=True, type=Path)
    parser.add_argument("--out-json", required=True, type=Path)
    parser.add_argument("--asr-json", type=Path)
    parser.add_argument("--optimization-json", type=Path)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--sleep", default=5.0, type=float)
    parser.add_argument("--retries", default=12, type=int)
    parser.add_argument("--retry-sleep", default=30.0, type=float)
    parser.add_argument("--timeout", default=600.0, type=float)
    parser.add_argument("--terms", default=DEFAULT_TERMS)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    run_notes(**vars(args))


if __name__ == "__main__":
    main()
