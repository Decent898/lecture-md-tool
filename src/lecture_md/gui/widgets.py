"""Reusable widgets for the lecture-md GUI."""

from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"}

STAGES = [
    ("slides", "切页去重"),
    ("asr", "按页转写"),
    ("optimize", "纠错优化"),
    ("notes", "讲义生成"),
]
STAGE_WEIGHTS = {"slides": 0.15, "asr": 0.45, "optimize": 0.25, "notes": 0.15}


def repolish(widget: QWidget) -> None:
    """Re-apply QSS after a dynamic property change."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")


class PathPicker(QWidget):
    """Line edit + browse button for a file or directory."""

    changed = pyqtSignal(str)

    def __init__(self, placeholder: str, mode: str = "dir", file_filter: str = "") -> None:
        super().__init__()
        self.mode = mode
        self.file_filter = file_filter or "所有文件 (*.*)"
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.textChanged.connect(self.changed.emit)
        button = QPushButton("浏览…")
        button.clicked.connect(self._pick)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.edit, 1)
        layout.addWidget(button)

    def _pick(self) -> None:
        if self.mode == "file":
            path, _ = QFileDialog.getOpenFileName(self, "选择文件", self.text(), self.file_filter)
        else:
            path = QFileDialog.getExistingDirectory(self, "选择文件夹", self.text())
        if path:
            self.edit.setText(path)

    def text(self) -> str:
        return self.edit.text().strip()

    def set_text(self, value: str) -> None:
        self.edit.setText(value)


class DropZone(QFrame):
    """Drag-and-drop target for videos and folders; click to browse."""

    paths_dropped = pyqtSignal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(128)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(6)
        icon = QLabel("⬇")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 26px; background: transparent;")
        head = QLabel("把课程录屏拖到这里")
        head.setObjectName("h2")
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub = QLabel("支持视频文件或整个文件夹 · 也可以点击选择")
        sub.setObjectName("muted")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)
        layout.addWidget(head)
        layout.addWidget(sub)

    # -- drag & drop ----------------------------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            self.setProperty("dragOver", True)
            repolish(self)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self.setProperty("dragOver", False)
        repolish(self)

    def dropEvent(self, event) -> None:  # noqa: N802
        self.setProperty("dragOver", False)
        repolish(self)
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        videos = collect_videos(paths)
        if videos:
            self.paths_dropped.emit(videos)
        event.acceptProposedAction()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择课程录屏",
            "",
            "视频文件 (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.m4v);;所有文件 (*.*)",
        )
        videos = collect_videos(files)
        if videos:
            self.paths_dropped.emit(videos)


def collect_videos(paths: list[str]) -> list[str]:
    """Expand files/folders into a sorted list of video file paths."""
    found: list[str] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in VIDEO_EXTS:
                    found.append(str(child))
        elif path.is_file() and path.suffix.lower() in VIDEO_EXTS:
            found.append(str(path))
    seen: set[str] = set()
    unique = []
    for item in found:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


class StageProgress(QWidget):
    """Stage chips + weighted overall progress bar + status line."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        self.chips: dict[str, QLabel] = {}
        for key, label in STAGES:
            chip = QLabel(label)
            chip.setObjectName("stageChip")
            self.chips[key] = chip
            chips.addWidget(chip)
        chips.addStretch(1)
        self.detail = QLabel("等待任务")
        self.detail.setObjectName("muted")
        chips.addWidget(self.detail)
        layout.addLayout(chips)

        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self.bar.setFixedHeight(12)
        layout.addWidget(self.bar)

        self._enabled_stages: set[str] = {key for key, _ in STAGES}
        self._done_stages: set[str] = set()
        self._active: str | None = None
        self._stage_fraction = 0.0

    def configure(self, enabled_stages: set[str]) -> None:
        self._enabled_stages = enabled_stages
        for key, chip in self.chips.items():
            chip.setVisible(key in enabled_stages)
        self.reset()

    def reset(self) -> None:
        self._done_stages = set()
        self._active = None
        self._stage_fraction = 0.0
        for chip in self.chips.values():
            chip.setProperty("state", "")
            repolish(chip)
        self.bar.setValue(0)
        self.detail.setText("等待任务")

    def _set_chip(self, key: str, state: str) -> None:
        chip = self.chips[key]
        chip.setProperty("state", state)
        repolish(chip)

    def start_stage(self, key: str, note: str = "") -> None:
        if self._active and self._active != key:
            self._done_stages.add(self._active)
            self._set_chip(self._active, "done")
        self._active = key
        self._stage_fraction = 0.0
        self._set_chip(key, "active")
        if note:
            self.detail.setText(note)
        self._update_bar()

    def stage_progress(self, key: str, current: int, total: int, note: str = "") -> None:
        if key != self._active:
            self.start_stage(key)
        self._stage_fraction = current / total if total else 0.0
        self.detail.setText(note or f"第 {current}/{total} 页")
        self._update_bar()

    def finish(self, ok: bool, note: str) -> None:
        if ok:
            for key in self._enabled_stages:
                self._set_chip(key, "done")
            self.bar.setValue(1000)
        elif self._active:
            self._set_chip(self._active, "failed")
        self.detail.setText(note)

    def _update_bar(self) -> None:
        total_weight = sum(STAGE_WEIGHTS[k] for k in self._enabled_stages) or 1.0
        done = sum(STAGE_WEIGHTS[k] for k in self._done_stages if k in self._enabled_stages)
        if self._active and self._active in self._enabled_stages:
            done += STAGE_WEIGHTS[self._active] * min(self._stage_fraction, 1.0)
        self.bar.setValue(int(done / total_weight * 1000))


class QueueRow(QWidget):
    """One row in the task queue: name + status chip + remove button."""

    removed = pyqtSignal(str)

    def __init__(self, video: str) -> None:
        super().__init__()
        self.video = video
        frame = QFrame()
        frame.setObjectName("queueRow")
        inner = QHBoxLayout(frame)
        inner.setContentsMargins(12, 8, 8, 8)
        inner.setSpacing(10)
        self.name = QLabel(Path(video).name)
        self.name.setToolTip(video)
        self.status = QLabel("等待")
        self.status.setObjectName("muted")
        self.close_btn = QToolButton()
        self.close_btn.setObjectName("rowClose")
        self.close_btn.setText("✕")
        self.close_btn.setToolTip("从队列移除")
        self.close_btn.clicked.connect(lambda: self.removed.emit(self.video))
        inner.addWidget(self.name, 1)
        inner.addWidget(self.status)
        inner.addWidget(self.close_btn)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)

    def set_status(self, text: str, kind: str) -> None:
        self.status.setText(text)
        names = {"ok": "statusOk", "bad": "statusBad", "warn": "statusWarn", "muted": "muted"}
        self.status.setObjectName(names.get(kind, "muted"))
        repolish(self.status)
        self.close_btn.setVisible(kind != "warn")  # hide while running


class ApiTestWorker(QThread):
    """Probe an OpenAI-compatible endpoint with GET /models."""

    result = pyqtSignal(bool, str)

    def __init__(self, base_url: str, api_key: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key

    def run(self) -> None:
        import requests

        url = self.base_url.rstrip("/") + "/models"
        try:
            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )
        except requests.RequestException as exc:
            self.result.emit(False, f"连接失败:{exc.__class__.__name__}")
            return
        if response.status_code == 200:
            count = ""
            try:
                data = response.json().get("data", [])
                if isinstance(data, list) and data:
                    count = f",{len(data)} 个可用模型"
            except Exception:
                pass
            self.result.emit(True, f"连接成功(HTTP 200{count})")
        elif response.status_code in {401, 403}:
            self.result.emit(False, f"密钥无效(HTTP {response.status_code})")
        else:
            self.result.emit(False, f"HTTP {response.status_code}:{response.text[:120]}")
