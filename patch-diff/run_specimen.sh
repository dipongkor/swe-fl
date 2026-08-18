#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
export DOCKER_DEFAULT_PLATFORM=linux/amd64
for f in _spec_gold _spec_agent; do
  echo "=== $f ==="
  python -m swebench.harness.run_evaluation \
    --dataset_name SWE-bench/SWE-bench_Verified \
    --predictions_path patch-diff/preds/$f.jsonl \
    --max_workers 1 --run_id spec --cache_level instance 2>&1 | grep -v "httpx\|HTTP Request" 
done
mv -f *.spec.json patch-diff/reports/ 2>/dev/null || true
echo DONE_SPECIMEN
