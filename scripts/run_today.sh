#!/usr/bin/env bash
# Process all videos modified today in a folder. Usage:
#   ./scripts/run_today.sh [input-dir] [output-root] [extra lecture-md process args]
set -euo pipefail

INPUT_DIR="${1:-$HOME/Downloads}"
OUTPUT_ROOT="${2:-./lecture_md_out}"
if [[ $# -gt 0 ]]; then shift; fi
if [[ $# -gt 0 ]]; then shift; fi

python -m lecture_md process --input-dir "$INPUT_DIR" --today --output-root "$OUTPUT_ROOT" --skip-existing "$@"
