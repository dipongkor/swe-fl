INSTANCE_ID="matplotlib__matplotlib-26208"
BASE_COMMIT="f0f133943d3e4f1e2e665291fe1c8f658a84cc09"

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

run_suite base

# # Copy reports out to host
# HOST_REPORTS=./test-reports
# mkdir -p $HOST_REPORTS
# docker cp $INSTANCE_ID:../reports/. $HOST_REPORTS/
# echo "Reports saved to $HOST_REPORTS/"

# Attach interactively (do this last)
docker exec -it -w /testbed $INSTANCE_ID /bin/bash
