import argparse
import html
import re
import subprocess
import tempfile
from pathlib import Path


DEFAULT_EDGE_PATHS = [
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
]


IMAGE_RE = re.compile(r"^\[!\[([^\]]*)\]\(([^)]+)\)\]\(([^)]+)\)\s*$")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render lecture Markdown notes to PDF with a headless browser.")
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--include-name", action="append", default=[])
    parser.add_argument("--md-name", default="slides_lecture_notes.md")
    parser.add_argument("--browser", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def find_browser(explicit: Path | None) -> Path:
    if explicit:
        if explicit.exists():
            return explicit
        raise FileNotFoundError(f"Browser not found: {explicit}")
    for path in DEFAULT_EDGE_PATHS:
        if path.exists():
            return path
    raise FileNotFoundError("No Edge/Chrome executable found.")


def safe_name(text: str) -> str:
    text = re.sub(r'[\\/:*?"<>|]+', "_", text)
    return re.sub(r"\s+", "_", text).strip("_") or "notes"


def file_uri(path: Path) -> str:
    return path.resolve().as_uri()


def inline_markdown(text: str) -> str:
    escaped = html.escape(text)

    def repl_bold(match: re.Match[str]) -> str:
        return f"<strong>{match.group(1)}</strong>"

    escaped = BOLD_RE.sub(repl_bold, escaped)

    def repl_link(match: re.Match[str]) -> str:
        label = match.group(1)
        href = html.escape(match.group(2), quote=True)
        return f'<a href="{href}">{label}</a>'

    return LINK_RE.sub(repl_link, escaped)


def markdown_to_html(markdown: str, base_dir: Path, title: str) -> str:
    body: list[str] = []
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            body.append("</ul>")
            in_list = False

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            close_list()
            continue
        if stripped.startswith("<a name="):
            close_list()
            body.append(stripped)
            continue
        if stripped == "---":
            close_list()
            body.append("<hr>")
            continue
        image_match = IMAGE_RE.match(stripped)
        if image_match:
            close_list()
            alt = html.escape(image_match.group(1) or "Slide", quote=True)
            src = html.escape(image_match.group(2), quote=True)
            href = html.escape(image_match.group(3), quote=True)
            body.append(f'<figure><a href="{href}"><img src="{src}" alt="{alt}"></a></figure>')
            continue
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            close_list()
            level = min(len(heading_match.group(1)), 6)
            body.append(f"<h{level}>{inline_markdown(heading_match.group(2))}</h{level}>")
            continue
        list_match = re.match(r"^[-*]\s+(.+)$", stripped)
        if list_match:
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f"<li>{inline_markdown(list_match.group(1))}</li>")
            continue
        close_list()
        body.append(f"<p>{inline_markdown(stripped)}</p>")
    close_list()

    base_href = html.escape(base_dir.resolve().as_uri() + "/", quote=True)
    title_html = html.escape(title)
    css = """
    @page { size: A4; margin: 14mm 12mm; }
    body {
      font-family: "Microsoft YaHei", "Noto Sans CJK SC", "Segoe UI", Arial, sans-serif;
      color: #111827;
      line-height: 1.55;
      font-size: 13px;
    }
    h1 { font-size: 25px; margin: 0 0 16px; }
    h2 { font-size: 20px; margin: 24px 0 10px; page-break-before: auto; }
    h3 { font-size: 15px; margin: 14px 0 6px; color: #1f2937; }
    p { margin: 5px 0 9px; }
    hr { border: 0; border-top: 1px solid #d1d5db; margin: 18px 0; }
    figure { margin: 8px 0 12px; page-break-inside: avoid; }
    img { display: block; max-width: 100%; max-height: 145mm; object-fit: contain; border: 1px solid #e5e7eb; }
    a { color: #1d4ed8; text-decoration: none; }
    ul { margin: 6px 0 10px 22px; padding: 0; }
    li { margin: 3px 0; }
    strong { font-weight: 700; }
    """
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <base href="{base_href}">
  <title>{title_html}</title>
  <style>{css}</style>
</head>
<body>
{chr(10).join(body)}
</body>
</html>
"""


def render_pdf(browser: Path, html_path: Path, pdf_path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="md-pdf-browser-") as user_data_dir:
        cmd = [
            str(browser),
            "--headless",
            "--disable-gpu",
            "--no-first-run",
            f"--user-data-dir={user_data_dir}",
            f"--print-to-pdf={pdf_path}",
            file_uri(html_path),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def main() -> None:
    args = parse_args()
    browser = find_browser(args.browser)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    html_dir = args.output_dir / "html"
    html_dir.mkdir(parents=True, exist_ok=True)

    selected = []
    for directory in sorted(args.input_root.glob("screen_*"), key=lambda path: path.name):
        if not directory.is_dir():
            continue
        if args.include_name and not any(include in directory.name for include in args.include_name):
            continue
        md_path = directory / args.md_name
        if md_path.exists():
            selected.append((directory, md_path))

    for directory, md_path in selected:
        name = safe_name(directory.name)
        html_path = html_dir / f"{name}.html"
        pdf_path = args.output_dir / f"{name}.pdf"
        if pdf_path.exists() and not args.overwrite:
            print(f"skipped: {pdf_path.name}", flush=True)
            continue
        markdown = md_path.read_text(encoding="utf-8", errors="replace")
        html_path.write_text(markdown_to_html(markdown, directory, directory.name), encoding="utf-8")
        render_pdf(browser, html_path, pdf_path)
        print(f"rendered: {pdf_path.name}", flush=True)

    print(f"PDF count: {len(list(args.output_dir.glob('*.pdf')))}", flush=True)


if __name__ == "__main__":
    main()
