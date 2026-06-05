# Lecture Markdown Tool

Turn lecture screen-recording videos into Markdown notes aligned by slide page.

The workflow is:

1. `slidegeist` detects slide/page changes and extracts `slides/slide_XXX.jpg`.
2. `ffmpeg` cuts audio according to each slide time range.
3. `mimo-v2.5-asr` transcribes each slide's audio.
4. RapidOCR extracts text from each slide image.
5. `mimo-v2.5-pro` corrects ASR errors using the OCR text as slide context.
6. The final note is written to `slides_mimo_asr_corrected.md`.

## Outputs

Each video gets its own output directory:

- `slides.md`: slidegeist's extracted slide timeline
- `slides/`: extracted slide images
- `slides_mimo_asr.md`: raw per-slide MiMo ASR transcript
- `mimo_asr.json`: raw ASR records and usage metadata
- `slides_mimo_asr_corrected.md`: final corrected Markdown
- `mimo_asr_corrections.json`: OCR text, original ASR, corrected transcript, and notes
- `batch.log`: command log for batch runs

## Requirements

- Python 3.10+
- ffmpeg and ffprobe
- MiMo API key

### macOS

```bash
brew install ffmpeg
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Windows PowerShell

Install ffmpeg or place it somewhere known, then:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## API Key

Do not commit your API key. Set it as an environment variable:

macOS/Linux:

```bash
export MIMO_API_KEY="your-key"
```

Windows PowerShell:

```powershell
$env:MIMO_API_KEY = "your-key"
```

## Process One Video

macOS/Linux:

```bash
./run_one.sh "/path/to/lecture.mp4" ./out
```

Windows PowerShell:

```powershell
.\run_one.ps1 -Video "C:\path\to\lecture.mp4" -OutputRoot ".\out"
```

## Process Today's Videos In A Folder

macOS/Linux:

```bash
./run_today.sh ~/Downloads ./batch_mimo_today
```

Windows PowerShell:

```powershell
.\run_today.ps1 -InputDir "$env:USERPROFILE\Downloads" -OutputRoot ".\batch_mimo_today"
```

## Python CLI

The shell wrappers call the Python batch CLI:

```bash
python lecture_md_batch.py --video /path/to/video.mp4 --output-root ./out
python lecture_md_batch.py --input-dir ~/Downloads --today --output-root ./batch_mimo_today
```

Useful parameters:

- `--scene-threshold 0.001`: lower means more sensitive slide cuts
- `--min-scene-len 5`: merge very short segments
- `--start-offset 0`: do not skip the start of the recording
- `--max-chunk-seconds 90`: keep MiMo ASR chunks below upload limits
- `--sleep 5`: delay between API calls to reduce rate limiting

## Notes

- `mimo-v2.5-asr` is used through `/v1/chat/completions` with `input_audio`, not `/v1/audio/transcriptions`.
- Long slide intervals are split into smaller audio chunks automatically.
- The scripts retry 429 and temporary network failures and write progress incrementally so runs can resume.
- If slide detection is poor for a video, tune `--scene-threshold` and `--min-scene-len`.

