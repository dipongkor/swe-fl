#!/usr/bin/env python3
"""Strengthened differential testing for the 23 conflicting cells.

For each (instance, agent patch) we compare the agent's "resolved" patch against the gold
patch on a *superset* of the curated SWE-bench tests: we run the ENTIRE test file(s) that
gold's ``test_patch`` touches (all node-ids in them), not just the FAIL_TO_PASS/PASS_TO_PASS
subset. A test that passes under the gold-patched repo but fails under the agent-patched
repo is a strengthened-test divergence -- behaviour the curated subset did not catch.

Procedure per instance (inside the x86_64 eval image, emulated on Apple Silicon):
  1. checkout base_commit (clean)
  2. apply gold's test_patch (adds the reproduction tests) to BOTH arms
  3. arm=gold : apply gold code patch;  arm=agent : apply the agent code patch
  4. run pytest on the whole affected test file(s); collect pass/fail per node-id
  5. diff: nodes passing under gold but not under agent  ->  divergence

Writes patch-diff/strengthen-results.json.

Run AFTER images are cached (patch-diff/run_baseline.sh). Requires Docker + emulation.
"""
from __future__ import annotations
import json, os, re, subprocess, sys, glob
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
PLATFORM = "linux/amd64"

def img(inst):
    org, rest = inst.split("__")
    return f"swebench/sweb.eval.x86_64.{org}_1776_{rest}:latest"

def sh(cid, cmd):
    return subprocess.run(["docker","exec",cid,"bash","-lc",cmd],
                          capture_output=True, text=True)

def test_files_of(test_patch):
    return sorted(set(re.findall(r'^\+\+\+ b/(\S+)', test_patch, re.M)) |
                  set(re.findall(r'^diff --git a/(\S+) b/', test_patch, re.M)))

def agent_patch(inst, model, run):
    base=f'agent-fl/swebench-fl-{model}-{run}'
    for pred in glob.glob(f'{base}/*/preds.json'):
        try: d=json.load(open(pred))
        except: continue
        for k,v in (d.items() if isinstance(d,dict) else []):
            if isinstance(v,dict) and (inst in k or v.get('instance_id')==inst):
                p=v.get('model_patch') or v.get('patch')
                if p: return p
    for tj in glob.glob(f'{base}/*/{inst}/{inst}.traj.json'):
        s=(json.load(open(tj)).get('info') or {}).get('submission') or ''
        if s: return s
    return None

def parse_pytest(out):
    """node-id -> PASSED/FAILED/ERROR from pytest -v output."""
    res={}
    for m in re.finditer(r'^(\S+::\S+)\s+(PASSED|FAILED|ERROR|SKIPPED)', out, re.M):
        res[m.group(1)]=m.group(2)
    for m in re.finditer(r'^(PASSED|FAILED|ERROR|SKIPPED)\s+(\S+::\S+)', out, re.M):
        res[m.group(2)]=m.group(1)
    return res

def run_arm(cid, code_patch, test_patch, test_files, conda="testbed"):
    act=f"source /opt/miniconda3/etc/profile.d/conda.sh && conda activate {conda}"
    sh(cid, "cd /testbed && git checkout -- . && git clean -fdq")
    # write patches
    subprocess.run(["bash","-lc",f"printf '%s' {json.dumps(test_patch)!r} > /tmp/t.patch"],
                   capture_output=True, text=True)  # placeholder; patches copied via docker cp below
    return None  # (driver copies patches; see main)

def main():
    import csv
    cells=[(r['instance'],r['model'],r['run'])
           for r in csv.DictReader(open('fix-without-understanding-cells.csv'))
           if r['class']=='fix_without_understanding']
    from datasets import load_dataset
    insts=sorted({c[0] for c in cells})
    ds={r['instance_id']:r for r in load_dataset('SWE-bench/SWE-bench_Verified',split='test')
        if r['instance_id'] in set(insts)}
    results={}
    for inst in insts:
        row=ds[inst]; tp=row['test_patch']; tfiles=test_files_of(tp)
        gold=open(f'ground-truth-patches/{inst}.patch').read()
        image=img(inst)
        cid=subprocess.run(["docker","run","-d","--platform",PLATFORM,image,"sleep","3600"],
                           capture_output=True,text=True).stdout.strip()
        if not cid:
            results[inst]={"error":"container start failed"}; continue
        try:
            # stage patches into container
            for name,content in [("gold_code",gold),("test",tp)]:
                open(f'/tmp/{inst}.{name}.patch','w').write(content)
                subprocess.run(["docker","cp",f'/tmp/{inst}.{name}.patch',f'{cid}:/tmp/{name}.patch'],
                               capture_output=True)
            act="source /opt/miniconda3/etc/profile.d/conda.sh && conda activate testbed"
            files=" ".join(tfiles)
            arms={}
            # gold arm
            for (model,run) in [("__GOLD__","")]+[ (m,r) for (i,m,r) in cells if i==inst]:
                if model=="__GOLD__":
                    codepatch=gold; label="gold"
                else:
                    codepatch=agent_patch(inst,model,run); label=f"agent:{model}-{run}"
                    if not codepatch: continue
                open(f'/tmp/{inst}.code.patch','w').write(codepatch)
                subprocess.run(["docker","cp",f'/tmp/{inst}.code.patch',f'{cid}:/tmp/code.patch'],capture_output=True)
                sh(cid,"cd /testbed && git checkout -- . && git clean -fdq")
                ap=sh(cid,"cd /testbed && git apply /tmp/test.patch && git apply /tmp/code.patch && echo APPLIED_OK")
                if "APPLIED_OK" not in ap.stdout:
                    arms[label]={"apply_error":(ap.stderr or ap.stdout)[-400:]}; continue
                pt=sh(cid,f"cd /testbed && {act} && python -m pytest -p no:cacheprovider -q -v {files} 2>&1 | tail -400")
                arms[label]=parse_pytest(pt.stdout)
            # diff each agent arm vs gold
            goldres=arms.get("gold",{})
            gpass={k for k,v in goldres.items() if v=="PASSED"}
            diffs={}
            for label,res in arms.items():
                if label=="gold" or "apply_error" in res: continue
                apass={k for k,v in res.items() if v=="PASSED"}
                regressions=sorted(gpass-apass)   # passed under gold, not under agent
                diffs[label]={"n_tests":len(res),"n_pass_gold":len(gpass),"n_pass_agent":len(apass),
                              "regressions":regressions,"equivalent":not regressions}
            results[inst]={"test_files":tfiles,"gold_pass":len(gpass),"arms":diffs}
            print(f"{inst}: gold_pass={len(gpass)}  " +
                  "; ".join(f"{l}:{'EQUIV' if d['equivalent'] else 'DIVERGES '+str(d['regressions'][:3])}"
                            for l,d in diffs.items()))
        finally:
            subprocess.run(["docker","rm","-f",cid],capture_output=True)
    json.dump(results, open("patch-diff/strengthen-results.json","w"), indent=2)
    print("\nwrote patch-diff/strengthen-results.json")

if __name__=="__main__":
    main()
