"""Regenerate assets/demo.gif (the animated README banner).

The GIF is drawn programmatically with Pillow, so the demo stays
reproducible and free of screen-recording artifacts.

Usage:
    python tools/make_demo_gif.py [--out assets/demo.gif]

Requires Pillow and a CJK font (defaults target Noto Sans CJK on Linux;
on Windows, pass --cjk-font / --cjk-bold pointing to e.g. msyh.ttc).
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 960, 540
N_FRAMES = 60
FRAME_MS = 120

INK = "#0f172a"
MUTED = "#64748b"
PAGE_BG = "#eef2f7"
CARD_BORDER = "#e2e8f0"
STAGE_COLORS = ["#2563eb", "#0891b2", "#f59e0b", "#f97316", "#16a34a"]
STAGE_TINTS = ["#eff6ff", "#ecfeff", "#fffbeb", "#fff7ed", "#f0fdf4"]

STAGES = [
    ("课程录屏", "PPT + 声音"),
    ("切页去重", "防抖过滤"),
    ("按页转写", "Whisper · API"),
    ("纠错优化", "OCR + LLM"),
    ("讲义输出", "MD / PDF"),
]

CODE_LINES = [
    ("# Slide 12: Cache 写策略", "#86efac"),
    ("- 写直达:同时写入 Cache 与主存", "#e2e8f0"),
    ("- 写回:置脏位,替换时写回主存", "#e2e8f0"),
    ("- 保留校正转写与 ASR 原文", "#94a3b8"),
]
LINE_APPEAR_FRAMES = [16, 26, 36, 46]


def load_fonts(cjk: str, cjk_bold: str, mono: str):
    return {
        "title": ImageFont.truetype(cjk_bold, 34),
        "sub": ImageFont.truetype(cjk, 17),
        "cmd": ImageFont.truetype(mono, 14),
        "card_t": ImageFont.truetype(cjk_bold, 19),
        "card_s": ImageFont.truetype(cjk, 12),
        "slide_t": ImageFont.truetype(cjk_bold, 22),
        "code": ImageFont.truetype(cjk, 15),
        "code_file": ImageFont.truetype(mono, 14),
        "foot": ImageFont.truetype(cjk, 13),
        "badge": ImageFont.truetype(cjk_bold, 13),
    }


def fit_text(draw, text, font, max_width):
    """Trim text with an ellipsis if it would overflow max_width."""
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text + "…"


def draw_frame(frame: int, fonts) -> Image.Image:
    img = Image.new("RGB", (W, H), PAGE_BG)
    d = ImageDraw.Draw(img)
    stage = min(frame // 12, 4)

    # container
    d.rounded_rectangle([28, 20, 932, 520], radius=24, fill="#ffffff", outline=CARD_BORDER, width=2)

    # header
    d.text((68, 40), "lecture-md-tool", font=fonts["title"], fill=INK)
    d.text((68, 86), "课程录屏 → 按页对齐的 Markdown 讲义", font=fonts["sub"], fill=MUTED)
    d.text((68, 114), "$ lecture-md process lecture.mp4 --asr local --optimize api --notes api",
           font=fonts["cmd"], fill="#475569")

    # stage cards
    card_w, gap, card_h, top = 152, 14, 116, 150
    start_x = (W - (5 * card_w + 4 * gap)) // 2
    for i, (t, s) in enumerate(STAGES):
        x = start_x + i * (card_w + gap)
        active = i == stage
        done = i < stage
        border = STAGE_COLORS[i] if (active or done) else CARD_BORDER
        fill = STAGE_TINTS[i] if active else "#ffffff"
        d.rounded_rectangle([x, top, x + card_w, top + card_h], radius=14,
                            fill=fill, outline=border, width=3 if active else 2)
        cx, cy, r = x + 28, top + 28, 13
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=STAGE_COLORS[i])
        if done:
            d.line([cx - 6, cy, cx - 1, cy + 5], fill="#ffffff", width=3)
            d.line([cx - 1, cy + 5, cx + 7, cy - 5], fill="#ffffff", width=3)
        else:
            d.text((cx, cy), str(i + 1), font=fonts["badge"], fill="#ffffff", anchor="mm")
        max_w = card_w - 32
        d.text((x + 16, top + 50), fit_text(d, t, fonts["card_t"], max_w), font=fonts["card_t"], fill=INK)
        d.text((x + 16, top + 82), fit_text(d, s, fonts["card_s"], max_w), font=fonts["card_s"], fill=MUTED)

    # slide preview (bottom left)
    d.rounded_rectangle([72, 296, 436, 462], radius=14, fill="#ffffff", outline=CARD_BORDER, width=2)
    d.text((96, 316), "Slide 12", font=fonts["slide_t"], fill=INK)
    d.rounded_rectangle([96, 360, 256, 374], radius=7, fill="#2563eb")
    d.rounded_rectangle([96, 388, 308, 398], radius=5, fill="#cbd5e1")
    d.rounded_rectangle([96, 412, 232, 422], radius=5, fill="#e2e8f0")
    d.polygon([(352, 372), (396, 398), (352, 424)], fill="#0f766e")

    # markdown panel (bottom right)
    d.rounded_rectangle([456, 296, 888, 462], radius=14, fill="#0f172a")
    d.text((480, 312), "slides_lecture_notes.md", font=fonts["code_file"], fill="#7dd3fc")
    y = 342
    last_visible = -1
    for i, (line, color) in enumerate(CODE_LINES):
        if frame >= LINE_APPEAR_FRAMES[i]:
            d.text((480, y), fit_text(d, line, fonts["code"], 384), font=fonts["code"], fill=color)
            last_visible = i
        y += 27
    if last_visible < len(CODE_LINES) - 1 and frame % 8 < 4:  # blinking cursor
        cursor_y = 342 + (last_visible + 1) * 27
        d.rectangle([480, cursor_y + 2, 489, cursor_y + 18], fill="#7dd3fc")

    # progress bar + footer
    d.rounded_rectangle([72, 478, 888, 490], radius=6, fill=CARD_BORDER)
    frac = (frame + 1) / N_FRAMES
    d.rounded_rectangle([72, 478, 72 + int(816 * frac), 490], radius=6, fill=STAGE_COLORS[stage])
    d.text((W // 2, 504), "增量输出:slides.md → slides_asr.md → slides_lecture_notes.md → PDF",
           font=fonts["foot"], fill=MUTED, anchor="ma")
    return img


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent.parent / "assets" / "demo.gif")
    parser.add_argument("--cjk-font", default="/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    parser.add_argument("--cjk-bold", default="/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")
    parser.add_argument("--mono-font", default="/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
    args = parser.parse_args()

    fonts = load_fonts(args.cjk_font, args.cjk_bold, args.mono_font)
    frames = [draw_frame(i, fonts).quantize(colors=128, dither=Image.Dither.NONE) for i in range(N_FRAMES)]
    durations = [FRAME_MS] * N_FRAMES
    durations[-1] = 1600  # hold the finished state
    args.out.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(args.out, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)
    print(f"Wrote {args.out} ({args.out.stat().st_size / 1024:.0f} KB, {N_FRAMES} frames)")


if __name__ == "__main__":
    main()
