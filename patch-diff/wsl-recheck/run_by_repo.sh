#!/usr/bin/env bash
# Repo-at-a-time recheck with a HARD disk cleanup between repos. Processes repos smallest
# -> largest, and runs `docker system prune -af` after each so nothing carries over. Peak
# disk is bounded by a single repo's concurrent footprint (~workers x one instance image).
# Use this if disk is tight or you want visible per-repo checkpoints.
#
# Usage (inside WSL, from this folder):
#   bash run_by_repo.sh              # run_id=recheck, 4 workers
#   bash run_by_repo.sh recheck 3    # fewer workers -> lower peak disk
set -uo pipefail
cd "$(dirname "$0")"
RUN_ID="${1:-recheck}"
WORKERS="${2:-4}"

# smallest -> largest by instance count (astropy/pydata 2 ... django 24)
REPOS=(astropy pydata matplotlib sympy pytest-dev sphinx-doc scikit-learn django)

echo "Disk before: $(docker system df 2>/dev/null | awk '/^Images/{print $4}')"
for r in "${REPOS[@]}"; do
  echo "########################## REPO: $r ##########################"
  REPO="$r" bash run_all.sh "$RUN_ID" "$WORKERS"
  echo "--- hard cleanup after $r (only sweb.* images) ---"
  docker images --format '{{.Repository}}:{{.Tag}}' | grep -E 'sweb\.(eval|env|base)' \
    | xargs -r docker rmi -f >/dev/null 2>&1 || true
  docker image prune -f >/dev/null 2>&1 || true      # dangling layers only
  docker system df 2>/dev/null | awk '/^Images/{print "   images on disk now: "$4}'
done
echo "########################## ALL REPOS DONE ##########################"
python3 summarize.py
