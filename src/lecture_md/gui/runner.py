"""Run the lecture-md pipeline per video and turn its log into progress events."""

import re
import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, pyqtSignal

PROFILES = {
    "local_only": {"asr": "local", "optimize": "none", "notes": "none"},
    "standard": {"asr": "local", "optimize": "api", "notes": "none"},
    "full": {"asr": "local", "optimize": "api", "notes": "api"},
    "all_api": {"asr": "api", "optimize": "api", "notes": "api"},
}

PROFILE_LABELS = [
    ("local_only", "仅本地转写", "切页 + 本地 Whisper 转写,全程不调用 API,无需密钥"),
    ("standard", "本地转写 + 纠错", "本地 Whisper 转写后,用 API 做 OCR 辅助纠错"),
    ("full", "完整讲义(推荐)", "本地转写 + API 纠错 + 生成适合复习的讲义稿"),
    ("all_api", "全 API", "转写与纠错全部走 API,本机无需 GPU,消耗较多 Token"),
]

RE_ASR = re.compile(r"^\[ASR (\d+)/(\d+)\]")
RE_OPTIMIZE = re.compile(r"^\[Optimize (\d+)/(\d+)\]")
RE_NOTES = re.compile(r"^\[Notes (\d+)/(\d+)\]")
RE_DEDUPE = re.compile(r"^Deduped slides: (\d+) -> (\d+)")


def profile_stages(profile: str) -> set[str]:
    config = PROFILES.get(profile, PROFILES["full"])
    stages = {"slides", "asr"}
    if config["optimize"] == "api":
        stages.add("optimize")
    if config["notes"] == "api":
        stages.add("notes")
    return stages


def build_env_overrides(settings: dict) -> dict[str, str]:
    """LECTURE_MD_* values from GUI settings (empty values are skipped)."""
    mapping = {
        "LECTURE_MD_API_KEY": settings.get("api_key", ""),
        "LECTURE_MD_BASE_URL": settings.get("base_url", ""),
        "LECTURE_MD_ASR_MODEL": settings.get("asr_model", ""),
        "LECTURE_MD_CHAT_MODEL": settings.get("chat_model", ""),
        "LECTURE_MD_TERMS": settings.get("terms", ""),
    }
    return {key: value for key, value in mapping.items() if value.strip()}


def build_process_args(video: str, settings: dict) -> list[str]:
    config = PROFILES.get(settings.get("profile", "full"), PROFILES["full"])
    args = [
        "-m",
        "lecture_md",
        "process",
        "--video",
        video,
        "--output-root",
        settings["output_root"],
        "--asr",
        config["asr"],
        "--optimize",
        config["optimize"],
        "--notes",
        config["notes"],
        "--scene-threshold",
        str(settings.get("scene_threshold", 0.001)),
        "--min-scene-len",
        str(settings.get("min_scene_len", 5)),
        "--dedupe-mode",
        settings.get("dedupe_mode", "debounce"),
        "--dedupe-stable-seconds",
        str(settings.get("stable_seconds", 6.0)),
        "--asr-language",
        settings.get("language", "zh"),
        "--local-asr-model",
        settings.get("local_model", "small"),
        "--local-asr-device",
        settings.get("device", "cpu"),
        "--local-asr-compute-type",
        settings.get("compute_type", "int8"),
        "--max-chunk-seconds",
        str(settings.get("chunk_seconds", 90)),
        "--sleep",
        str(settings.get("sleep", 5.0)),
    ]
    if settings.get("skip_existing", True):
        args.append("--skip-existing")
    return args


class TaskRunner(QObject):
    """Run one video through `python -m lecture_md process` with live events."""

    log_line = pyqtSignal(str)
    stage_started = pyqtSignal(str, str)          # stage key, note
    stage_progress = pyqtSignal(str, int, int)    # stage key, current, total
    finished = pyqtSignal(bool, str)              # ok, message

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.process: QProcess | None = None
        self._buffer = ""
        self._failed_line = ""
        self._notified = False

    # -- control --------------------------------------------------------
    def start(self, video: str, settings: dict) -> None:
        self._buffer = ""
        self._failed_line = ""
        self._notified = False
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUTF8", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUNBUFFERED", "1")
        for key, value in build_env_overrides(settings).items():
            env.insert(key, value)
        process.setProcessEnvironment(env)

        process.readyReadStandardOutput.connect(self._on_output)
        process.finished.connect(self._on_finished)
        process.errorOccurred.connect(self._on_error)
        self.process = process

        args = build_process_args(video, settings)
        self.stage_started.emit("slides", "正在检测翻页并提取幻灯片…")
        self.log_line.emit("$ python " + " ".join(args))
        process.start(sys.executable, args)

    def stop(self) -> None:
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()

    def is_running(self) -> bool:
        return bool(self.process) and self.process.state() != QProcess.ProcessState.NotRunning

    # -- internals -------------------------------------------------------
    def _on_output(self) -> None:
        if not self.process:
            return
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._buffer += data
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.rstrip("\r")
            if line:
                self._handle_line(line)

    def _handle_line(self, line: str) -> None:
        self.log_line.emit(line)
        match = RE_ASR.match(line)
        if match:
            self.stage_progress.emit("asr", int(match.group(1)), int(match.group(2)))
            return
        match = RE_OPTIMIZE.match(line)
        if match:
            self.stage_progress.emit("optimize", int(match.group(1)), int(match.group(2)))
            return
        match = RE_NOTES.match(line)
        if match:
            self.stage_progress.emit("notes", int(match.group(1)), int(match.group(2)))
            return
        match = RE_DEDUPE.match(line)
        if match:
            kept = match.group(2)
            self.stage_started.emit("asr", f"切页完成,保留 {kept} 页,开始转写…")
            return
        if line.startswith("Loading local ASR model"):
            self.stage_started.emit("asr", "正在加载本地 Whisper 模型…")
        elif line.startswith("Failed "):
            self._failed_line = line

    def _on_finished(self, exit_code: int, _status) -> None:
        if self._notified:
            return
        self._notified = True
        if exit_code == 0 and not self._failed_line:
            self.finished.emit(True, "处理完成")
        else:
            message = self._failed_line or f"进程退出码 {exit_code}"
            self.finished.emit(False, message)
        self.process = None

    def _on_error(self, error) -> None:
        if self._notified:
            return
        if self.process and self.process.state() == QProcess.ProcessState.NotRunning:
            self._notified = True
            self.finished.emit(False, f"无法启动子进程({error})")
            self.process = None

