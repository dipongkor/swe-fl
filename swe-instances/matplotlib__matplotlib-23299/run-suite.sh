run_suite() {

    local prefix="$1"
  
    pytest -rA -vv \
    -o console_output_style=classic \
    --tb=short \
    --cov-config=/testbed/.coveragerc \
    --cov-report=term-missing \
    --junitxml=../reports/${prefix}-junit.xml \
    --log-file=../reports/${prefix}-pytest.log \
    --log-file-level=DEBUG \
    2>&1 | tee ../reports/${prefix}-pytest.out
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