# lecture-md-tool

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![OpenAI-Compatible API](https://img.shields.io/badge/API-OpenAI%20compatible-orange.svg)](#配置-api-后端)

把课程录屏视频一键转换成**按 PPT 页对齐的 Markdown 讲义**。

每页幻灯片自动截图、切分音频、语音识别（ASR）、OCR 辅助纠错，最后由大模型整理成可直接复习的讲义稿，并支持导出 PDF。适用于任何"录屏 + 讲解"形式的课程、培训或讲座视频。

## 功能特性

- **幻灯片切分**：基于 [slidegeist](https://pypi.org/project/slidegeist/) 检测翻页，自动提取每页截图与时间轴
- **防抖去重**：折叠光标移动、压缩噪声、临时翻回等造成的不稳定切分，保护渐进式 PPT 动画页
- **双 ASR 后端**：本地 faster-whisper（免费、可用 GPU）或任意 OpenAI 兼容 API 的音频模型
- **OCR 辅助纠错**：RapidOCR 提取页面文字，结合大模型逐页修正 ASR 中的术语、同音字和断句错误
- **讲义稿生成**：去口语化、公式 LaTeX 化，每页输出精炼讲义，同时保留校正转写与 ASR 原文
- **断点续跑**：所有步骤增量写盘，429 / 网络错误自动重试，中断后可直接续跑
- **流水线并行**：`postprocess` 监视模式可在 ASR 批量运行的同时并行执行 API 后处理
- **PDF 导出**：用无头 Chrome/Edge 把讲义 Markdown 渲染成 A4 PDF

## 工作流程

```
视频 ──► slidegeist 翻页检测 ──► 防抖去重 ──► ffmpeg 按页切音频
                                                    │
        讲义稿生成 ◄── OCR + LLM 纠错 ◄── ASR 转写 ◄─┘
              │
              ▼
   slides_lecture_notes.md / PDF
```

## 安装

依赖 Python 3.10+ 与 [ffmpeg](https://ffmpeg.org/)（含 ffprobe）。

```bash
git clone https://github.com/Decent898/lecture-md-tool.git
cd lecture-md-tool
python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
pip install -e ".[all]"
```

可选依赖按需安装：

| 安装方式 | 包含内容 |
| --- | --- |
| `pip install -e .` | 核心流水线（幻灯片切分 + API ASR） |
| `pip install -e ".[local]"` | 加本地 Whisper ASR（faster-whisper） |
| `pip install -e ".[ocr]"` | 加 OCR 辅助纠错（rapidocr-onnxruntime） |
| `pip install -e ".[all]"` | 全部功能 |

> Windows 上如果 ffmpeg 不在 PATH 中，先执行 `$env:PATH="C:\path\to\ffmpeg\bin;$env:PATH"`。

## 配置 API 后端

本工具兼容**任何 OpenAI 风格的 `/v1/chat/completions` 接口**（OpenAI、DeepSeek、MiMo、Ollama、vLLM 等）。不使用 API 功能（`--asr local --optimize none --notes none`）则无需任何配置。

通过环境变量配置（也可用对应命令行参数覆盖）：

| 环境变量 | 说明 | 默认值 |
| --- | --- | --- |
| `LECTURE_MD_API_KEY` | API 密钥（也接受 `OPENAI_API_KEY`） | 无 |
| `LECTURE_MD_BASE_URL` | API 地址 | `https://api.openai.com/v1` |
| `LECTURE_MD_ASR_MODEL` | 支持 `input_audio` 的音频对话模型 | `gpt-4o-mini-audio-preview` |
| `LECTURE_MD_CHAT_MODEL` | 用于纠错和讲义生成的文本模型 | `gpt-4o-mini` |
| `LECTURE_MD_TERMS` | 课程术语表（逗号分隔），辅助纠错 | 空 |

示例（macOS/Linux）：

```bash
export LECTURE_MD_API_KEY="sk-..."
export LECTURE_MD_BASE_URL="https://api.openai.com/v1"
export LECTURE_MD_TERMS="流水线, 冒险, 转发, Cache, 虚拟存储"
```

示例（Windows PowerShell，以 MiMo 为例）：

```powershell
$env:LECTURE_MD_API_KEY = "your-key"
$env:LECTURE_MD_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
$env:LECTURE_MD_ASR_MODEL = "mimo-v2.5-asr"
$env:LECTURE_MD_CHAT_MODEL = "mimo-v2.5-pro"
```

> 注意：API ASR 走的是 `/v1/chat/completions` 的 `input_audio` 消息（如 `gpt-4o-audio-preview`、`mimo-v2.5-asr`），不是 `/v1/audio/transcriptions`。请勿把密钥写进代码或提交到仓库。

## 快速开始

处理单个视频（本地 Whisper，全程免 API）：

```bash
lecture-md process --video lecture.mp4 --output-root ./out \
  --asr local --optimize none --notes none
```

本地 ASR + API 纠错 + 讲义稿（推荐）：

```bash
lecture-md process --video lecture.mp4 --output-root ./out \
  --asr local --optimize api --notes api
```

批量处理某文件夹中今天录制的视频：

```bash
lecture-md process --input-dir ~/Downloads --today --output-root ./out --skip-existing
```

ASR 批量运行的同时，另开终端并行做 API 后处理：

```bash
lecture-md postprocess --output-root ./out --watch --jobs 2
```

把讲义导出为 PDF：

```bash
lecture-md to-pdf --input-root ./out --output-dir ./pdf
```

## 命令一览

统一入口 `lecture-md`（等价于 `python -m lecture_md`）：

| 子命令 | 作用 |
| --- | --- |
| `process` | 完整流水线：切分 → 去重 → ASR → 纠错 → 讲义 |
| `postprocess` | 监视输出目录，对已完成 ASR 的视频并行执行纠错 + 讲义生成 |
| `asr` | 单步：对一个视频按页转写 |
| `optimize` | 单步：OCR + LLM 纠错一个 ASR Markdown |
| `notes` | 单步：生成讲义稿 |
| `dedupe` | 单步：清理 slides.md 中的不稳定切分 |
| `merge-hls` | 把本地 HLS `.ts` 分片合并成 `.mp4` |
| `to-pdf` | 把讲义 Markdown 渲染成 PDF |

各子命令均支持 `--help` 查看全部参数。

### `process` 常用参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--asr api\|local` | `api` | ASR 后端 |
| `--optimize api\|none` | `api` | 是否做 OCR + LLM 纠错 |
| `--notes api\|none` | `none` | 是否生成讲义稿 |
| `--file-glob` | `*` | `--input-dir` 模式下的文件名通配符 |
| `--include-name 文本` | 无 | 只处理文件名包含该文本的视频，可重复指定多门课程 |
| `--today` | 关 | 只处理今天修改过的文件 |
| `--skip-existing` | 关 | 跳过已有最终输出的视频 |
| `--dry-run` | 关 | 只打印将要处理的视频列表 |
| `--scene-threshold` | `0.001` | 翻页检测灵敏度，越小越敏感 |
| `--min-scene-len` | `5` | 合并过短片段（秒） |
| `--dedupe-mode debounce\|merge` | `debounce` | 防抖（保守）或激进视觉合并 |
| `--dedupe-stable-seconds` | `6` | 防抖模式下只折叠短于该时长的重复/翻回切分 |
| `--asr-language` | `zh` | ASR 语言，本地模式可用 `auto` 自动检测 |
| `--local-asr-model` | `small` | faster-whisper 模型 |
| `--local-asr-device` | `cpu` | 本地推理设备，可设 `cuda` |
| `--max-chunk-seconds` | `90` | 切分音频块上限，兼顾 API 限制和内存 |
| `--terms` | 空 | 课程术语表，覆盖 `LECTURE_MD_TERMS` |
| `--sleep` | `5` | API 调用间隔（秒），降低限流概率 |

## 输出文件

每个视频生成独立的输出目录：

| 文件 | 内容 |
| --- | --- |
| `slides/` | 每页幻灯片截图 |
| `slides.md` | 去重后的幻灯片时间轴 |
| `slides_raw.md` | 去重前的原始时间轴 |
| `slides_dedupe.json` | 去重决策与合并明细 |
| `slides_asr.md` | 按页 ASR 转写 |
| `asr.json` | ASR 原始记录与元数据 |
| `slides_optimized.md` | 纠错后的转写（`--optimize api`） |
| `optimization.json` | OCR 文本、原始/校正转写与修正点 |
| `slides_lecture_notes.md` | 讲义稿 + 校正转写 + ASR 原文（`--notes api`） |
| `lecture_notes.json` | 逐页讲义记录 |
| `batch.log` | 命令日志 |

批量模式还会在输出根目录生成 `manifest.json` 与 `index.md` 索引。

## 周期性批量示例

`scripts/` 目录提供可直接使用的包装脚本：

```bash
./scripts/run_one.sh lecture.mp4 ./out --asr local --optimize none
./scripts/run_today.sh ~/Downloads ./out
```

```powershell
.\scripts\run_one.ps1 -Video "C:\path\to\lecture.mp4" -OutputRoot ".\out"
.\scripts\run_today.ps1 -InputDir "$env:USERPROFILE\Downloads" -OutputRoot ".\out"

# 周期性课程录屏批处理（按课程名过滤，本地 ASR + API 纠错 + 讲义）
.\scripts\run_courses.ps1 -InputDir "E:\Recordings" -Courses "计算机组成","软件工程" -DryRun
.\scripts\run_courses.ps1 -InputDir "E:\Recordings" -Courses "计算机组成","软件工程"
```

## 常见问题

**翻页检测太碎 / 漏页？** 调节 `--scene-threshold`（越小越敏感）与 `--min-scene-len`。两小时课程出现成百上千页时，保持去重开启并调大 `--dedupe-stable-seconds`，或在接受激进合并的前提下使用 `--dedupe-mode merge`。

**本地 ASR 太慢？** 用 `--local-asr-device cuda` 启用 GPU，或换更小的模型 `--local-asr-model tiny/base`。首次运行会自动下载所选 Whisper 模型。

**API 频