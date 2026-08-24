#!/bin/zsh
# Adjudication-only stability over CACHED evidence artifacts (no multimodal
# extraction). Works while the video multimodal gateway is degraded as long as
# single adjudication calls get through.
set -a; source config.env; set +a
export V2_API_RETRIES=8
for i in 01 02 04; do
  echo "=== replay-stab v$i start $(date +%H:%M:%S) ==="
  python3 -m v2.benchmarks.adjudication_stability \
    --evidence "output/v$i/v2/structured_evidence.json" \
    --creative-id "v$i" --repeats 3 || echo "v$i FAILED"
done
echo "=== ALL DONE $(date +%H:%M:%S) ==="
