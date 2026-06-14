"""Main window of the lecture-md desktop GUI."""

import os
import sys
from pathlib import Path

from PyQt6.QtCore import QProcess, QSettings, Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from lecture_md import __version__
from lecture_md.gui import envcheck
from lecture_md.gui.runner import PROFILE_LABELS, TaskRunner, profile_stages
from lecture_md.gui.theme import build_qss
from lecture_md.gui.widgets import (
    ApiTestWorker,
    Card,
    DropZone,
    PathPicker,
    QueueRow,
    StageProgress,
    repolish,
)
from lecture_md.runtime import cli_command

REPO_URL = "https://github.com/Decent898/lecture-md-tool"

BASE_URL_PRESETS = [
    ("OpenAI", "https://api.openai.com/v1"),
    ("DeepSeek", "https://api.deepseek.com/v1"),
    ("MiMo", "https://token-plan-cn.xiaomimimo.com/v1"),
    ("Ollama (本机)", "http://localhost:11434/v1"),
]


def default_output_root() -> str:
    return str(Path.home() / "Documents" / "lecture_md_runs" / "gui")


def load_guide() -> str:
    try:
        from importlib import resources

        return resources.files("lecture_md.gui").joinpath("guide.md").read_text(encoding="utf-8")
    except Exception:
        return "未找到使用说明文档(guide.md)。完整文档请见 GitHub 仓库。"


class MainWindow(QMainWindow):
    def __init__(self, output_root: str | None = None) -> None:
        super().__init__()
        self.settings_store = QSettings("lecture-md-tool", "gui")
        self._loading = True
        self.runner = TaskRunner(self)
        self.queue: list[str] = []
        self.queue_rows: dict[str, QueueRow] = {}
        self.queue_items: dict[str, QListWidgetItem] = {}
        self.current_video: str | None = None
        self.queue_active = False
        self.done_count = 0
        self.fail_count = 0
        self.api_worker: ApiTestWorker | None = None
        self.pdf_process: QProcess | None = None
        self.install_process: QProcess | None = None
        self._install_queue: list[list[str]] = []
        self._install_key: str | None = None

        self.setWindowTitle("lecture-md · 课程录屏转讲义")
        self.resize(1280, 850)
        self.setMinimumSize(1080, 700)

        self._build_ui()
        self._load_settings(output_root)
        self._loading = False
        self.apply_theme(self.theme_name)
        self._refresh_env_checks()
        self._refresh_results()
        self._on_profile_changed()

        self.runner.log_line.connect(self._append_log)
        self.runner.stage_started.connect(self.stage_view.start_stage)
        self.runner.stage_progress.connect(self.stage_view.stage_progress)
        self.runner.finished.connect(self._on_task_finished)

    # ================= layout =================
    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())

        self.pages = QStackedWidget()
        self.pages.addWidget(self._wrap_page(self._build_process_page()))
        self.pages.addWidget(self._wrap_page(self._build_results_page()))
        self.pages.addWidget(self._wrap_page(self._build_guide_page()))
        self.pages.addWidget(self._wrap_page(self._build_settings_page()))
        layout.addWidget(self.pages, 1)

    def _wrap_page(self, widget: QWidget) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        wrapper = QVBoxLayout(page)
        wrapper.setContentsMargins(26, 22, 26, 22)
        wrapper.addWidget(widget)
        return page

    def _build_sidebar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("sidebar")
        bar.setFixedWidth(216)
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(14, 18, 14, 16)
        layout.setSpacing(6)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        mark = QLabel("MD")
        mark.setObjectName("brandMark")
        mark.setFixedSize(38, 38)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text = QVBoxLayout()
        text.setSpacing(0)
        name = QLabel("lecture-md")
        name.setObjectName("brandName")
        sub = QLabel("录屏 → 讲义")
        sub.setObjectName("brandSub")
        text.addWidget(name)
        text.addWidget(sub)
        brand.addWidget(mark)
        brand.addLayout(text, 1)
        layout.addLayout(brand)
        layout.addSpacing(18)

        self.nav_buttons: list[QPushButton] = []
        for index, (icon, label) in enumerate(
            [("▶", "处理中心"), ("🗂", "结果浏览"), ("📖", "使用说明"), ("⚙", "设 置")]
        ):
            button = QPushButton(f"{icon}  {label}")
            button.setObjectName("navBtn")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, i=index: self._select_page(i))
            layout.addWidget(button)
            self.nav_buttons.append(button)

        layout.addStretch(1)

        self.theme_button = QPushButton("🌙  切换深色")
        self.theme_button.setObjectName("themeBtn")
        self.theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_button.clicked.connect(self._toggle_theme)
        layout.addWidget(self.theme_button)

        github = QPushButton("⭐  GitHub 项目主页")
        github.setObjectName("themeBtn")
        github.setCursor(Qt.CursorShape.PointingHandCursor)
        github.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(REPO_URL)))
        layout.addWidget(github)

        foot = QLabel(f"v{__version__} · MIT License")
        foot.setObjectName("sidebarFoot")
        foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(foot)
        return bar

    def _select_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setProperty("active", i == index)
            repolish(button)
        if index == 1:
            self._refresh_results()

    # ================= page 1: process =================
    def _build_process_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QVBoxLayout()
        h1 = QLabel("处理中心")
        h1.setObjectName("h1")
        sub = QLabel("把课程录屏转换成按 PPT 页对齐的 Markdown 讲义")
        sub.setObjectName("muted")
        title.addWidget(h1)
        title.addWidget(sub)
        header.addLayout(title, 1)

        self.profile_combo = QComboBox()
        for key, label, tip in PROFILE_LABELS:
            self.profile_combo.addItem(label, key)
            self.profile_combo.setItemData(self.profile_combo.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        self.profile_combo.setMinimumWidth(190)
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        header.addWidget(QLabel("处理方案"))
        header.addWidget(self.profile_combo)

        self.start_button = QPushButton("开始处理")
        self.start_button.setObjectName("primary")
        self.start_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_button.clicked.connect(self._start_queue)
        self.stop_button = QPushButton("停 止")
        self.stop_button.setObjectName("danger")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop_queue)
        header.addWidget(self.start_button)
        header.addWidget(self.stop_button)
        layout.addLayout(header)

        self.profile_desc = QLabel("")
        self.profile_desc.setObjectName("muted")
        self.profile_desc.setWordWrap(True)
        layout.addWidget(self.profile_desc)

        self.drop_zone = DropZone()
        self.drop_zone.paths_dropped.connect(self._add_videos)
        layout.addWidget(self.drop_zone)

        body = QHBoxLayout()
        body.setSpacing(14)

        queue_card = Card()
        queue_layout = QVBoxLayout(queue_card)
        queue_layout.setContentsMargins(16, 14, 16, 14)
        queue_layout.setSpacing(8)
        queue_head = QHBoxLayout()
        queue_title = QLabel("任务队列")
        queue_title.setObjectName("h2")
        self.queue_hint = QLabel("0 个任务")
        self.queue_hint.setObjectName("muted")
        clear_button = QPushButton("清空")
        clear_button.setObjectName("link")
        clear_button.clicked.connect(self._clear_queue)
        queue_head.addWidget(queue_title)
        queue_head.addStretch(1)
        queue_head.addWidget(self.queue_hint)
        queue_head.addWidget(clear_button)
        queue_layout.addLayout(queue_head)
        self.queue_list = QListWidget()
        self.queue_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.queue_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        queue_layout.addWidget(self.queue_list, 1)
        body.addWidget(queue_card, 4)

        progress_card = Card()
        progress_layout = QVBoxLayout(progress_card)
        progress_layout.setContentsMargins(16, 14, 16, 14)
        progress_layout.setSpacing(10)
        progress_head = QHBoxLayout()
        progress_title = QLabel("当前任务")
        progress_title.setObjectName("h2")
        self.current_label = QLabel("尚未开始")
        self.current_label.setObjectName("muted")
        progress_head.addWidget(progress_title)
        progress_head.addStretch(1)
        progress_head.addWidget(self.current_label)
        progress_layout.addLayout(progress_head)
        self.stage_view = StageProgress()
        progress_layout.addWidget(self.stage_view)
        self.log_toggle = QCheckBox("显示运行日志")
        self.log_toggle.toggled.connect(lambda checked: self.log_view.setVisible(checked))
        progress_layout.addWidget(self.log_toggle)
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(4000)
        self.log_view.setVisible(False)
        progress_layout.addWidget(self.log_view, 1)
        progress_layout.addStretch(0)
        body.addWidget(progress_card, 6)

        layout.addLayout(body, 1)
        return page

    # -- queue handling ---------------------------------------------------
    def _add_videos(self, videos: list[str]) -> None:
        added = 0
        for video in videos:
            if video in self.queue_rows:
                continue
            row = QueueRow(video)
            row.removed.connect(self._remove_video)
            item = QListWidgetItem()
            hint = row.sizeHint()
            hint.setHeight(52)
            item.setSizeHint(hint)
            self.queue_list.addItem(item)
            self.queue_list.setItemWidget(item, row)
            self.queue.append(video)
            self.queue_rows[video] = row
            self.queue_items[video] = item
            added += 1
        if added:
            self._update_queue_hint()

    def _remove_video(self, video: str) -> None:
        if video == self.current_video:
            return
        item = self.queue_items.pop(video, None)
        if item is not None:
            self.queue_list.takeItem(self.queue_list.row(item))
        self.queue_rows.pop(video, None)
        if video in self.queue:
            self.queue.remove(video)
        self._update_queue_hint()

    def _clear_queue(self) -> None:
        if self.queue_active:
            return
        self.queue_list.clear()
        self.queue.clear()
        self.queue_rows.clear()
        self.queue_items.clear()
        self._update_queue_hint()

    def _update_queue_hint(self) -> None:
        self.queue_hint.setText(f"{len(self.queue)} 个任务")

    def _pending_videos(self) -> list[str]:
        return [v for v in self.queue if self.queue_rows[v].status.text() in {"等待", "失败"}]

    def _start_queue(self) -> None:
        if self.queue_active:
            return
        if not self._pending_videos():
            QMessageBox.information(self, "队列为空", "请先把课程录屏拖入上方区域。")
            return
        settings = self.current_settings()
        if settings["profile"] != "local_only" and not self._api_key_available(settings):
            QMessageBox.warning(
                self,
                "缺少 API 密钥",
                "当前处理方案需要调用 API。\n请在「设置」页填写 API 密钥,或改用「仅转写(免费)」方案。",
            )
            self._select_page(3)
            return
        Path(settings["output_root"]).mkdir(parents=True, exist_ok=True)
        self.queue_active = True
        self.done_count = 0
        self.fail_count = 0
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.profile_combo.setEnabled(False)
        self._run_next()

    def _run_next(self) -> None:
        pending = self._pending_videos()
        if not pending:
            self._queue_done()
            return
        video = pending[0]
        self.current_video = video
        row = self.queue_rows[video]
        row.set_status("处理中", "warn")
        self.current_label.setText(Path(video).name)
        self.stage_view.configure(profile_stages(self.current_settings()["profile"]))
        self.runner.start(video, self.current_settings())

    def _on_task_finished(self, ok: bool, message: str) -> None:
        video = self.current_video
        self.current_video = None
        if video and video in self.queue_rows:
            if ok:
                self.queue_rows[video].set_status("完成 ✓", "ok")
                self.done_count += 1
            else:
                self.queue_rows[video].set_status("失败", "bad")
                self.fail_count += 1
        self.stage_view.finish(ok, message)
        if self.queue_active:
            self._run_next()

    def _queue_done(self) -> None:
        self.queue_active = False
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.profile_combo.setEnabled(True)
        summary = f"全部完成:成功 {self.done_count} 个"
        if self.fail_count:
            summary += f",失败 {self.fail_count} 个"
        self.stage_view.detail.setText(summary)
        self.current_label.setText("队列已结束")
        if self.done_count and self.open_when_done.isChecked():
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.current_settings()["output_root"]))
        self._refresh_results()

    def _stop_queue(self) -> None:
        self.queue_active = False
        self.runner.stop()
        if self.current_video and self.current_video in self.queue_rows:
            self.queue_rows[self.current_video].set_status("已停止", "bad")
        self.current_video = None
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.profile_combo.setEnabled(True)
        self.stage_view.detail.setText("已停止(已完成的页面会在下次续跑)")

    def _append_log(self, line: str) -> None:
        self.log_view.appendPlainText(line)

    def _on_profile_changed(self) -> None:
        key = self.profile_combo.currentData() or "full"
        self.stage_view.configure(profile_stages(key))
        for profile_key, _, description in PROFILE_LABELS:
            if profile_key == key:
                self.profile_desc.setText("💡 " + description)
                break
        self._save_settings()

    # ================= page 2: results =================
    def _build_results_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QVBoxLayout()
        h1 = QLabel("结果浏览")
        h1.setObjectName("h1")
        sub = QLabel("查看每个视频生成的讲义,可直接预览 Markdown 或导出 PDF")
        sub.setObjectName("muted")
        title.addWidget(h1)
        title.addWidget(sub)
        header.addLayout(title, 1)
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self._refresh_results)
        open_root = QPushButton("打开输出目录")
        open_root.clicked.connect(lambda: self._open_path(self.current_settings()["output_root"]))
        self.pdf_all_button = QPushButton("全部导出 PDF")
        self.pdf_all_button.clicked.connect(lambda: self._export_pdf(None))
        header.addWidget(refresh)
        header.addWidget(open_root)
        header.addWidget(self.pdf_all_button)
        layout.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.result_list = QListWidget()
        self.result_list.currentItemChanged.connect(lambda *_: self._show_result())
        splitter.addWidget(self.result_list)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        toolbar = QHBoxLayout()
        self.result_title = QLabel("选择左侧的视频查看讲义")
        self.result_title.setObjectName("h2")
        toolbar.addWidget(self.result_title, 1)
        self.open_folder_button = QPushButton("打开文件夹")
        self.open_folder_button.clicked.connect(self._open_selected_folder)
        self.pdf_one_button = QPushButton("导出 PDF")
        self.pdf_one_button.clicked.connect(lambda: self._export_pdf(self._selected_folder()))
        toolbar.addWidget(self.open_folder_button)
        toolbar.addWidget(self.pdf_one_button)
        right_layout.addLayout(toolbar)
        self.preview = QTextBrowser()
        self.preview.setObjectName("preview")
        self.preview.setOpenExternalLinks(True)
        right_layout.addWidget(self.preview, 1)
        self.pdf_status = QLabel("")
        self.pdf_status.setObjectName("muted")
        right_layout.addWidget(self.pdf_status)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 7)
        layout.addWidget(splitter, 1)
        return page

    PREFERRED_MD = ("slides_lecture_notes.md", "slides_optimized.md", "slides_asr.md", "slides.md")
    MD_BADGES = {
        "slides_lecture_notes.md": "📒",
        "slides_optimized.md": "✏️",
        "slides_asr.md": "🎙",
        "slides.md": "🖼",
    }

    def _refresh_results(self) -> None:
        self.result_list.clear()
        root = Path(self.current_settings()["output_root"])
        if not root.exists():
            return
        for folder in sorted(root.iterdir()):
            if not folder.is_dir():
                continue
            md = self._best_markdown(folder)
            if md is None:
                continue
            item = QListWidgetItem(f"{self.MD_BADGES[md.name]}  {folder.name}")
            item.setData(Qt.ItemDataRole.UserRole, str(folder))
            item.setToolTip(str(md))
            self.result_list.addItem(item)

    def _best_markdown(self, folder: Path) -> Path | None:
        for name in self.PREFERRED_MD:
            candidate = folder / name
            if candidate.exists() and candidate.stat().st_size > 0:
                return candidate
        return None

    def _selected_folder(self) -> str | None:
        item = self.result_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _show_result(self) -> None:
        folder = self._selected_folder()
        if not folder:
            return
        path = Path(folder)
        md = self._best_markdown(path)
        if md is None:
            return
        self.result_title.setText(path.name)
        text = md.read_text(encoding="utf-8", errors="replace")
        if len(text) > 400_000:
            text = text[:400_000] + "\n\n---\n\n*(预览已截断,完整内容请打开原文件)*"
        self.preview.setSearchPaths([str(path)])
        self.preview.setMarkdown(text)

    def _open_selected_folder(self) -> None:
        folder = self._selected_folder()
        if folder:
            self._open_path(folder)

    def _open_path(self, path: str) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _export_pdf(self, folder: str | None) -> None:
        if self.pdf_process is not None:
            return
        root = self.current_settings()["output_root"]
        out_dir = str(Path(root) / "pdf")
        args = ["-m", "lecture_md", "to-pdf", "--input-root", root, "--output-dir", out_dir, "--overwrite"]
        for name in self.PREFERRED_MD:
            if folder is None or (Path(folder) / name).exists():
                args += ["--md-name", name]
                break
        if folder:
            args += ["--include-name", Path(folder).name]
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.finished.connect(lambda code, _s: self._pdf_done(code, out_dir))
        self.pdf_process = process
        self.pdf_status.setText("正在导出 PDF…(需要本机安装 Chrome 或 Edge)")
        self.pdf_all_button.setEnabled(False)
        self.pdf_one_button.setEnabled(False)
        program, runtime_args = cli_command(*args[2:])
        process.start(program, runtime_args)

    def _pdf_done(self, exit_code: int, out_dir: str) -> None:
        self.pdf_process = None
        self.pdf_all_button.setEnabled(True)
        self.pdf_one_button.setEnabled(True)
        if exit_code == 0:
            self.pdf_status.setText(f"PDF 已导出到 {out_dir}")
            self._open_path(out_dir)
        else:
            self.pdf_status.setText("PDF 导出失败,请确认已安装 Chrome/Edge,或查看日志")

    # ================= page 3: guide =================
    def _build_guide_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        h1 = QLabel("使用说明")
        h1.setObjectName("h1")
        sub = QLabel("四种处理方案的区别、准备工作和常见问题")
        sub.setObjectName("muted")
        layout.addWidget(h1)
        layout.addWidget(sub)
        viewer = QTextBrowser()
        viewer.setObjectName("preview")
        viewer.setOpenExternalLinks(True)
        viewer.setMarkdown(load_guide())
        layout.addWidget(viewer, 1)
        return page

    # ================= page 4: settings =================
    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(14)

        h1 = QLabel("设 置")
        h1.setObjectName("h1")
        sub = QLabel("所有设置自动保存,处理时即时生效")
        sub.setObjectName("muted")
        outer.addWidget(h1)
        outer.addWidget(sub)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("page")
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, 8, 0)
        grid.setSpacing(14)

        # ---- API card ----
        api_card = Card()
        api_form = QFormLayout(api_card)
        api_form.setContentsMargins(18, 16, 18, 16)
        api_form.setSpacing(10)
        api_title = QLabel("API 后端(OpenAI 兼容)")
        api_title.setObjectName("h2")
        api_form.addRow(api_title)

        self.base_url_edit = QComboBox()
        self.base_url_edit.setEditable(True)
        for label, url in BASE_URL_PRESETS:
            self.base_url_edit.addItem(f"{url}", url)
        self.base_url_edit.setCurrentText("")
        self.base_url_edit.lineEdit().setPlaceholderText("https://api.openai.com/v1")
        api_form.addRow("API 地址", self.base_url_edit)

        key_row = QHBoxLayout()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("sk-…(留空则使用环境变量 LECTURE_MD_API_KEY)")
        self.key_visible = QPushButton("显示")
        self.key_visible.setCheckable(True)
        self.key_visible.toggled.connect(
            lambda checked: self.api_key_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        key_row.addWidget(self.api_key_edit, 1)
        key_row.addWidget(self.key_visible)
        api_form.addRow("API 密钥", key_row)

        self.asr_model_edit = QLineEdit()
        self.asr_model_edit.setPlaceholderText("如 mimo-v2.5-asr / gpt-4o-audio-preview(全 API 方案才需要)")
        api_form.addRow("音频模型", self.asr_model_edit)
        self.chat_model_edit = QLineEdit()
        self.chat_model_edit.setPlaceholderText("如 mimo-v2.5-pro / gpt-4o-mini")
        api_form.addRow("文本模型", self.chat_model_edit)
        self.terms_edit = QLineEdit()
        self.terms_edit.setPlaceholderText("课程术语,逗号分隔,如:流水线, 数据冒险, Cache 一致性")
        api_form.addRow("术语表", self.terms_edit)

        test_row = QHBoxLayout()
        self.api_test_button = QPushButton("测试连接")
        self.api_test_button.clicked.connect(self._test_api)
        self.api_test_status = QLabel("")
        self.api_test_status.setObjectName("muted")
        test_row.addWidget(self.api_test_button)
        test_row.addWidget(self.api_test_status, 1)
        api_form.addRow("", test_row)
        grid.addWidget(api_card, 0, 0)

        # ---- processing card ----
        proc_card = Card()
        proc_form = QFormLayout(proc_card)
        proc_form.setContentsMargins(18, 16, 18, 16)
        proc_form.setSpacing(10)
        proc_title = QLabel("处理参数")
        proc_title.setObjectName("h2")
        proc_form.addRow(proc_title)

        self.language_combo = QComboBox()
        for label, code in [("中文", "zh"), ("英文", "en"), ("自动检测(本地)", "auto")]:
            self.language_combo.addItem(label, code)
        proc_form.addRow("课程语言", self.language_combo)

        self.local_model_combo = QComboBox()
        for name in ["tiny", "base", "small", "medium", "large-v3"]:
            self.local_model_combo.addItem(name, name)
        self.local_model_combo.setCurrentIndex(2)
        proc_form.addRow("本地 Whisper 模型", self.local_model_combo)

        self.device_combo = QComboBox()
        for label, value in [("CPU", "cpu"), ("NVIDIA GPU (CUDA)", "cuda"), ("自动", "auto")]:
            self.device_combo.addItem(label, value)
        proc_form.addRow("本地推理设备", self.device_combo)

        self.scene_threshold_spin = QDoubleSpinBox()
        self.scene_threshold_spin.setDecimals(4)
        self.scene_threshold_spin.setRange(0.0001, 0.1)
        self.scene_threshold_spin.setSingleStep(0.001)
        self.scene_threshold_spin.setValue(0.001)
        self.scene_threshold_spin.setToolTip("翻页检测灵敏度,数值越小越敏感")
        proc_form.addRow("翻页灵敏度", self.scene_threshold_spin)

        self.min_scene_spin = QSpinBox()
        self.min_scene_spin.setRange(1, 120)
        self.min_scene_spin.setValue(5)
        self.min_scene_spin.setSuffix(" 秒")
        self.min_scene_spin.setToolTip("短于该时长的片段会被合并")
        proc_form.addRow("最短片段", self.min_scene_spin)

        self.dedupe_combo = QComboBox()
        self.dedupe_combo.addItem("防抖(保守,保护动画页)", "debounce")
        self.dedupe_combo.addItem("视觉合并(激进去重)", "merge")
        proc_form.addRow("去重模式", self.dedupe_combo)

        self.stable_spin = QDoubleSpinBox()
        self.stable_spin.setRange(0.0, 120.0)
        self.stable_spin.setValue(6.0)
        self.stable_spin.setSuffix(" 秒")
        self.stable_spin.setToolTip("防抖模式下,只折叠短于该时长的重复/翻回切页")
        proc_form.addRow("防抖窗口", self.stable_spin)

        self.chunk_spin = QSpinBox()
        self.chunk_spin.setRange(15, 600)
        self.chunk_spin.setValue(90)
        self.chunk_spin.setSuffix(" 秒")
        proc_form.addRow("音频分块上限", self.chunk_spin)

        self.sleep_spin = QDoubleSpinBox()
        self.sleep_spin.setRange(0.0, 60.0)
        self.sleep_spin.setValue(5.0)
        self.sleep_spin.setSuffix(" 秒")
        self.sleep_spin.setToolTip("API 调用间隔,频繁 429 时调大")
        proc_form.addRow("API 间隔", self.sleep_spin)

        self.skip_existing_check = QCheckBox("跳过已有最终输出的视频(支持断点续跑)")
        self.skip_existing_check.setChecked(True)
        proc_form.addRow("", self.skip_existing_check)
        grid.addWidget(proc_card, 0, 1)

        # ---- output card ----
        out_card = Card()
        out_form = QFormLayout(out_card)
        out_form.setContentsMargins(18, 16, 18, 16)
        out_form.setSpacing(10)
        out_title = QLabel("输出")
        out_title.setObjectName("h2")
        out_form.addRow(out_title)
        self.output_root_picker = PathPicker("讲义输出根目录", mode="dir")
        out_form.addRow("输出目录", self.output_root_picker)
        self.open_when_done = QCheckBox("队列完成后自动打开输出目录")
        self.open_when_done.setChecked(True)
        out_form.addRow("", self.open_when_done)
        grid.addWidget(out_card, 1, 0)

        # ---- environment card ----
        env_card = Card()
        env_layout = QVBoxLayout(env_card)
        env_layout.setContentsMargins(18, 16, 18, 16)
        env_layout.setSpacing(8)
        env_head = QHBoxLayout()
        env_title = QLabel("环境检查")
        env_title.setObjectName("h2")
        env_refresh = QPushButton("重新检测")
        env_refresh.clicked.connect(self._refresh_env_checks)
        env_head.addWidget(env_title, 1)
        env_head.addWidget(env_refresh)
        env_layout.addLayout(env_head)
        self.env_rows: dict[str, tuple[QLabel, QLabel, QPushButton]] = {}
        for key, label in [
            ("python", "Python"),
            ("ffmpeg", "ffmpeg(音频切分,必需)"),
            ("slidegeist", "slidegeist(翻页检测,必需)"),
            ("faster_whisper", "faster-whisper(本地转写)"),
            ("rapidocr", "RapidOCR(API 纠错)"),
        ]:
            row = QHBoxLayout()
            name = QLabel(label)
            status = QLabel("…")
            status.setObjectName("muted")
            install = QPushButton("安装")
            install.setObjectName("link")
            install.setCursor(Qt.CursorShape.PointingHandCursor)
            install.setVisible(False)
            if key in envcheck.INSTALL_STEPS:
                install.setToolTip(envcheck.INSTALL_NOTES.get(key, ""))
                install.clicked.connect(lambda _=False, k=key: self._install_dep(k))
            row.addWidget(name, 1)
            row.addWidget(status)
            row.addWidget(install)
            env_layout.addLayout(row)
            self.env_rows[key] = (name, status, install)
        self.install_hint = QLabel("")
        self.install_hint.setObjectName("muted")
        self.install_hint.setWordWrap(True)
        env_layout.addWidget(self.install_hint)
        env_layout.addStretch(1)
        grid.addWidget(env_card, 1, 1)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        for signal in [
            self.base_url_edit.currentTextChanged,
            self.api_key_edit.textChanged,
            self.asr_model_edit.textChanged,
            self.chat_model_edit.textChanged,
            self.terms_edit.textChanged,
            self.language_combo.currentIndexChanged,
            self.local_model_combo.currentIndexChanged,
            self.device_combo.currentIndexChanged,
            self.dedupe_combo.currentIndexChanged,
            self.output_root_picker.changed,
        ]:
            signal.connect(lambda *_: self._save_settings())
        for spin in [self.scene_threshold_spin, self.min_scene_spin, self.stable_spin, self.chunk_spin, self.sleep_spin]:
            spin.valueChanged.connect(lambda *_: self._save_settings())
        self.skip_existing_check.toggled.connect(lambda *_: self._save_settings())
        self.open_when_done.toggled.connect(lambda *_: self._save_settings())
        return page

    # -- environment ------------------------------------------------------
    def _refresh_env_checks(self) -> None:
        installing = self._install_key

        def mark(key: str, ok: bool, text: str, hint: str = "") -> None:
            _, status, install = self.env_rows[key]
            status.setText(text)
            status.setObjectName("statusOk" if ok else "statusBad")
            if hint:
                status.setToolTip(hint)
            repolish(status)
            install.setVisible(not ok and key in envcheck.INSTALL_STEPS)
            install.setEnabled(installing is None)

        mark("python", True, f"✓ {sys.version.split()[0]}")
        ffmpeg_ok, ffmpeg_detail = envcheck.ffmpeg_status()
        ffmpeg_text = "✓ 已安装" if ffmpeg_ok else "✗ 未找到"
        if ffmpeg_ok and ffmpeg_detail.startswith("static-ffmpeg:"):
            ffmpeg_text = "✓ static-ffmpeg"
        mark("ffmpeg", ffmpeg_ok, ffmpeg_text, ffmpeg_detail or "点击「安装」自动获取,或手动安装 ffmpeg 并加入 PATH")
        sg_ok, sg_detail = envcheck.slidegeist_status()
        mark("slidegeist", sg_ok, "✓ 已安装" if sg_ok else "✗ 未找到", sg_detail or "pip install slidegeist")
        has_fw = envcheck.module_status("faster_whisper")
        mark("faster_whisper", has_fw, "✓ 已安装" if has_fw else "✗ 未安装", 'pip install "lecture-md-tool[local]"')
        has_ocr = envcheck.module_status("rapidocr_onnxruntime")
        mark("rapidocr", has_ocr, "✓ 已安装" if has_ocr else "✗ 未安装", 'pip install "lecture-md-tool[ocr]"')

    # -- one-click install -------------------------------------------------
    def _install_dep(self, key: str) -> None:
        if self.install_process is not None or key not in envcheck.INSTALL_STEPS:
            return
        self._install_key = key
        self._install_queue = [list(cmd) for cmd in envcheck.INSTALL_STEPS[key]]
        _, status, _ = self.env_rows[key]
        status.setText("⏳ 安装中…")
        status.setObjectName("statusWarn")
        repolish(status)
        for _, _, button in self.env_rows.values():
            button.setEnabled(False)
        self.install_hint.setText(envcheck.INSTALL_NOTES.get(key, "正在安装…"))
        self._run_next_install_step()

    def _run_next_install_step(self) -> None:
        if not self._install_queue:
            self._install_finished(True)
            return
        cmd = self._install_queue.pop(0)
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._install_output)
        process.finished.connect(self._install_step_done)
        self.install_process = process
        process.start(cmd[0], cmd[1:])

    def _install_output(self) -> None:
        if not self.install_process:
            return
        data = bytes(self.install_process.readAllStandardOutput()).decode("utf-8", errors="replace")
        lines = [line.strip() for line in data.splitlines() if line.strip()]
        if lines:
            self.install_hint.setText(lines[-1][:160])

    def _install_step_done(self, exit_code: int, _status) -> None:
        self.install_process = None
        if exit_code == 0:
            self._run_next_install_step()
        else:
            self._install_finished(False)

    def _install_finished(self, ok: bool) -> None:
        key = self._install_key
        self._install_key = None
        self._install_queue = []
        self.install_process = None
        if ok:
            self.install_hint.setText("安装完成 ✓")
        else:
            note = envcheck.INSTALL_NOTES.get(key or "", "")
            self.install_hint.setText(f"安装失败,可在命令行手动执行:{note}")
        self._refresh_env_checks()

    def _test_api(self) -> None:
        settings = self.current_settings()
        base_url = settings["base_url"] or os.environ.get("LECTURE_MD_BASE_URL", "https://api.openai.com/v1")
        api_key = settings["api_key"] or os.environ.get("LECTURE_MD_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            self.api_test_status.setText("请先填写 API 密钥")
            return
        self.api_test_button.setEnabled(False)
        self.api_test_status.setText("正在连接 " + base_url + " …")
        self.api_worker = ApiTestWorker(base_url, api_key)
        self.api_worker.result.connect(self._api_test_done)
        self.api_worker.start()

    def _api_test_done(self, ok: bool, message: str) -> None:
        self.api_test_button.setEnabled(True)
        self.api_test_status.setText(("✓ " if ok else "✗ ") + message)
        self.api_test_status.setObjectName("statusOk" if ok else "statusBad")
        repolish(self.api_test_status)

    def _api_key_available(self, settings: dict) -> bool:
        return bool(
            settings["api_key"]
            or os.environ.get("LECTURE_MD_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("MIMO_API_KEY")
        )

    # ================= settings persistence =================
    def current_settings(self) -> dict:
        return {
            "profile": self.profile_combo.currentData() or "full",
            "base_url": self.base_url_edit.currentText().strip(),
            "api_key": self.api_key_edit.text().strip(),
            "asr_model": self.asr_model_edit.text().strip(),
            "chat_model": self.chat_model_edit.text().strip(),
            "terms": self.terms_edit.text().strip(),
            "language": self.language_combo.currentData() or "zh",
            "local_model": self.local_model_combo.currentData() or "small",
            "device": self.device_combo.currentData() or "cpu",
            "compute_type": "int8",
            "scene_threshold": self.scene_threshold_spin.value(),
            "min_scene_len": self.min_scene_spin.value(),
            "dedupe_mode": self.dedupe_combo.currentData() or "debounce",
            "stable_seconds": self.stable_spin.value(),
            "chunk_seconds": self.chunk_spin.value(),
            "sleep": self.sleep_spin.value(),
            "skip_existing": self.skip_existing_check.isChecked(),
            "output_root": self.output_root_picker.text() or default_output_root(),
        }

    def _save_settings(self) -> None:
        if self._loading:
            return
        store = self.settings_store
        values = self.current_settings()
        for key, value in values.items():
            store.setValue(f"v1/{key}", value)
        store.setValue("v1/open_when_done", self.open_when_done.isChecked())
        store.setValue("v1/theme", self.theme_name)

    def _load_settings(self, output_root_override: str | None) -> None:
        store = self.settings_store

        def text(key: str, default: str = "") -> str:
            return str(store.value(f"v1/{key}", default) or "")

        self.theme_name = text("theme", "light")
        profile = text("profile", "full")
        index = self.profile_combo.findData(profile)
        self.profile_combo.setCurrentIndex(index if index >= 0 else 2)
        self.base_url_edit.setCurrentText(text("base_url"))
        self.api_key_edit.setText(text("api_key"))
        self.asr_model_edit.setText(text("asr_model"))
        self.chat_model_edit.setText(text("chat_model"))
        self.terms_edit.setText(text("terms"))
        for combo, key, default in [
            (self.language_combo, "language", "zh"),
            (self.local_model_combo, "local_model", "small"),
            (self.device_combo, "device", "cpu"),
            (self.dedupe_combo, "dedupe_mode", "debounce"),
        ]:
            idx = combo.findData(text(key, default))
            if idx >= 0:
                combo.setCurrentIndex(idx)
        self.scene_threshold_spin.setValue(float(text("scene_threshold", "0.001") or 0.001))
        self.min_scene_spin.setValue(int(float(text("min_scene_len", "5") or 5)))
        self.stable_spin.setValue(float(text("stable_seconds", "6") or 6))
        self.chunk_spin.setValue(int(float(text("chunk_seconds", "90") or 90)))
        self.sleep_spin.setValue(float(text("sleep", "5") or 5))
        self.skip_existing_check.setChecked(text("skip_existing", "true").lower() in {"true", "1"})
        self.open_when_done.setChecked(text("open_when_done", "true").lower() in {"true", "1"})
        self.output_root_picker.set_text(output_root_override or text("output_root", default_output_root()))
        self._select_page(0)

    # ================= theme =================
    def apply_theme(self, name: str) -> None:
        self.theme_name = name
        app = QApplication.instance()
        if app:
            app.setStyleSheet(build_qss(name))
        self.theme_button.setText("☀  切换浅色" if name == "dark" else "🌙  切换深色")
        if not self._loading:
            self._save_settings()

    def _toggle_theme(self) -> None:
        self.apply_theme("dark" if self.theme_name == "light" else "light")

    # ================= lifecycle =================
    def closeEvent(self, event) -> None:  # noqa: N802
        if self.runner.is_running():
            answer = QMessageBox.question(
                self,
                "任务仍在运行",
                "当前还有任务在处理,确定要退出吗?\n(已完成的页面会保存,下次可续跑)",
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.runner.stop()
        self._save_settings()
        event.accept()


def launch(output_root: str | None = None) -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("lecture-md")
    app.setStyle("Fusion")
    window = MainWindow(output_root=output_root)
    window.show()
    test_exit_ms = os.environ.get("LECTURE_MD_GUI_TEST_EXIT_MS")
    if test_exit_ms:
        QTimer.singleShot(int(test_exit_ms), app.quit)
    sys.exit(app.exec())
