# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.0] - 2026-06-12

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
