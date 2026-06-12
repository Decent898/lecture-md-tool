"""PyQt6 desktop interface for the lecture-md pipeline."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _import_qt():
    try:
        from PyQt6.QtCore import QProcess, QProcessEnvironment, Qt, QUrl
        from PyQt6.QtGui import QDesktopServices, QFont, QTextCursor
        from PyQt6.QtWidgets import (
            QApplication,
            QCheckBox,
            QComboBox,
            QFileDialog,
            QFormLayout,
            QFrame,
            QGridLayout,
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QPlainTextEdit,
            QProgressBar,
            QSpinBox,
            QSplitter,
            QTabWidget,
            QVBoxLayout,
            QWidget,
        )
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional GUI dependency
        raise SystemExit(
            "PyQt6 is not installed. Install it with:\n\n"
            '  pip install -e ".[gui]"\n\n'
            'or, for all non-GUI pipeline extras plus GUI:\n\n'
            '  pip install -e ".[all,gui]"'
        ) from exc

    return {
        "QApplication": QApplication,
        "QCheckBox": QCheckBox,
        "QComboBox": QComboBox,
        "QDesktopServices": QDesktopServices,
        "QFileDialog": QFileDialog,
        "QFont": QFont,
        "QFrame": QFrame,
        "QGridLayout": QGridLayout,
        "QGroupBox": QGroupBox,
        "QHBoxLayout": QHBoxLayout,
        "QLabel": QLabel,
        "QLineEdit": QLineEdit,
        "QMainWindow": QMainWindow,
        "QMessageBox": QMessageBox,
        "QPlainTextEdit": QPlainTextEdit,
        "QProcess": QProcess,
        "QProcessEnvironment": QProcessEnvironment,
        "QProgressBar": QProgressBar,
        "QPushButton": QPushButton,
        "QSpinBox": QSpinBox,
        "QSplitter": QSplitter,
        "QTabWidget": QTabWidget,
        "QTextCursor": QTextCursor,
        "Qt": Qt,
        "QUrl": QUrl,
        "QVBoxLayout": QVBoxLayout,
        "QHBoxLayout": QHBoxLayout,
        "QFormLayout": QFormLayout,
        "QWidget": QWidget,
    }


def _qt_stylesheet() -> str:
    return """
    QMainWindow, QWidget {
      background: #f8fafc;
      color: #0f172a;
      font-size: 13px;
    }
    QGroupBox {
      border: 1px solid #d8dee9;
      border-radius: 8px;
      margin-top: 12px;
      padding: 12px;
      background: #ffffff;
      font-weight: 600;
    }
    QGroupBox::title {
      subcontrol-origin: margin;
      left: 10px;
      padding: 0 4px;
    }
    QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      padding: 7px;
      background: #ffffff;
    }
    QPushButton {
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      padding: 8px 12px;
      background: #ffffff;
    }
    QPushButton:hover { background: #f1f5f9; }
    QPushButton#primaryButton {
      background: #2563eb;
      border-color: #2563eb;
      color: #ffffff;
      font-weight: 700;
    }
    QPushButton#dangerButton {
      background: #dc2626;
      border-color: #dc2626;
      color: #ffffff;
      font-weight: 700;
    }
    QLabel#heroTitle {
      font-size: 24px;
      font-weight: 800;
    }
    QLabel#mutedLabel { color: #64748b; }
    QProgressBar {
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      background: #e2e8f0;
      text-align: center;
      height: 18px;
    }
    QProgressBar::chunk {
      border-radius: 6px;
      background: #0f766e;
    }
    """


def _env_value(name: str, fallback: str = "") -> str:
    return os.environ.get(name, fallback)


def main() -> None:
    qt = _import_qt()

    QApplication = qt["QApplication"]
    QCheckBox = qt["QCheckBox"]
    QComboBox = qt["QComboBox"]
    QDesktopServices = qt["QDesktopServices"]
    QFileDialog = qt["QFileDialog"]
    QFont = qt["QFont"]
    QGroupBox = qt["QGroupBox"]
    QHBoxLayout = qt["QHBoxLayout"]
    QLabel = qt["QLabel"]
    QLineEdit = qt["QLineEdit"]
    QMainWindow = qt["QMainWindow"]
    QMessageBox = qt["QMessageBox"]
    QPlainTextEdit = qt["QPlainTextEdit"]
    QProcess = qt["QProcess"]
    QProcessEnvironment = qt["QProcessEnvironment"]
    QProgressBar = qt["QProgressBar"]
    QPushButton = qt["QPushButton"]
    QSpinBox = qt["QSpinBox"]
    QTabWidget = qt["QTabWidget"]
    QTextCursor = qt["QTextCursor"]
    Qt = qt["Qt"]
    QUrl = qt["QUrl"]
    QVBoxLayout = qt["QVBoxLayout"]
    QFormLayout = qt["QFormLayout"]
    QWidget = qt["QWidget"]

    class PathPicker(QWidget):
        def __init__(self, placeholder: str, mode: str) -> None:
            super().__init__()
            self.mode = mode
            self.edit = QLineEdit()
            self.edit.setPlaceholderText(placeholder)
            self.button = QPushButton("Browse")
            self.button.clicked.connect(self.pick)
            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self.edit, 1)
            layout.addWidget(self.button)

        def pick(self) -> None:
            if self.mode == "file":
                path, _ = QFileDialog.getOpenFileName(
                    self,
                    "Select lecture video",
                    "",
                    "Videos (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.m4v);;All files (*.*)",
                )
            else:
                path = QFileDialog.getExistingDirectory(self, "Select directory")
            if path:
                self.edit.setText(path)

        def text(self) -> str:
            return self.edit.text().strip()

        def setText(self, value: str) -> None:
            self.edit.setText(value)

    class LectureMdWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.process: QProcess | None = None
            self.setWindowTitle("lecture-md-tool")
            self.resize(1120, 760)
            self.setStyleSheet(_qt_stylesheet())
            self._build_ui()

        def _build_ui(self) -> None:
            root = QWidget()
            self.setCentralWidget(root)
            outer = QVBoxLayout(root)
            outer.setContentsMargins(22, 18, 22, 18)
            outer.setSpacing(12)

            title = QLabel("lecture-md-tool")
            title.setObjectName("heroTitle")
            subtitle = QLabel("Turn PPT lecture recordings into slide-aligned Markdown notes and PDFs.")
            subtitle.setObjectName("mutedLabel")
            outer.addWidget(title)
            outer.addWidget(subtitle)

            tabs = QTabWidget()
            tabs.addTab(self._pipeline_tab(), "Pipeline")
            tabs.addTab(self._api_tab(), "API")
            tabs.addTab(self._advanced_tab(), "Advanced")
            outer.addWidget(tabs, 1)

            actions = QHBoxLayout()
            self.command_preview = QLineEdit()
            self.command_preview.setReadOnly(True)
            self.command_preview.setPlaceholderText("Command preview")
            self.run_button = QPushButton("Run pipeline")
            self.run_button.setObjectName("primaryButton")
            self.run_button.clicked.connect(self.run_pipeline)
            self.stop_button = QPushButton("Stop")
            self.stop_button.setObjectName("dangerButton")
            self.stop_button.setEnabled(False)
            self.stop_button.clicked.connect(self.stop_process)
            self.pdf_button = QPushButton("Export PDFs")
            self.pdf_button.clicked.connect(self.run_pdf_export)
            self.open_output_button = QPushButton("Open output")
            self.open_output_button.clicked.connect(self.open_output)
            actions.addWidget(self.command_preview, 1)
            actions.addWidget(self.run_button)
            actions.addWidget(self.pdf_button)
            actions.addWidget(self.open_output_button)
            actions.addWidget(self.stop_button)
            outer.addLayout(actions)

            self.progress = QProgressBar()
            self.progress.setRange(0, 1)
            self.progress.setValue(0)
            outer.addWidget(self.progress)

            self.log = QPlainTextEdit()
            self.log.setReadOnly(True)
            self.log.setFont(QFont("Consolas", 10))
            outer.addWidget(self.log, 2)

            self._connect_preview_signals(root)
            self.update_preview()

        def _pipeline_tab(self) -> QWidget:
            page = QWidget()
            layout = QVBoxLayout(page)

            source_group = QGroupBox("Source")
            form = QFormLayout(source_group)
            self.source_mode = QComboBox()
            self.source_mode.addItems(["Single video", "Folder"])
            self.video_picker = PathPicker("C:/path/to/lecture.mp4", "file")
            self.input_dir_picker = PathPicker("C:/path/to/videos", "dir")
            self.input_dir_picker.setEnabled(False)
            self.source_mode.currentIndexChanged.connect(self._source_mode_changed)
            self.file_glob = QLineEdit("*.mp4")
            self.include_name = QLineEdit()
            self.include_name.setPlaceholderText("Optional course name filter, e.g. 软件工程基础")
            self.today_only = QCheckBox("Only files modified today")
            self.skip_existing = QCheckBox("Skip existing final outputs")
            form.addRow("Mode", self.source_mode)
            form.addRow("Video", self.video_picker)
            form.addRow("Folder", self.input_dir_picker)
            form.addRow("File glob", self.file_glob)
            form.addRow("Include name", self.include_name)
            form.addRow("", self.today_only)
            form.addRow("", self.skip_existing)

            output_group = QGroupBox("Output")
            out_form = QFormLayout(output_group)
            self.output_root = PathPicker("Choose output root", "dir")
            self.output_root.setText(str(Path.home() / "Documents" / "lecture_md_runs" / "gui"))
            self.auto_pdf = QCheckBox("Export PDFs after the pipeline finishes")
            out_form.addRow("Output root", self.output_root)
            out_form.addRow("", self.auto_pdf)

            mode_group = QGroupBox("Pipeline options")
            mode_form = QFormLayout(mode_group)
            self.asr_backend = QComboBox()
            self.asr_backend.addItems(["local", "api"])
            self.optimize_backend = QComboBox()
            self.optimize_backend.addItems(["api", "none"])
            self.notes_backend = QComboBox()
            self.notes_backend.addItems(["api", "none"])
            self.notes_backend.setCurrentText("api")
            self.local_device = QComboBox()
            self.local_device.addItems(["cpu", "cuda", "auto"])
            self.local_model = QComboBox()
            self.local_model.addItems(["tiny", "base", "small", "medium", "large-v3"])
            self.local_model.setCurrentText("small")
            self.language = QComboBox()
            self.language.addItems(["zh", "auto", "en", "ja", "ko"])
            mode_form.addRow("ASR", self.asr_backend)
            mode_form.addRow("Optimization", self.optimize_backend)
            mode_form.addRow("Lecture notes", self.notes_backend)
            mode_form.addRow("Local ASR model", self.local_model)
            mode_form.addRow("Local ASR device", self.local_device)
            mode_form.addRow("Language", self.language)

            layout.addWidget(source_group)
            layout.addWidget(output_group)
            layout.addWidget(mode_group)
            layout.addStretch(1)
            return page

        def _api_tab(self) -> QWidget:
            page = QWidget()
            layout = QVBoxLayout(page)
            group = QGroupBox("OpenAI-compatible API")
            form = QFormLayout(group)
            self.api_key = QLineEdit(_env_value("LECTURE_MD_API_KEY") or _env_value("OPENAI_API_KEY"))
            self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
            self.base_url = QLineEdit(_env_value("LECTURE_MD_BASE_URL", "https://api.openai.com/v1"))
            self.asr_model = QLineEdit(_env_value("LECTURE_MD_ASR_MODEL", "gpt-4o-mini-audio-preview"))
            self.chat_model = QLineEdit(_env_value("LECTURE_MD_CHAT_MODEL", "gpt-4o-mini"))
            self.terms = QLineEdit(_env_value("LECTURE_MD_TERMS"))
            self.terms.setPlaceholderText("Comma-separated course terms")
            form.addRow("API key", self.api_key)
            form.addRow("Base URL", self.base_url)
            form.addRow("ASR model", self.asr_model)
            form.addRow("Chat model", self.chat_model)
            form.addRow("Terms", self.terms)
            layout.addWidget(group)
            hint = QLabel("The key is only passed to the child process environment. It is not written to project files.")
            hint.setObjectName("mutedLabel")
            layout.addWidget(hint)
            layout.addStretch(1)
            return page

        def _advanced_tab(self) -> QWidget:
            page = QWidget()
            layout = QVBoxLayout(page)
            group = QGroupBox("Slide detection and retry settings")
            form = QFormLayout(group)
            self.scene_threshold = QLineEdit("0.001")
            self.min_scene_len = QLineEdit("5")
            self.dedupe_mode = QComboBox()
            self.dedupe_mode.addItems(["debounce", "merge"])
            self.stable_seconds = QSpinBox()
            self.stable_seconds.setRange(1, 120)
            self.stable_seconds.setValue(6)
            self.max_chunk_seconds = QSpinBox()
            self.max_chunk_seconds.setRange(10, 600)
            self.max_chunk_seconds.setValue(90)
            self.sleep_seconds = QSpinBox()
            self.sleep_seconds.setRange(0, 120)
            self.sleep_seconds.setValue(5)
            self.retry_sleep = QSpinBox()
            self.retry_sleep.setRange(1, 600)
            self.retry_sleep.setValue(30)
            form.addRow("Scene threshold", self.scene_threshold)
            form.addRow("Minimum scene seconds", self.min_scene_len)
            form.addRow("Dedupe mode", self.dedupe_mode)
            form.addRow("Stable seconds", self.stable_seconds)
            form.addRow("Max audio chunk seconds", self.max_chunk_seconds)
            form.addRow("API sleep seconds", self.sleep_seconds)
            form.addRow("Retry sleep seconds", self.retry_sleep)
            layout.addWidget(group)
            layout.addStretch(1)
            return page

        def _connect_preview_signals(self, root: QWidget) -> None:
            for widget in root.findChildren(QLineEdit):
                widget.textChanged.connect(self.update_preview)
            for widget in root.findChildren(QComboBox):
                widget.currentTextChanged.connect(self.update_preview)
            for widget in root.findChildren(QSpinBox):
                widget.valueChanged.connect(self.update_preview)
            for widget in root.findChildren(QCheckBox):
                widget.stateChanged.connect(self.update_preview)

        def _source_mode_changed(self) -> None:
            folder = self.source_mode.currentText() == "Folder"
            self.video_picker.setEnabled(not folder)
            self.input_dir_picker.setEnabled(folder)
            self.file_glob.setEnabled(folder)
            self.today_only.setEnabled(folder)
            self.update_preview()

        def build_process_args(self) -> list[str]:
            args = ["-m", "lecture_md", "process"]
            if self.source_mode.currentText() == "Folder":
                if self.input_dir_picker.text():
                    args += ["--input-dir", self.input_dir_picker.text()]
                args += ["--file-glob", self.file_glob.text().strip() or "*"]
                if self.today_only.isChecked():
                    args.append("--today")
                include = self.include_name.text().strip()
                if include:
                    args += ["--include-name", include]
            else:
                if self.video_picker.text():
                    args += ["--video", self.video_picker.text()]
            args += ["--output-root", self.output_root.text()]
            args += ["--asr", self.asr_backend.currentText()]
            args += ["--optimize", self.optimize_backend.currentText()]
            args += ["--notes", self.notes_backend.currentText()]
            args += ["--asr-language", self.language.currentText()]
            args += ["--local-asr-model", self.local_model.currentText()]
            args += ["--local-asr-device", self.local_device.currentText()]
            args += ["--scene-threshold", self.scene_threshold.text().strip() or "0.001"]
            args += ["--min-scene-len", self.min_scene_len.text().strip() or "5"]
            args += ["--dedupe-mode", self.dedupe_mode.currentText()]
            args += ["--dedupe-stable-seconds", str(self.stable_seconds.value())]
            args += ["--max-chunk-seconds", str(self.max_chunk_seconds.value())]
            args += ["--sleep", str(self.sleep_seconds.value())]
            args += ["--retry-sleep", str(self.retry_sleep.value())]
            if self.base_url.text().strip():
                args += ["--asr-base-url", self.base_url.text().strip()]
                args += ["--optimize-base-url", self.base_url.text().strip()]
            if self.asr_model.text().strip():
                args += ["--asr-model", self.asr_model.text().strip()]
            if self.chat_model.text().strip():
                args += ["--optimize-model", self.chat_model.text().strip()]
            if self.terms.text().strip():
                args += ["--terms", self.terms.text().strip()]
            if self.skip_existing.isChecked():
                args.append("--skip-existing")
            return args

        def build_pdf_args(self) -> list[str]:
            return [
                "-m",
                "lecture_md",
                "to-pdf",
                "--input-root",
                self.output_root.text(),
                "--output-dir",
                str(Path(self.output_root.text()) / "pdf"),
                "--overwrite",
            ]

        def process_environment(self) -> list[str]:
            env = os.environ.copy()
            if self.api_key.text().strip():
                env["LECTURE_MD_API_KEY"] = self.api_key.text().strip()
            if self.base_url.text().strip():
                env["LECTURE_MD_BASE_URL"] = self.base_url.text().strip()
            if self.asr_model.text().strip():
                env["LECTURE_MD_ASR_MODEL"] = self.asr_model.text().strip()
            if self.chat_model.text().strip():
                env["LECTURE_MD_CHAT_MODEL"] = self.chat_model.text().strip()
            if self.terms.text().strip():
                env["LECTURE_MD_TERMS"] = self.terms.text().strip()
            if "PYTHONPATH" not in env:
                package_root = Path(__file__).resolve().parents[1]
                env["PYTHONPATH"] = str(package_root)
            return [f"{key}={value}" for key, value in env.items()]

        def update_preview(self) -> None:
            try:
                args = self.build_process_args()
            except RuntimeError:
                return
            self.command_preview.setText("python " + " ".join(f'"{arg}"' if " " in arg else arg for arg in args))

        def validate_run(self) -> bool:
            if self.source_mode.currentText() == "Folder":
                path = self.input_dir_picker.text()
                if not path or not Path(path).exists():
                    QMessageBox.warning(self, "Missing folder", "Please select an input folder.")
                    return False
            else:
                path = self.video_picker.text()
                if not path or not Path(path).exists():
                    QMessageBox.warning(self, "Missing video", "Please select a lecture video.")
                    return False
            if not self.output_root.text():
                QMessageBox.warning(self, "Missing output", "Please select an output directory.")
                return False
            needs_api = self.asr_backend.currentText() == "api" or self.optimize_backend.currentText() == "api" or self.notes_backend.currentText() == "api"
            if needs_api and not self.api_key.text().strip() and not _env_value("OPENAI_API_KEY"):
                QMessageBox.warning(self, "Missing API key", "This configuration needs an API key.")
                return False
            return True

        def start_process(self, args: list[str], title: str, auto_pdf_after: bool = False) -> None:
            if self.process is not None:
                QMessageBox.information(self, "Busy", "A command is already running.")
                return
            self.append_log(f"\n== {title} ==\n$ python {' '.join(args)}\n")
            self.progress.setRange(0, 0)
            self.run_button.setEnabled(False)
            self.pdf_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            process = QProcess(self)
            process.setProgram(sys.executable)
            process.setArguments(args)
            env = QProcessEnvironment.systemEnvironment()
            for item in self.process_environment():
                key, _, value = item.partition("=")
                env.insert(key, value)
            process.setProcessEnvironment(env)
            process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
            process.readyReadStandardOutput.connect(lambda: self.read_output(process))
            process.finished.connect(lambda code, status: self.process_finished(code, status, auto_pdf_after))
            self.process = process
            process.start()

        def run_pipeline(self) -> None:
            if not self.validate_run():
                return
            self.start_process(self.build_process_args(), "Pipeline", self.auto_pdf.isChecked())

        def run_pdf_export(self) -> None:
            if not self.output_root.text():
                QMessageBox.warning(self, "Missing output", "Please select an output directory.")
                return
            self.start_process(self.build_pdf_args(), "PDF export")

        def stop_process(self) -> None:
            if self.process is not None:
                self.append_log("\nStopping process...\n")
                self.process.kill()

        def read_output(self, process: QProcess) -> None:
            data = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
            if data:
                self.append_log(data)

        def process_finished(self, code: int, status, auto_pdf_after: bool) -> None:
            self.append_log(f"\nProcess finished with exit code {code}.\n")
            self.progress.setRange(0, 1)
            self.progress.setValue(1 if code == 0 else 0)
            self.run_button.setEnabled(True)
            self.pdf_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.process = None
            if code == 0 and auto_pdf_after:
                self.start_process(self.build_pdf_args(), "PDF export")

        def append_log(self, text: str) -> None:
            self.log.moveCursor(QTextCursor.MoveOperation.End)
            self.log.insertPlainText(text)
            self.log.moveCursor(QTextCursor.MoveOperation.End)

        def open_output(self) -> None:
            path = Path(self.output_root.text())
            path.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    app = QApplication(sys.argv)
    app.setApplicationName("lecture-md-tool")
    window = LectureMdWindow()
    window.show()
    sys.exit(app.exec())


def add_arguments(parser) -> None:
    parser.set_defaults(handler=lambda _args: main())


def run_cli(_args) -> None:
    main()


if __name__ == "__main__":
    main()
