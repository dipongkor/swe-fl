#!/usr/bin/env python3
"""Aggregate the harness reports into a per-cell resolved table + tally.

Reads:  reports/*.<run_id>.json   (whatever run_id you used; default 'recheck')
        preds/*.jsonl             (to know the full set of 214 agent cells + gold)
Writes: recheck-summary.csv       (one row per (model_name, instance) with resolved status)
Prints: a compact tally to share back.
"""
import csv, glob, json, os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 1) the full expected set of cells from the prediction files
cells = []               # (model_name_or_path, instance_id)
for pf in sorted(glob.glob("preds/*.jsonl")):
    for line in open(pf):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        cells.append((d["model_name_or_path"], d["instance_id"]))

# 2) resolved status from reports
status = {}              # (model_name, instance) -> resolved|UNRESOLVED|ERROR|incomplete
report_files = glob.glob("reports/*.json")
if not report_files:
    sys.exit("No reports/*.json found -- run run_all.sh first.")
for rf in report_files:
    d = json.load(open(rf))
    mn = os.path.basename(rf).rsplit(".", 2)[0]     # strip .<run_id>.json
    for iid in d.get("resolved_ids", []):    status[(mn, iid)] = "resolved"
    for iid in d.get("unresolved_ids", []):  status[(mn, iid)] = "UNRESOLVED"
    for iid in d.get("error_ids", []):       status[(mn, iid)] = "ERROR"

# 3) fallback to per-instance logs (authoritative if a report was overwritten/partial)
import re
def from_log(mn, iid):
    val = None
    for lg in glob.glob(f"logs/run_evaluation/*/{mn}/{iid}/run_instance.log"):
        m = re.findall(r"resolved:\s*(True|False)", open(lg, errors="ignore").read())
        if m:
            val = "resolved" if m[-1] == "True" else "UNRESOLVED"
    return val

rows = []
from collections import Counter
tally = Counter()
for mn, iid in cells:
    s = status.get((mn, iid)) or from_log(mn, iid) or "MISSING"
    tally[s] += 1
    rows.append({"model_name": mn, "instance_id": iid, "resolved": s})

# gold rows separately for the control tally
agent_rows = [r for r in rows if r["model_name"] != "gold"]
gold_rows  = [r for r in rows if r["model_name"] == "gold"]

with open("recheck-summary.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["model_name", "instance_id", "resolved"])
    w.writeheader(); w.writerows(rows)

print("=== fl_wrong_resolved recheck ===")
print(f"agent cells : {len(agent_rows)}")
print("  " + "  ".join(f"{k}={v}" for k, v in Counter(r['resolved'] for r in agent_rows).most_common()))
print(f"gold cells  : {len(gold_rows)}")
print("  " + "  ".join(f"{k}={v}" for k, v in Counter(r['resolved'] for r in gold_rows).most_common()))
bad = [r for r in agent_rows if r["resolved"] not in ("resolved",)]
if bad:
    print("\nNON-RESOLVED / PROBLEM CELLS (share these):")
    for r in bad:
        print(f"  {r['resolved']:<11} {r['model_name']:<26} {r['instance_id']}")
print("\nwrote recheck-summary.csv  (share this file + the tally above)")
