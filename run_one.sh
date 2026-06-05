#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: ./run_one.sh /path/to/video.mp4 /path/to/output-root"
  exit 2
fi

if [[ -z "${MIMO_API_KEY:-}" ]]; then
  echo "MIMO_API_KEY is not set"
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python "$SCRIPT_DIR/lecture_md_batch.py" --video "$1" --output-root "$2"

