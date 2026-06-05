#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: ./run_one.sh /path/to/video.mp4 /path/to/output-root [extra args]"
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VIDEO="$1"
OUTPUT_ROOT="$2"
shift 2
python "$SCRIPT_DIR/lecture_md_batch.py" --video "$VIDEO" --output-root "$OUTPUT_ROOT" "$@"
