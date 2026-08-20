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

INSTANCE_ID="django__django-15503"
BASE_COMMIT="859a87d873ce7152af73ab851653b4e1c3ffea4c"
DOCKER="/Users/es256599/.local/bin/docker"

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
    "$DOCKER" cp "$1" "$INSTANCE_ID:$2"
  fi
}

# Run a command string inside /testbed. We `cd` inside `bash -c` instead of
# using `-w /testbed` so the container path is never seen (or mangled) by the
# host shell. Quoting also means MSYS leaves the inner /paths alone.
dexec() {  # $* = command to run in /testbed
  "$DOCKER" exec "$INSTANCE_ID" bash -c "cd /testbed && $*"
}
# ----------------------------------------------------------------------------

DOCKER_IMAGE="swebench/sweb.eval.x86_64.$(echo "$INSTANCE_ID" | sed 's/__/_1776_/g' | tr '[:upper:]' '[:lower:]'):latest"

# Fresh container every run (avoids "name already in use").
"$DOCKER" rm -f "$INSTANCE_ID" >/dev/null 2>&1 || true
"$DOCKER" run -dit --platform linux/amd64 --name "$INSTANCE_ID" "$DOCKER_IMAGE" sleep infinity

# (Derived values kept for reference / use by run-suite.sh if needed.)
PR_ID="${INSTANCE_ID##*-}"
OWNER_REPO="$(echo "$INSTANCE_ID" | sed 's/__/\//' | sed 's/-[0-9]*$//')"
REMOTE_URL="https://github.com/$OWNER_REPO.git"

dexec "git checkout $BASE_COMMIT"

dexec "source /opt/miniconda3/bin/activate testbed && \
       python -m pip install -e ."

dexec "mkdir -p /reports"

# Stage helper files at absolute container paths, then make the script runnable.
copy_to_container "$SCRIPT_DIR/run-suite.sh"        /run-suite.sh
copy_to_container "$SCRIPT_DIR/../../parse_junit.py" /parse_junit.py
"$DOCKER" exec "$INSTANCE_ID" chmod +x /run-suite.sh

# Django doesn't use pytest — its suite is driven by ./tests/runtests.py
# (a thin wrapper around unittest's DiscoverRunner). runtests.py has no
# --testrunner CLI flag, so we point TEST_RUNNER at our own DiscoverRunner
# subclass via a settings shim that inherits everything from test_sqlite.
# The runner wraps unittest-xml-reporting's XMLTestRunner with a single
# output file (writing to a file object — passing a directory would emit
# one XML per test class, which the diff comparison can't consume).
dexec "source /opt/miniconda3/bin/activate testbed && \
       python -m pip install unittest-xml-reporting"

dexec "cat > /testbed/tests/test_sqlite_junit.py <<'PY'
from test_sqlite import *
import os
from django.test.runner import DiscoverRunner

class _SingleFileXMLRunner(DiscoverRunner):
    def run_suite(self, suite, **kwargs):
        import xmlrunner
        output_file = os.environ['JUNIT_OUTPUT_FILE']
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'wb') as f:
            runner = xmlrunner.XMLTestRunner(
                output=f, verbosity=self.verbosity,
                failfast=self.failfast,
                buffer=getattr(self, 'buffer', False),
            )
            return runner.run(suite)

TEST_RUNNER = 'test_sqlite_junit._SingleFileXMLRunner'
PY"

run_suite() {
  local prefix="$1"
  dexec "source /opt/miniconda3/bin/activate testbed && \
     JUNIT_OUTPUT_FILE=/reports/${prefix}-junit.xml \
     ./tests/runtests.py \
       --verbosity 2 \
       --settings=test_sqlite_junit \
       --parallel 1 \
       2>&1 | tee /reports/${prefix}-runtests.out"
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
  "$DOCKER" exec -it "$INSTANCE_ID" bash -c "cd /testbed && exec bash"
fi