#!/bin/zsh
# Adjudication-only stability diagnostic: all 10 videos, 3 adjudications each.
# Evidence is extracted once per video and cached (exact same structured
# evidence held constant across adjudications). Diagnostic only.
set -a; source config.env; set +a
export V2_FORCE_STAGED=1 V2_FRAME_MAX_EDGE=512 V2_API_RETRIES=8
VIDEOS_DIR=/Users/huangmingyao/Desktop/bc_30
for i in 01 02 03 04 05 06 07 08 09 10; do
  echo "=== adj-stab v$i start $(date +%H:%M:%S) ==="
  python3 -m v2.benchmarks.adjudication_stability \
    --video "$VIDEOS_DIR/v$i.mp4" --creative-id "v$i" --repeats 3 || echo "v$i FAILED"
done
echo "=== ALL DONE $(date +%H:%M:%S) ==="
