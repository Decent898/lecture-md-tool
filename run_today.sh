#!/usr/bin/env bash
set -euo pipefail

INPUT_DIR="${1:-$HOME/Downloads}"
OUTPUT_ROOT="${2:-./batch_mimo_today}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ $# -gt 0 ]]; then
  shift
fi
if [[ $# -gt 0 ]]; then
  shift
fi
python "$SCRIPT_DIR/lecture_md_batch.py" --input-dir "$INPUT_DIR" --today --output-root "$OUTPUT_ROOT" --skip-existing "$@"
