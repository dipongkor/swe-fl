#!/usr/bin/env bash
#
# Cross-platform SWE-bench base-run harness (Linux / macOS / Windows).
#
# Platform notes:
#   - Linux / macOS: runs natively.
#   - Windows: run under WSL2 (recommended — behaves exactly like Linux) OR
#     Git Bash. This script handles Git Bash's path-conversion quirks, but
#     interactive docker needs `winpty` (handled below). Save this file with
#     LF line endings, not CRLF, or bash will choke on the shebang.
#
set -uo pipefail   # NOTE: intentionally NOT `set -e` — failing base-run tests
                   # are expected and must not abort the script.

INSTANCE_ID="scikit-learn__scikit-learn-14496"
BASE_COMMIT="d49a6f13af2f22228d430ac64ac2b518937800d0"

# Resolve the directory this script lives in (portable).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- platform helpers --------------------------------------------------------
is_windows() {
  case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) return 0 ;; *) return 1 ;; esac
}

# Convert a host path to whatever the docker CLI on this platform expects.
host_path() {
  if is_windows; then cygpath -w "$1" 2>/dev/null || echo "$1"; else echo "$1"; fi
}

# Copy a host file to an ABSOLUTE container path, dodging MSYS path conversion
# of the container-side path on Windows.
copy_to_container() {  # $1 = host src, $2 = absolute container dest
  if is_windows; then
    MSYS_NO_PATHCONV=1 docker cp "$(host_path "$1")" "$INSTANCE_ID:$2"
  else
    docker cp "$1" "$INSTANCE_ID:$2"
  fi
}

# Run a command string inside /testbed. We `cd` inside `bash -c` instead of
# using `-w /testbed` so the container path is never seen (or mangled) by the
# host shell. Quoting also means MSYS leaves the inner /paths alone.
dexec() {  # $* = command to run in /testbed
  docker exec "$INSTANCE_ID" bash -c "cd /testbed && $*"
}
# ----------------------------------------------------------------------------

DOCKER_IMAGE="swebench/sweb.eval.x86_64.$(echo "$INSTANCE_ID" | sed 's/__/_1776_/g' | tr '[:upper:]' '[:lower:]'):latest"

# Fresh container every run (avoids "name already in use").
docker rm -f "$INSTANCE_ID" >/dev/null 2>&1 || true
docker run -dit --name "$INSTANCE_ID" "$DOCKER_IMAGE" sleep infinity

# (Derived values kept for reference / use by run-suite.sh if needed.)
PR_ID="${INSTANCE_ID##*-}"
OWNER_REPO="$(echo "$INSTANCE_ID" | sed 's/__/\//' | sed 's/-[0-9]*$//')"
REMOTE_URL="https://github.com/$OWNER_REPO.git"

dexec "git checkout $BASE_COMMIT"

dexec "source /opt/miniconda3/bin/activate testbed && \
       python -m pip install -v --no-use-pep517 --no-build-isolation -e . pytest-cov --verbose"

dexec "mkdir -p /reports"

# Stage helper files at absolute container paths, then make the script runnable.
copy_to_container "$SCRIPT_DIR/run-suite.sh"        /run-suite.sh
copy_to_container "$SCRIPT_DIR/../../parse_junit.py" /parse_junit.py
docker exec "$INSTANCE_ID" chmod +x /run-suite.sh

run_suite() {
  local prefix="$1"
  dexec "source /opt/miniconda3/bin/activate testbed && \
     pytest -rA -vv \
       -o console_output_style=classic \
       --tb=short \
       --cov-config=/testbed/.coveragerc \
       --cov-report=term-missing \
       --junitxml=/reports/${prefix}-junit.xml \
       --log-file=/reports/${prefix}-pytest.log \
       --log-file-level=DEBUG \
       2>&1 | tee /reports/${prefix}-pytest.out"
}

run_suite base_run1
run_suite base_run2
run_suite base_run3

dexec "source /opt/miniconda3/bin/activate testbed && \
   python /parse_junit.py /reports/base_run1-junit.xml /reports/base_run1-junit.json && \
   python /parse_junit.py /reports/base_run2-junit.xml /reports/base_run2-junit.json && \
   python /parse_junit.py /reports/base_run3-junit.xml /reports/base_run3-junit.json"

dexec "diff /reports/base_run1-junit.json /reports/base_run2-junit.json && \
   diff /reports/base_run2-junit.json /reports/base_run3-junit.json && \
   echo 'All three runs have the same test results!' || \
   echo 'Test results differ across runs!'"

# Attach interactively (do this last). winpty is needed for a TTY in Git Bash.
if is_windows && command -v winpty >/dev/null 2>&1; then
  winpty docker exec -it "$INSTANCE_ID" bash -c "cd /testbed && exec bash"
else
  docker exec -it "$INSTANCE_ID" bash -c "cd /testbed && exec bash"
fi