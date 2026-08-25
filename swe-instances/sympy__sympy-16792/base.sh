#!/usr/bin/env bash
set -uo pipefail

INSTANCE_ID="sympy__sympy-16792"
BASE_COMMIT="09786a173e7a0a488f46dd6000177c23e5d24eed"
DOCKER="/Users/es256599/.local/bin/docker"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

dexec() {
  "$DOCKER" exec "$INSTANCE_ID" bash -lc "cd /testbed && $*"
}

IMAGE_COMPONENT="$(printf '%s' "$INSTANCE_ID" | sed 's/__/_1776_/' | tr '[:upper:]' '[:lower:]')"
DOCKER_IMAGE="swebench/sweb.eval.x86_64.${IMAGE_COMPONENT}:latest"

"$DOCKER" pull --platform linux/amd64 "$DOCKER_IMAGE"
"$DOCKER" rm -f "$INSTANCE_ID" >/dev/null 2>&1 || true
"$DOCKER" run -dit \
  --platform linux/amd64 \
  --name "$INSTANCE_ID" \
  "$DOCKER_IMAGE" \
  sleep infinity

dexec "git reset --hard '$BASE_COMMIT' && git clean -fd && test \"\$(git rev-parse HEAD)\" = '$BASE_COMMIT'"
dexec "source /opt/miniconda3/bin/activate testbed && python -m pip install -e . --verbose"
dexec "mkdir -p /reports"

"$DOCKER" cp "$SCRIPT_DIR/run-suite.sh" "$INSTANCE_ID:/run-suite.sh"
"$DOCKER" cp "$SCRIPT_DIR/../../parse_junit.py" "$INSTANCE_ID:/parse_junit.py"
"$DOCKER" exec "$INSTANCE_ID" chmod +x /run-suite.sh

run_suite() {
  local prefix="$1"
  dexec "source /opt/miniconda3/bin/activate testbed && pytest -rA -vv -o console_output_style=classic --tb=short --cov-config=/testbed/.coveragerc --cov-report=term-missing --junitxml=/reports/${prefix}-junit.xml --log-file=/reports/${prefix}-pytest.log --log-file-level=DEBUG 2>&1 | tee /reports/${prefix}-pytest.out"
}

run_suite base_run1
run_suite base_run2
run_suite base_run3

dexec "source /opt/miniconda3/bin/activate testbed && python /parse_junit.py /reports/base_run1-junit.xml /reports/base_run1-junit.json && python /parse_junit.py /reports/base_run2-junit.xml /reports/base_run2-junit.json && python /parse_junit.py /reports/base_run3-junit.xml /reports/base_run3-junit.json"

dexec "diff /reports/base_run1-junit.json /reports/base_run2-junit.json && diff /reports/base_run2-junit.json /reports/base_run3-junit.json && echo 'All three runs have the same test results!' || echo 'Test results differ across runs!'"

"$DOCKER" exec -it "$INSTANCE_ID" bash -lc "cd /testbed && exec bash"
