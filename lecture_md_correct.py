import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests


DEFAULT_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
DEFAULT_MODEL = "mimo-v2.5-pro"


def parse_sections(markdown: str) -> tuple[str, list[dict[str, Any]]]:
    matches = list(re.finditer(r'(?m)^<a name="(slide_\d+)"></a>\s*$', markdown))
    if not matches:
        raise ValueError("No slide anchors found in markdown.")
    header = markdown[: matches[0].start()]
    sections: list[dict[str, Any]] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(markdown)
        block = markdown[start:end]
        image_match = re.search(r"\[!\[Slide\]\(slides/([^)]+)\)\]\(slides/[^)]+\)", block)
        time_match = re.search(r"\*\*Time:\*\*\s*([^\n]+)", block)
        transcript_match = re.search(
            r"(?s)(### Transcript\s*\n\n)(.*?)(?=\n\n---\s*$|\n\n### |\Z)", block
        )
        sections.append(
            {
                "slide_id": match.group(1),
                "block": block,
                "image": image_match.group(1) if image_match else "",
                "time": time_match.group(1).strip() if time_match else "",
                "transcript": transcript_match.group(2).strip() if transcript_match else "",
            }
        )
    return header, sections


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


def extract_json_object(text: str) -> dict[str, Any]:
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


def call_mimo(
    *,
    base_url: str,
    api_key: str,
    model: str,
    slide_id: str,
    slide_time: str,
    ocr_text: str,
    transcript: str,
    retries: int,
    retry_sleep: float,
    timeout: float,
) -> dict[str, Any]:
    system = (
        "你是中文课堂讲义转写校对助手。你会根据 PPT 页面 OCR 文本和原始 ASR 转写，"
        "逐页修正老师讲课内容中的识别错误。只做校正，不总结、不扩写、不编造。"
        "保留老师的讲课口吻和原有信息顺序。重点修正中英混合技术术语、同音错字、标点和断句。"
        "如果 OCR 和 ASR 冲突，以 ASR 表达的语义为主，以 OCR 作为术语和页面上下文参考。只输出 JSON。"
    )
    user = f"""请校正这一页的课堂转写。
固定术语参考：
Vivado, Verilog, FPGA, Xilinx, testbench, simulation, Behavioral Simulation,
Add Sources, Run Simulation, Flow Navigator, bitstream, RISC-V, RISCV, RV32I,
CPU, ALU, PC, IF, ID, EX, MEM, WB, 七段数码管, 16进制, 行为仿真, 约束文件,
源代码, 工程, 仿真波形。
页码：{slide_id}
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
        snippet = json.dumps(data, ensure_ascii=False)[:500]
        raise ValueError(f"Empty MiMo content for {slide_id}: {snippet}")
    try:
        parsed = extract_json_object(content)
        corrected = str(parsed.get("corrected_transcript", "")).strip()
        if not corrected and transcript:
            raise ValueError("missing corrected_transcript")
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


def replace_transcript(block: str, corrected: str) -> str:
    if "### Transcript" not in block:
        insert_at = block.rfind("\n---")
        if insert_at == -1:
            return block.rstrip() + f"\n\n### Transcript\n\n{corrected}\n"
        return block[:insert_at].rstrip() + f"\n\n### Transcript\n\n{corrected}\n\n" + block[insert_at:]
    return re.sub(
        r"(?s)(### Transcript\s*\n\n)(.*?)(?=\n\n---\s*$|\n\n### |\Z)",
        lambda m: m.group(1) + corrected.strip(),
        block,
        count=1,
    )


def run_correction(
    *,
    slides_md: Path,
    out_md: Path,
    out_json: Path,
    base_url: str = DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    sleep: float = 5.0,
    retries: int = 12,
    retry_sleep: float = 30.0,
    timeout: float = 600.0,
    resume: bool = True,
) -> None:
    api_key = os.environ.get("MIMO_API_KEY")
    if not api_key:
        raise RuntimeError("Set MIMO_API_KEY.")

    from rapidocr_onnxruntime import RapidOCR

    markdown = slides_md.read_text(encoding="utf-8")
    header, sections = parse_sections(markdown)
    output_dir = slides_md.parent
    slides_dir = output_dir / "slides"
    ocr = RapidOCR()

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
            if corrected:
                corrected_blocks.append(replace_transcript(section["block"], corrected))
                continue

        image_path = slides_dir / section["image"] if section["image"] else Path()
        ocr_text = ocr_image(ocr, image_path) if section["image"] else ""
        if transcript:
            result = call_mimo(
                base_url=base_url,
                api_key=api_key,
                model=model,
                slide_id=slide_id,
                slide_time=section["time"],
                ocr_text=ocr_text,
                transcript=transcript,
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slides-md", required=True, type=Path)
    parser.add_argument("--out-md", required=True, type=Path)
    parser.add_argument("--out-json", required=True, type=Path)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--sleep", default=5.0, type=float)
    parser.add_argument("--retries", default=12, type=int)
    parser.add_argument("--retry-sleep", default=30.0, type=float)
    parser.add_argument("--timeout", default=600.0, type=float)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    run_correction(**vars(args))


if __name__ == "__main__":
    main()
