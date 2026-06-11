#!/usr/bin/env bash
# Process one lecture video. Usage:
#   ./scripts/run_one.sh /path/to/video.mp4 ./out [extra lecture-md process args]
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: ./scripts/run_one.sh /path/to/video.mp4 /path/to/output-root [extra args]"
  exit 2
fi

VIDEO="$1"
OUTPUT_ROOT="$2"
shift 2
python -m lecture_md process --video "$VIDEO" --output-root "$OUTPUT_ROOT" "$@"
