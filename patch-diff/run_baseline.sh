#!/usr/bin/env bash
# Baseline: run every agent (per model-run) and the gold predictions through the
# standard SWE-bench Verified harness. Confirms the 23 conflicting cells resolve
# (validates our accuracy labels) and caches the per-instance images that the
# differential + strengthened passes reuse.
#
# Apple-Silicon host: SWE-bench prebuilt eval images are x86_64-only. The docker-py
# SDK's pull() ignores DOCKER_DEFAULT_PLATFORM, so we PRE-PULL each image with an
# explicit --platform linux/amd64 (CLI honours it); the harness then reuses the cache.
set -uo pipefail
cd "$(dirname "$0")/.."
RUN_ID="${1:-patchdiff-baseline}"
WORKERS="${2:-2}"
DATASET="SWE-bench/SWE-bench_Verified"
export DOCKER_DEFAULT_PLATFORM=linux/amd64

echo "=== pre-pulling x86_64 images under emulation ==="
while read -r img; do
  [ -z "$img" ] && continue
  if docker image inspect "$img" >/dev/null 2>&1; then echo "cached  $img"; continue; fi
  echo "pulling $img"
  docker pull --platform linux/amd64 "$img" >/dev/null 2>&1 && echo "  ok" || echo "  FAILED $img"
done < patch-diff/images.txt

mkdir -p patch-diff/reports
for f in patch-diff/preds/gold.jsonl patch-diff/preds/agent__*.jsonl; do
  echo "=== $f ==="
  python -m swebench.harness.run_evaluation \
    --dataset_name "$DATASET" \
    --predictions_path "$f" \
    --max_workers "$WORKERS" \
    --run_id "$RUN_ID" \
    --cache_level instance \
    2>&1 | grep -v "httpx\|HTTP Request"
done
echo "=== moving report jsons into patch-diff/reports/ ==="
mv -f ./*."$RUN_ID".json patch-diff/reports/ 2>/dev/null || true
ls -la patch-diff/reports/
echo "DONE_BASELINE"
