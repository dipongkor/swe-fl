#!/usr/bin/env python3
"""Fold baseline (resolved re-check) + strengthened-differential verdicts into the audit CSV.

Reads:
  patch-diff/reports/*.patchdiff-baseline.json   (standard-harness resolved status per run)
  patch-diff/strengthen-results.json             (whole-test-file gold-vs-agent diff)
Writes:
  fix-without-understanding-audit-tested.csv     (audit CSV + resolved_recheck, strengthen_verdict)
"""
import csv, glob, json, os
REPO=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); os.chdir(REPO)

# resolved re-check: map (model_name_or_path, instance) -> resolved bool
resolved={}
for rep in glob.glob("patch-diff/reports/*.patchdiff-baseline.json"):
    d=json.load(open(rep))
    mn=os.path.basename(rep).split(".patchdiff-baseline.json")[0]  # e.g. agent-claude-opus-run3 / gold
    for iid in d.get("resolved_ids",[]): resolved[(mn,iid)]="resolved"
    for iid in d.get("unresolved_ids",[]): resolved[(mn,iid)]="UNRESOLVED"

strengthen=json.load(open("patch-diff/strengthen-results.json")) if os.path.exists("patch-diff/strengthen-results.json") else {}

def recheck(model,run,inst):
    return resolved.get((f"agent-{model}-{run}",inst),"") or resolved.get((f"agent-{model}-{run}".replace('/','__'),inst),"")
def strv(model,run,inst):
    r=strengthen.get(inst,{})
    arm=r.get("arms",{}).get(f"agent:{model}-{run}")
    if not arm: return ""
    if arm.get("equivalent"): return "equivalent_to_gold"
    return "DIVERGES:"+",".join(arm.get("regressions",[])[:3])

rows=list(csv.DictReader(open("fix-without-understanding-audit.csv")))
cols=rows[0].keys() if rows else []
out_cols=list(cols)+["resolved_recheck","strengthen_verdict"]
for r in rows:
    r["resolved_recheck"]=recheck(r["model"],r["run"],r["instance"])
    r["strengthen_verdict"]=strv(r["model"],r["run"],r["instance"])
with open("fix-without-understanding-audit-tested.csv","w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=out_cols); w.writeheader(); w.writerows(rows)
print("wrote fix-without-understanding-audit-tested.csv")
from collections import Counter
print("resolved_recheck:",dict(Counter(r["resolved_recheck"] for r in rows)))
print("strengthen_verdict:",dict(Counter(r["strengthen_verdict"].split(':')[0] for r in rows)))
