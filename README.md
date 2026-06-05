# Lecture Markdown Tool

Turn lecture screen-recording videos into Markdown notes aligned by slide page.

The workflow is:

1. `slidegeist` detects slide/page changes and extracts `slides/slide_XXX.jpg`.
2. A debounce pass folds only unstable slide cuts caused by cursor motion, pointer marks, compression noise, or brief flip-back frames.
3. `ffmpeg` cuts audio according to each cleaned slide time range.
4. ASR transcribes each slide's audio, using either MiMo API or local Whisper.
5. Optional language optimization uses RapidOCR plus MiMo text API to correct ASR errors with slide context.
6. Optional lecture-note generation turns each slide into a concise, de-oralized handout page while keeping transcripts.
7. The final note is written to `slides_asr.md`, `slides_optimized.md`, or `slides_lecture_notes.md`.

## Outputs

Each video gets its own output directory:

- `slides.md`: slidegeist's extracted slide timeline
- `slides_raw.md`: original slidegeist timeline before dedupe, when dedupe is enabled
- `slides_dedupe.json`: debounce/dedupe summary and merge metadata
- `slides/`: extracted slide images
- `slides_asr.md`: per-slide ASR transcript
- `asr.json`: raw ASR records and metadata
- `slides_optimized.md`: final API-optimized Markdown when `--optimize api`
- `optimization.json`: OCR text, original ASR, optimized transcript, and notes
- `slides_lecture_notes.md`: cleaned handout-style notes plus corrected transcript and ASR text when `--notes api`
- `lecture_notes.json`: per-slide cleaned note records
- `batch.log`: command log for batch runs

## Requirements

- Python 3.10+
- ffmpeg and ffprobe
- MiMo API key, only when using `--asr api` or `--optimize api`

### macOS

```bash
brew install ffmpeg
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install faster-whisper  # only needed for --asr local
```

### Windows PowerShell

Install ffmpeg or place it somewhere known, then:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install faster-whisper  # only needed for --asr local
```

## API Key

Do not commit your API key. Set it as an environment variable when using API ASR or API optimization:

macOS/Linux:

```bash
export MIMO_API_KEY="your-key"
```

Windows PowerShell:

```powershell
$env:MIMO_API_KEY = "your-key"
```

For course-specific API cleanup, pass a term list or set it as an environment variable:

```bash
export LECTURE_MD_TERMS="LR(0), LR(1), FIRST, FOLLOW, GOTO, ACTION, 移进, 规约, 文法"
```

```powershell
$env:LECTURE_MD_TERMS = "LR(0), LR(1), FIRST, FOLLOW, GOTO, ACTION, 移进, 规约, 文法"
```

## Process One Video

macOS/Linux:

```bash
./run_one.sh "/path/to/lecture.mp4" ./out
./run_one.sh "/path/to/lecture.mp4" ./out --asr local --optimize none
```

Windows PowerShell:

```powershell
.\run_one.ps1 -Video "C:\path\to\lecture.mp4" -OutputRoot ".\out"
.\run_one.ps1 -Video "C:\path\to\lecture.mp4" -OutputRoot ".\out" --asr local --optimize none
```

## Process Today's Videos In A Folder

macOS/Linux:

```bash
./run_today.sh ~/Downloads ./batch_mimo_today
./run_today.sh ~/Downloads ./batch_mimo_today --asr local --optimize none
```

Windows PowerShell:

```powershell
.\run_today.ps1 -InputDir "$env:USERPROFILE\Downloads" -OutputRoot ".\batch_mimo_today"
.\run_today.ps1 -InputDir "$env:USERPROFILE\Downloads" -OutputRoot ".\batch_mimo_today" --asr local --optimize none
```

## ASR And Optimization Modes

Fast local transcription, no API key:

```bash
pip install faster-whisper
python lecture_md_batch.py --video /path/to/video.mp4 --output-root ./out --asr local --optimize none
```

Local transcription plus API language optimization:

```bash
export MIMO_API_KEY="your-key"
python lecture_md_batch.py --video /path/to/video.mp4 --output-root ./out --asr local --optimize api
```

Local transcription plus API cleanup and handout notes:

```bash
export MIMO_API_KEY="your-key"
python lecture_md_batch.py --video /path/to/video.mp4 --output-root ./out --asr local --optimize api --notes api
```

Full API mode:

```bash
export MIMO_API_KEY="your-key"
python lecture_md_batch.py --video /path/to/video.mp4 --output-root ./out --asr api --optimize api
```

## Python CLI

The shell wrappers call the Python batch CLI:

```bash
python lecture_md_batch.py --video /path/to/video.mp4 --output-root ./out
python lecture_md_batch.py --input-dir ~/Downloads --today --output-root ./batch_mimo_today
```

Useful parameters:

- `--dedupe-slides` / `--no-dedupe-slides`: clean slide cuts; enabled by default
- `--dedupe-mode debounce`: default AutoSlides-style conservative debounce. Use `merge` for the older aggressive visual merge mode.
- `--dedupe-stable-seconds 6`: in `debounce` mode, only visually repeated or flip-back cuts shorter than this are folded
- `--dedupe-hash-distance 6`: larger means more tolerant perceptual-hash matching
- `--dedupe-rms 4.0`: larger means more tolerant pixel-level matching
- `--dedupe-min-slide-seconds 2`: always treat very short repeated cuts as unstable
- `--dedupe-max-slide-seconds 300`: keep long repeated-slide stretches split into manageable chunks
- `--dedupe-crop-ratio 0.04`: ignore slide edges while comparing screenshots
- `--asr api|local`: choose MiMo API ASR or local Whisper ASR
- `--optimize api|none`: run or skip API language optimization
- `--notes api|none`: generate de-oralized lecture-note pages while preserving transcripts
- `--asr-language zh`: ASR language code; use `auto` for local auto-detect
- `--local-asr-model small`: faster-whisper model for local ASR
- `--local-asr-device cpu`: set `cuda` if faster-whisper can use your GPU
- `--asr-model mimo-v2.5-asr`: MiMo ASR model
- `--optimize-model mimo-v2.5-pro`: MiMo text model for language optimization
- `--terms "LR(0), LR(1), ..."`: course/domain terms used by API language optimization
- `--asr-base-url` and `--optimize-base-url`: API base URLs
- `--scene-threshold 0.001`: lower means more sensitive slide cuts
- `--min-scene-len 5`: merge very short segments
- `--start-offset 0`: do not skip the start of the recording
- `--max-chunk-seconds 90`: keep ASR chunks short enough for API limits and local memory
- `--sleep 5`: delay between API calls to reduce rate limiting

## Notes

- If `ffmpeg` is installed but not found on Windows, add its `bin` directory to the current shell first, for example: `$env:PATH="C:\path\to\ffmpeg\bin;$env:PATH"`.
- `mimo-v2.5-asr` is used through `/v1/chat/completions` with `input_audio`, not `/v1/audio/transcriptions`.
- Local ASR uses `faster-whisper`; the first run downloads the selected Whisper model.
- Default `--dedupe-mode debounce` is conservative: long slide segments are preserved even when they look similar, which protects progressive PPT pages.
- If a two-hour lecture produces hundreds or thousands of slides, keep dedupe enabled, raise `--dedupe-stable-seconds`, or use `--dedupe-mode merge` only when you accept more aggressive duplicate removal.
- Long slide intervals are split into smaller audio chunks automatically.
- The scripts retry 429 and temporary network failures and write progress incrementally so runs can resume.
- If slide detection is poor for a video, tune `--scene-threshold` and `--min-scene-len`.
