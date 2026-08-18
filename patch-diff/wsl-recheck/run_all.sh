#!/usr/bin/env bash
# Re-check all fl_wrong_resolved agent patches (+ gold) resolve, on native x86_64 (WSL2).
# Disk is capped EXTERNALLY (works on any swebench version, incl. 5.x which dropped
# --cache_level): instances run in batches of $CHUNK and every sweb.eval.* image is deleted
# after each batch, so peak disk ~= CHUNK x one image (~4GB) + base ~= <=20 GB at CHUNK=4.
#
# Usage (inside WSL, from this folder):
#   bash run_all.sh                 # run_id=recheck, 4 workers, 4 per batch
#   bash run_all.sh recheck 3       # 3 workers
#   CHUNK=2 bash run_all.sh         # smaller batches -> lower peak disk
#   REPO=django bash run_all.sh     # only one repo
set -uo pipefail
cd "$(dirname "$0")"
RUN_ID="${1:-recheck}"
WORKERS="${2:-4}"
CHUNK="${CHUNK:-4}"
DATASET="SWE-bench/SWE-bench_Verified"
REPO_FILTER="${REPO:-}"
mkdir -p reports logs

PYBIN="$(command -v python3 || command -v python)"
[ -z "$PYBIN" ] && { echo "ERROR: no python3/python on PATH"; exit 1; }
"$PYBIN" -c "import swebench" 2>/dev/null || { echo "ERROR: swebench not installed for $PYBIN. Run: pip3 install swebench datasets"; exit 1; }

# include --cache_level only if this swebench supports it (older 4.x); harmless otherwise
CACHE_FLAG=""
"$PYBIN" -m swebench.harness.run_evaluation --help 2>&1 | grep -q -- '--cache_level' && CACHE_FLAG="--cache_level env"

prune_eval() {
  docker images --format '{{.Repository}}:{{.Tag}}' | grep -E 'sweb\.eval' \
    | xargs -r docker rmi -f >/dev/null 2>&1 || true
  docker image prune -f >/dev/null 2>&1 || true
}
disk() { docker system df 2>/dev/null | awk '/^Images/{print "   images on disk: "$4}'; }

for f in preds/gold.jsonl preds/agent__*.jsonl; do
  IDS=$("$PYBIN" _ids.py "$f" "$REPO_FILTER"); [ -z "$IDS" ] && continue
  echo "==================== $f  ($(echo $IDS | wc -w) cells${REPO_FILTER:+, repo=$REPO_FILTER}) ===================="
  set -- $IDS
  while [ "$#" -gt 0 ]; do
    BATCH=""; n=0
    while [ "$#" -gt 0 ] && [ "$n" -lt "$CHUNK" ]; do BATCH="$BATCH $1"; shift; n=$((n+1)); done
    echo "  -- batch:$BATCH"
    "$PYBIN" -m swebench.harness.run_evaluation \
      --dataset_name "$DATASET" \
      --predictions_path "$f" \
      --instance_ids $BATCH \
      --max_workers "$WORKERS" \
      --run_id "$RUN_ID" \
      $CACHE_FLAG \
      2>&1 | grep -vE "httpx|HTTP Request"
    prune_eval; disk
  done
done

mv -f ./*."$RUN_ID".json reports/ 2>/dev/null || true
echo "==================== DONE ===================="
echo "Run:  $PYBIN summarize.py     (reads per-instance logs, so batching is fine)"
