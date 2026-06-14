# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.1] - 2026-06-14

### 修复

- 桌面打包版内置 slidegeist、static-ffmpeg、RapidOCR/ONNX Runtime，减少
  macOS / Linux / Windows 首次运行时的外部依赖
- 修复打包版点击处理、导出 PDF 或安装按钮时可能重复弹出 GUI 窗口的问题
- 改进 macOS `.dmg` 打包流程，降低 GitHub Actions 中 `hdiutil` 偶发失败概率
- 修复 Windows 打包版中 slidegeist 调用 ffmpeg 时可能因 GBK 解码失败中断的问题
- 改进本地 Whisper 模型下载失败时的提示，并支持在 GUI 填写本地模型目录
- 打包版改为进程内调用 slidegeist，避免 macOS/Windows 内部任务重复弹出 GUI 窗口
- 打包入口强制重配标准输出为 UTF-8，避免 Windows 日志中的中文路径乱码

### 新增

- 为 Windows `.exe` 和 macOS `.app` 添加应用图标

## [1.0.0] - 2026-06-12

### 新增

- PyQt6 原生桌面界面（`lecture-md gui` / `lecture-md-gui`）：侧边栏多页应用，
  含拖拽任务队列、分阶段实时进度、结果浏览与 Markdown 预览、PDF 导出、
  API 连接测试、环境自检（缺失依赖一键安装，ffmpeg 走 static-ffmpeg）、
  设置持久化与浅色/深色双主题

### 重构

- 重构为标准 `src/` 布局 Python 包，提供统一 CLI 入口 `lecture-md`（含
  `process` / `postprocess` / `asr` / `optimize` / `notes` / `dedupe` /
  `merge-hls` / `to-pdf` 子命令），支持 `pip install -e .` 安装
- API 后端泛化为任意 OpenAI 兼容接口：通过 `LECTURE_MD_API_KEY` /
  `LECTURE_MD_BASE_URL` / `LECTURE_MD_ASR_MODEL` / `LECTURE_MD_CHAT_MODEL`
  配置；继续兼容旧的 `MIMO_API_KEY`
- 抽取共享模块：HTTP 重试客户端（`client.py`）、幻灯片 Markdown 解析
  （`slides_md.py`）、配置解析（`config.py`），消除三处重复代码
- 移除内置的编译原理课程术语表；术语改为通过 `--terms` 或
  `LECTURE_MD_TERMS` 按需提供
- 批处理脚本移动到 `scripts/` 并参数化，移除硬编码的课程名与本机路径
- faster-whisper 与 rapidocr 改为可选依赖（`[local]` / `[ocr]` / `[all]`）
- PDF 导出的浏览器探测扩展到 macOS / Linux（Chrome、Edge、Chromium）
- 新增中文 README、MIT LICENSE 与本更新日志

### 兼容性说明

- 旧版输出目录可直接续跑：ASR 记录中的历史字段名仍被识别
- 旧环境变量 `MIMO_API_KEY` 仍可用，建议迁移到 `LECTURE_MD_API_KEY`
