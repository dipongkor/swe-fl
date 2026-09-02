#!/usr/bin/env bash

# Django's suite is driven by ./tests/runtests.py, not pytest. base.sh sets
# up /testbed/tests/test_sqlite_junit.py (a settings shim whose TEST_RUNNER
# emits a single JUnit XML); re-create it idempotently here so this script
# is usable standalone.
python -m pip install unittest-xml-reporting >/dev/null

cat > /testbed/tests/test_sqlite_junit.py <<'PY'
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
PY

run_suite() {
    local prefix="$1"

    JUNIT_OUTPUT_FILE=../reports/${prefix}-junit.xml \
    ./tests/runtests.py \
        --verbosity 2 \
        --settings=test_sqlite_junit \
        --parallel 1 \
        2>&1 | tee ../reports/${prefix}-runtests.out
}

rule="$1"

run_suite ${rule}_run1
run_suite ${rule}_run2
run_suite ${rule}_run3

python ../parse_junit.py ../reports/${rule}_run1-junit.xml ../reports/${rule}_run1-junit.json
python ../parse_junit.py ../reports/${rule}_run2-junit.xml ../reports/${rule}_run2-junit.json
python ../parse_junit.py ../reports/${rule}_run3-junit.xml ../reports/${rule}_run3-junit.json

diff ../reports/${rule}_run1-junit.json ../reports/${rule}_run2-junit.json  && \
diff ../reports/${rule}_run2-junit.json ../reports/${rule}_run3-junit.json && \
echo 'All three runs have the same test results!' || \
echo 'Test results differ across runs!'

diff ../reports/base_run1-junit.json ../reports/${rule}_run1-junit.json  && \
echo 'Base run and rule run have the same test results!' || \
echo 'Base run and rule run have different test results!'
