"""Light / dark QSS themes for the lecture-md GUI (no Qt imports needed)."""

LIGHT = {
    "bg": "#eef2f7",
    "surface": "#ffffff",
    "surface2": "#f8fafc",
    "border": "#e2e8f0",
    "text": "#0f172a",
    "muted": "#64748b",
    "accent": "#2563eb",
    "accent_hover": "#1d4ed8",
    "accent_soft": "#dbeafe",
    "on_accent": "#ffffff",
    "success": "#16a34a",
    "success_soft": "#dcfce7",
    "danger": "#dc2626",
    "danger_soft": "#fee2e2",
    "warn": "#b45309",
    "warn_soft": "#fef3c7",
    "sidebar": "#0f172a",
    "sidebar_text": "#cbd5e1",
    "sidebar_hover": "#1e293b",
    "sidebar_active": "#2563eb",
    "code_bg": "#0f172a",
    "code_text": "#dbe4f0",
    "track": "#e2e8f0",
}

DARK = {
    "bg": "#0b1220",
    "surface": "#121b2e",
    "surface2": "#0f1829",
    "border": "#26334d",
    "text": "#e6edf7",
    "muted": "#94a7c4",
    "accent": "#3b82f6",
    "accent_hover": "#60a5fa",
    "accent_soft": "#1c2f55",
    "on_accent": "#ffffff",
    "success": "#34d399",
    "success_soft": "#10331f",
    "danger": "#f87171",
    "danger_soft": "#3b1414",
    "warn": "#fbbf24",
    "warn_soft": "#3a2c08",
    "sidebar": "#070d18",
    "sidebar_text": "#94a7c4",
    "sidebar_hover": "#13203a",
    "sidebar_active": "#3b82f6",
    "code_bg": "#0a0f1c",
    "code_text": "#c9d6ea",
    "track": "#1d2940",
}

THEMES = {"light": LIGHT, "dark": DARK}


def build_qss(name: str) -> str:
    p = THEMES.get(name, LIGHT)
    return f"""
* {{
    font-family: "Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", "Segoe UI", sans-serif;
    font-size: 13px;
}}
QMainWindow, QWidget#page {{
    background: {p["bg"]};
}}
QToolTip {{
    background: {p["surface"]};
    color: {p["text"]};
    border: 1px solid {p["border"]};
    padding: 6px 8px;
    border-radius: 6px;
}}

/* ---------- sidebar ---------- */
QFrame#sidebar {{
    background: {p["sidebar"]};
    border: none;
}}
QLabel#brandMark {{
    background: {p["accent"]};
    color: {p["on_accent"]};
    font-size: 16px;
    font-weight: 800;
    border-radius: 10px;
}}
QLabel#brandName {{
    color: #ffffff;
    font-size: 15px;
    font-weight: 700;
}}
QLabel#brandSub {{
    color: {p["sidebar_text"]};
    font-size: 11px;
}}
QPushButton#navBtn {{
    background: transparent;
    color: {p["sidebar_text"]};
    border: none;
    border-radius: 10px;
    padding: 10px 14px;
    font-size: 14px;
    text-align: left;
}}
QPushButton#navBtn:hover {{
    background: {p["sidebar_hover"]};
    color: #ffffff;
}}
QPushButton#navBtn[active="true"] {{
    background: {p["sidebar_active"]};
    color: #ffffff;
    font-weight: 700;
}}
QPushButton#themeBtn {{
    background: {p["sidebar_hover"]};
    color: {p["sidebar_text"]};
    border: none;
    border-radius: 10px;
    padding: 8px 12px;
}}
QPushButton#themeBtn:hover {{
    color: #ffffff;
}}
QLabel#sidebarFoot {{
    color: {p["sidebar_text"]};
    font-size: 11px;
}}

/* ---------- generic text ---------- */
QLabel {{
    color: {p["text"]};
    background: transparent;
}}
QLabel#h1 {{
    font-size: 22px;
    font-weight: 800;
}}
QLabel#h2 {{
    font-size: 15px;
    font-weight: 700;
}}
QLabel#muted {{
    color: {p["muted"]};
}}
QLabel#statusOk {{
    color: {p["success"]};
    font-weight: 700;
}}
QLabel#statusBad {{
    color: {p["danger"]};
    font-weight: 700;
}}
QLabel#statusWarn {{
    color: {p["warn"]};
    font-weight: 700;
}}

/* ---------- cards ---------- */
QFrame#card {{
    background: {p["surface"]};
    border: 1px solid {p["border"]};
    border-radius: 14px;
}}
QFrame#dropZone {{
    background: {p["surface2"]};
    border: 2px dashed {p["border"]};
    border-radius: 14px;
}}
QFrame#dropZone[dragOver="true"] {{
    border-color: {p["accent"]};
    background: {p["accent_soft"]};
}}
QFrame#queueRow {{
    background: {p["surface2"]};
    border: 1px solid {p["border"]};
    border-radius: 10px;
}}

/* ---------- buttons ---------- */
QPushButton {{
    background: {p["surface2"]};
    color: {p["text"]};
    border: 1px solid {p["border"]};
    border-radius: 9px;
    padding: 8px 16px;
}}
QPushButton:hover {{
    border-color: {p["accent"]};
    color: {p["accent"]};
}}
QPushButton:disabled {{
    color: {p["muted"]};
    border-color: {p["border"]};
    background: {p["bg"]};
}}
QPushButton#primary {{
    background: {p["accent"]};
    color: {p["on_accent"]};
    border: none;
    font-size: 14px;
    font-weight: 700;
    padding: 10px 26px;
}}
QPushButton#primary:hover {{
    background: {p["accent_hover"]};
    color: {p["on_accent"]};
}}
QPushButton#primary:disabled {{
    background: {p["track"]};
    color: {p["muted"]};
}}
QPushButton#danger {{
    background: transparent;
    color: {p["danger"]};
    border: 1px solid {p["danger"]};
    font-weight: 700;
}}
QPushButton#danger:hover {{
    background: {p["danger_soft"]};
}}
QPushButton#link {{
    background: transparent;
    border: none;
    color: {p["accent"]};
    padding: 4px 8px;
}}
QToolButton#rowClose {{
    background: transparent;
    color: {p["muted"]};
    border: none;
    font-size: 14px;
    font-weight: 700;
}}
QToolButton#rowClose:hover {{
    color: {p["danger"]};
}}

/* ---------- inputs ---------- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{
    background: {p["surface2"]};
    color: {p["text"]};
    border: 1px solid {p["border"]};
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: {p["accent"]};
    selection-color: {p["on_accent"]};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{
    border-color: {p["accent"]};
}}
QComboBox::drop-down {{
    border: none;
    width: 26px;
}}
QComboBox QAbstractItemView {{
    background: {p["surface"]};
    color: {p["text"]};
    border: 1px solid {p["border"]};
    selection-background-color: {p["accent_soft"]};
    selection-color: {p["text"]};
}}
QCheckBox, QRadioButton {{
    color: {p["text"]};
    spacing: 8px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
}}

/* ---------- progress ---------- */
QProgressBar {{
    background: {p["track"]};
    border: none;
    border-radius: 6px;
    height: 12px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {p["accent"]};
    border-radius: 6px;
}}
QLabel#stageChip {{
    background: {p["surface2"]};
    color: {p["muted"]};
    border: 1px solid {p["border"]};
    border-radius: 12px;
    padding: 4px 12px;
    font-size: 12px;
}}
QLabel#stageChip[state="active"] {{
    background: {p["accent_soft"]};
    color: {p["accent"]};
    border-color: {p["accent"]};
    font-weight: 700;
}}
QLabel#stageChip[state="done"] {{
    background: {p["success_soft"]};
    color: {p["success"]};
    border-color: {p["success"]};
}}
QLabel#stageChip[state="failed"] {{
    background: {p["danger_soft"]};
    color: {p["danger"]};
    border-color: {p["danger"]};
}}

/* ---------- log & preview ---------- */
QPlainTextEdit#logView {{
    background: {p["code_bg"]};
    color: {p["code_text"]};
    border: 1px solid {p["border"]};
    border-radius: 10px;
    font-family: "Cascadia Mono", Consolas, "Courier New", monospace;
    font-size: 12px;
}}
QTextBrowser#preview {{
    background: {p["surface"]};
    color: {p["text"]};
    border: 1px solid {p["border"]};
    border-radius: 10px;
    padding: 10px;
}}
QListWidget {{
    background: {p["surface"]};
    color: {p["text"]};
    border: 1px solid {p["border"]};
    border-radius: 10px;
    padding: 4px;
}}
QListWidget::item {{
    border-radius: 8px;
    padding: 6px;
    margin: 2px;
}}
QListWidget::item:selected {{
    background: {p["accent_soft"]};
    color: {p["text"]};
}}

/* ---------- scrollbars ---------- */
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {p["track"]};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {p["muted"]};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {p["track"]};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
"""
