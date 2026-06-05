#!/usr/bin/env bash
set -euo pipefail

INPUT_DIR="${1:-$HOME/Downloads}"
OUTPUT_ROOT="${2:-./batch_mimo_today}"

if [[ -z "${MIMO_API_KEY:-}" ]]; then
  echo "MIMO_API_KEY is not set"
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python "$SCRIPT_DIR/lecture_md_batch.py" --input-dir "$INPUT_DIR" --today --output-root "$OUTPUT_ROOT" --skip-existing

