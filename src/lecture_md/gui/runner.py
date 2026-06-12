"""Run the lecture-md pipeline per video and turn its log into progress events."""

import os
import re
import shutil
import sys

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, pyqtSignal

from lecture_md.gui.envcheck import static_ffmpeg_dir

PROFILES = {
    "local_only": {"asr": "local", "optimize": "none", "notes": "none"},
    "standard": {"asr": "local", "optimize": "api", "notes": "none"},
    "full": {"asr": "local", "optimize": "api", "notes": "api"},
    "all_api": {"asr": "api", "optimize": "api", "notes": "api"},
}

PROFILE_LABELS = [
    (
        "local_only",
        "仅转写(免费)",
        "得到:每页 PPT 截图 + 原始语音逐字稿(slides_asr.md)。"
        "全程在本机运行,不调用 API、零费用;缺点是转写里会有错别字和口语。",
    ),
    (
        "standard",
        "转写 + 纠错",
        "得到:校对干净的逐字稿(slides_optimized.md)——错别字、专业术语、断句"
        "已由大模型对照 PPT 上的文字逐页修正。本机转写 + 少量 API 调用。",
    ),
    (
        "full",
        "完整讲义(推荐)",
        "得到:每页一份精炼讲义稿 + 校正逐字稿 + 原始转写,三层内容齐全"
        "(slides_lecture_notes.md),可直接复习或导出 PDF。本机转写 + API 纠错与撰写。",
    ),
    (
        "all_api",
        "全 API(本机零负担)",
        "得到:与「完整讲义」完全相同的输出,但语音转写也交给 API 完成,"
        "不占用本机 CPU/GPU、无需装 faster-whisper;Token 消耗最大。",
    ),
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
        if not shutil.which("ffmpeg"):
            ffmpeg_dir = static_ffmpeg_dir()
            if ffmpeg_dir:
                env.insert("PATH", ffmpeg_dir + os.pathsep + env.value("PATH"))
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

