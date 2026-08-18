#!/usr/bin/env bash
# Re-check that all 214 fl_wrong_resolved agent patches (and 64 gold patches) resolve,
# using the standard SWE-bench Verified harness on a NATIVE x86_64 machine (Windows+WSL2).
# No emulation: prebuilt swebench/sweb.eval.x86_64.* images pull directly.
#
# DISK: --cache_level env makes the harness DELETE each ~2-4GB instance image immediately
# after that instance finishes (per-instance, in run_instance's finally). So images do NOT
# accumulate: peak disk ~= base image + (max_workers x one instance image) ~= 15-20 GB at
# 4 workers, NOT 64 x 4GB. Workers therefore control both speed and peak disk.
#
# Usage (from this folder, inside WSL):
#   bash run_all.sh                 # run_id=recheck, 4 workers, all repos
#   bash run_all.sh recheck 3       # fewer workers -> lower peak disk (~12 GB)
#   REPO=django bash run_all.sh     # only one repo (used by run_by_repo.sh)
set -uo pipefail
cd "$(dirname "$0")"
RUN_ID="${1:-recheck}"
WORKERS="${2:-4}"
DATASET="SWE-bench/SWE-bench_Verified"
REPO_FILTER="${REPO:-}"
mkdir -p reports logs

# python: prefer python3, fall back to python. Preflight the swebench install.
PYBIN="$(command -v python3 || command -v python)"
[ -z "$PYBIN" ] && { echo "ERROR: no python3/python on PATH"; exit 1; }
"$PYBIN" -c "import swebench" 2>/dev/null || { echo "ERROR: swebench not installed for $PYBIN. Run: pip3 install swebench datasets"; exit 1; }

disk() { docker system df 2>/dev/null | awk '/^Images/{print "   docker images on disk: "$4" (reclaimable "$5")"}'; }

for f in preds/gold.jsonl preds/agent__*.jsonl; do
  # optional per-repo filter: only run instance_ids whose repo matches $REPO
  IDS=$("$PYBIN" _ids.py "$f" "$REPO_FILTER")
  [ -z "$IDS" ] && continue
  echo "==================== $f  ($(echo $IDS | wc -w) cells${REPO_FILTER:+, repo=$REPO_FILTER}) ===================="
  "$PYBIN" -m swebench.harness.run_evaluation \
    --dataset_name "$DATASET" \
    --predictions_path "$f" \
    --instance_ids $IDS \
    --max_workers "$WORKERS" \
    --run_id "$RUN_ID" \
    --cache_level env \
    2>&1 | grep -v "httpx\|HTTP Request"
  docker image prune -f >/dev/null 2>&1 || true      # drop dangling layers between files
  disk
done

mv -f ./*."$RUN_ID".json reports/ 2>/dev/null || true
echo "==================== DONE ===================="
ls -la reports/ 2>/dev/null
echo "Now run:  python3 summarize.py"
