import pandas as pd
from datasets import load_dataset
from swebench.harness.test_spec.test_spec import make_test_spec
import re
import os

def count_unique_files(patch_text):
    # Match 'diff --git a/<path> b/<path>' headers
    files = re.findall(r'^diff --git a/(.+?) b/.+$', patch_text, re.MULTILINE)
    return len(set(files))

ds = load_dataset('SWE-bench/SWE-bench_Verified', split='test')

df = ds.to_pandas()

with open('pilot-instances.txt', 'r') as f:
    pilot_instances = [line.strip() for line in f]

for index, row in df.iterrows():
    instance_id = row['instance_id']
    if instance_id not in pilot_instances:
        continue
    patch = row['patch']
    test_patch = row['test_patch']
    problem_statement = row['problem_statement']
    FAIL_TO_PASS = row['FAIL_TO_PASS']
    PASS_TO_PASS = row['PASS_TO_PASS']
    
    environment_setup_commit = row['environment_setup_commit']
    
    base_commit = row['base_commit']
    
    os.mkdir(f'swe-instances/{instance_id}')
    
    matches = [x for x in ds if x['instance_id'] == instance_id]
    
    spec = make_test_spec(matches[0])
    
    with open(f'swe-instances/{instance_id}/eval_script.sh', 'w') as f:
        f.write(spec.eval_script)
    
    with open(f'swe-instances/{instance_id}/setup_env_script.sh', 'w') as f:
        f.write(spec.setup_env_script)
    
    with open(f'swe-instances/{instance_id}/install_repo_script.sh', 'w') as f:
        f.write(spec.install_repo_script)
        
    with open(f'swe-instances/{instance_id}/patch.diff', 'w') as f:
        f.write(patch)
    
    with open(f'swe-instances/{instance_id}/test_patch.diff', 'w') as f:
        f.write(test_patch)
    
    with open(f'swe-instances/{instance_id}/problem_statement.txt', 'w') as f:
        f.write(problem_statement)
        
    with open(f'swe-instances/{instance_id}/fail_to_pass.json', 'w') as f:
        f.write(FAIL_TO_PASS)
    
    with open(f'swe-instances/{instance_id}/pass_to_pass.json', 'w') as f:
        f.write(PASS_TO_PASS)
    
    with open(f'swe-instances/{instance_id}/environment_setup_commit.txt', 'w') as f:
        f.write(environment_setup_commit)
    
    with open(f'swe-instances/{instance_id}/base_commit.txt', 'w') as f:
        f.write(base_commit)