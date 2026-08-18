#!/usr/bin/env bash
set -uo pipefail; cd "$(dirname "$0")/.."
export DOCKER_DEFAULT_PLATFORM=linux/amd64
for mr in claude-opus-run3 minimax-m3-run3; do
  python -m swebench.harness.run_evaluation --dataset_name SWE-bench/SWE-bench_Verified \
    --predictions_path patch-diff/preds/_re_$mr.jsonl --max_workers 1 --run_id patchdiff-baseline \
    --cache_level instance 2>&1 | grep -v "httpx\|HTTP Request"
done
mv -f ./*.patchdiff-baseline.json patch-diff/reports/ 2>/dev/null || true
echo DONE_RETRY
