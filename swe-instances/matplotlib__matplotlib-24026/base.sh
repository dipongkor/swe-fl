INSTANCE_ID="matplotlib__matplotlib-24026"
BASE_COMMIT="14c96b510ebeba40f573e512299b1976f35b620e"

DOCKER_IMAGE="swebench/sweb.eval.x86_64.$(echo $INSTANCE_ID | sed 's/__/_1776_/g' | tr '[:upper:]' '[:lower:]'):latest"

docker run -dit --name $INSTANCE_ID $DOCKER_IMAGE sleep infinity

PR_ID=$(echo $INSTANCE_ID | rev | cut -d'-' -f1 | rev)
OWNER_REPO=$(echo $INSTANCE_ID | sed 's/__/\//' | sed 's/-[0-9]*$//')
REMOTE_URL="https://github.com/$OWNER_REPO.git"

docker exec -w /testbed $INSTANCE_ID git checkout $BASE_COMMIT

docker exec -w /testbed $INSTANCE_ID bash -c \
  "source /opt/miniconda3/bin/activate testbed && python -m pip install -e . pytest-cov --verbose"

docker exec -w /testbed $INSTANCE_ID bash -c "mkdir -p ../reports"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
docker cp "$SCRIPT_DIR/run-suite.sh" $INSTANCE_ID:../run-suite.sh
docker chmod +x ../run-suite.sh
docker cp "$SCRIPT_DIR/../../parse_junit.py" $INSTANCE_ID:../parse_junit.py

run_suite() {
  local prefix="$1"
  docker exec -w /testbed $INSTANCE_ID bash -c \
    "source /opt/miniconda3/bin/activate testbed && \
     pytest -rA -vv \
       -o console_output_style=classic \
       --tb=short \
       --cov-config=/testbed/.coveragerc \
       --cov-report=term-missing \
       --junitxml=../reports/${prefix}-junit.xml \
       --log-file=../reports/${prefix}-pytest.log \
       --log-file-level=DEBUG \
       2>&1 | tee ../reports/${prefix}-pytest.out"
}

run_suite base_run1
run_suite base_run2
run_suite base_run3

docker exec -w /testbed $INSTANCE_ID bash -c \
  "source /opt/miniconda3/bin/activate testbed && python ../parse_junit.py ../reports/base_run1-junit.xml ../reports/base_run1-junit.json && python ../parse_junit.py ../reports/base_run2-junit.xml ../reports/base_run2-junit.json && python ../parse_junit.py ../reports/base_run3-junit.xml ../reports/base_run3-junit.json"

docker exec -w /testbed $INSTANCE_ID bash -c \
  "diff ../reports/base_run1-junit.json ../reports/base_run2-junit.json  && \
   diff ../reports/base_run2-junit.json ../reports/base_run3-junit.json && \
   echo 'All three runs have the same test results!' || \
   echo 'Test results differ across runs!'"

# Attach interactively (do this last)
docker exec -it -w /testbed $INSTANCE_ID /bin/bash
