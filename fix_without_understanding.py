#!/usr/bin/env python3
"""Split fl_wrong_resolved cells by whether the *rationale* also failed.

A fl_wrong_resolved cell (fl_apr_align.py ``apr_only``: resolved but line-FL wrong) is
only genuine "fix without understanding" if the agent ALSO misexplained the bug. Joining
the fl_wrong_resolved cells against the reasoning jury's per-cell verdicts splits them into:

    fix_without_understanding  apr_only AND rationale conflicting  (resolved, wrong line, wrong mechanism)
    understood_wrong_line      apr_only AND rationale consistent   (resolved, wrong line, RIGHT mechanism)
    unjudged                   apr_only with no/abstained verdict

The second class is the django__django-14434 pattern: the agent localizes to the use site
instead of the definition site but describes the true mechanism, so line-FL alone
overstates "fix without understanding."

Reads:
    fl-apr-cells[-<tag>].csv       (model, run, instance, quadrant=apr_only)
    reasoning-cells-base.csv       (model, run, instance, binary=consistent|conflicting|'')

Writes:
    fix-without-understanding-cells[-<tag>].csv       one row per apr_only cell + class
    fix-without-understanding-instances[-<tag>].csv   per-instance class counts + FwU reduction

Usage:
    python fix_without_understanding.py
    python fix_without_understanding.py --rule all --min-models 2
    python fix_without_understanding.py --reasoning reasoning-cells-base.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.abspath(__file__))
FWR = "apr_only"  # fl_wrong_resolved quadrant

CLASS = {
    "conflicting": "fix_without_understanding",
    "consistent": "understood_wrong_line",
    "": "unjudged",
}


def reduce_rule(k: int, n: int, rule: str) -> bool:
    if n == 0:
        return False
    if rule == "any":
        return k >= 1
    if rule == "majority":
        return k * 2 > n
    if rule == "all":
        return k == n
    raise ValueError(rule)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--tag", default="", help="read fl-apr-cells-<tag>.csv, write -<tag> outputs")
    p.add_argument("--cells", default=None, help="explicit fl-apr cells CSV (overrides --tag)")
    p.add_argument("--reasoning", default=os.path.join(REPO, "reasoning-cells-base.csv"),
                   help="reasoning jury per-cell CSV to join (default reasoning-cells-base.csv)")
    p.add_argument("--rule", choices=["any", "majority", "all"], default="majority",
                   help="per-model rule for fix_without_understanding flag (default majority)")
    p.add_argument("--min-models", type=int, default=1,
                   help="only list instances FwU-flagged (under --rule) in >= this many models")
    args = p.parse_args(argv)

    suffix = f"-{args.tag}" if args.tag else ""
    cells_path = args.cells or os.path.join(REPO, f"fl-apr-cells{suffix}.csv")
    for path in (cells_path, args.reasoning):
        if not os.path.exists(path):
            sys.exit(f"missing {path}")

    # reasoning verdict per cell
    verdict: dict[tuple[str, str, str], str] = {}
    with open(args.reasoning, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            verdict[(r["model"], r["run"], r["instance"])] = r.get("binary", "") or ""

    # apr_only cells, classified
    cell_rows = []
    # rows[instance][model][run] = class
    rows: dict[str, dict[str, dict[str, str]]] = defaultdict(lambda: defaultdict(dict))
    with open(cells_path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["quadrant"] != FWR:
                continue
            key = (r["model"], r["run"], r["instance"])
            b = verdict.get(key, "")
            cls = CLASS.get(b, "unjudged")
            cell_rows.append({"model": r["model"], "run": r["run"], "instance": r["instance"],
                              "rationale": b or "none", "class": cls})
            rows[r["instance"]][r["model"]][r["run"]] = cls

    cell_rows.sort(key=lambda d: (d["class"] != "fix_without_understanding",
                                  d["instance"], d["model"], d["run"]))
    out_cells = os.path.join(REPO, f"fix-without-understanding-cells{suffix}.csv")
    with open(out_cells, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["model", "run", "instance", "rationale", "class"])
        w.writeheader()
        w.writerows(cell_rows)

    # per-instance aggregation
    records = []
    for inst, per_model in rows.items():
        cells = [c for runs in per_model.values() for c in runs.values()]
        n_fwu = cells.count("fix_without_understanding")
        n_und = cells.count("understood_wrong_line")
        n_unj = cells.count("unjudged")
        flags = {}
        for rule in ("any", "majority", "all"):
            flags[rule] = {
                m for m, runs in per_model.items()
                if reduce_rule(sum(v == "fix_without_understanding" for v in runs.values()),
                               len(runs), rule)
            }
        breakdown = ";".join(
            f"{m}:{sum(v=='fix_without_understanding' for v in runs.values())}fwu/"
            f"{sum(v=='understood_wrong_line' for v in runs.values())}uwl/{len(runs)}"
            for m, runs in sorted(per_model.items())
        )
        records.append({
            "instance": inst,
            "n_apr_only": len(cells),
            "n_fix_without_understanding": n_fwu,
            "n_understood_wrong_line": n_und,
            "n_unjudged": n_unj,
            "n_models_fwu_any": len(flags["any"]),
            "n_models_fwu_majority": len(flags["majority"]),
            "n_models_fwu_all": len(flags["all"]),
            "models_fwu": ";".join(sorted(flags[args.rule])),
            "breakdown": breakdown,
        })

    records.sort(key=lambda d: (d["n_models_fwu_all"], d["n_models_fwu_majority"],
                                d["n_fix_without_understanding"], d["n_models_fwu_any"]),
                 reverse=True)
    selected = [d for d in records
                if d["models_fwu"] and len(d["models_fwu"].split(";")) >= args.min_models]

    out_inst = os.path.join(REPO, f"fix-without-understanding-instances{suffix}.csv")
    cols = ["instance", "n_apr_only", "n_fix_without_understanding", "n_understood_wrong_line",
            "n_unjudged", "n_models_fwu_any", "n_models_fwu_majority", "n_models_fwu_all",
            "models_fwu", "breakdown"]
    with open(out_inst, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(selected)

    # stdout summary
    tot = len(cell_rows)
    n_fwu = sum(1 for c in cell_rows if c["class"] == "fix_without_understanding")
    n_und = sum(1 for c in cell_rows if c["class"] == "understood_wrong_line")
    n_unj = sum(1 for c in cell_rows if c["class"] == "unjudged")
    print(f"fl-apr cells        : {cells_path}")
    print(f"reasoning cells     : {args.reasoning}")
    print(f"apr_only cells      : {tot}")
    print(f"  fix_without_understanding (wrong line + conflicting) : {n_fwu} ({n_fwu/tot:.0%})")
    print(f"  understood_wrong_line     (wrong line + consistent)  : {n_und} ({n_und/tot:.0%})")
    print(f"  unjudged                  (no/abstained verdict)     : {n_unj} ({n_unj/tot:.0%})")
    print(f"cells    -> {out_cells}")
    print(f"instances-> {out_inst}   ({len(selected)} FwU-flagged under '{args.rule}', >= {args.min_models} model)")
    print()
    print("top FIX-WITHOUT-UNDERSTANDING candidates (resolved, wrong line, conflicting rationale):")
    print(f"  {'instance':<38} any maj all  #fwu  #uwl")
    for d in records[:12]:
        if d["n_fix_without_understanding"] == 0:
            continue
        print(f"  {d['instance']:<38} {d['n_models_fwu_any']:>3} {d['n_models_fwu_majority']:>3} "
              f"{d['n_models_fwu_all']:>3} {d['n_fix_without_understanding']:>5} "
              f"{d['n_understood_wrong_line']:>5}")
    print()
    print("top UNDERSTOOD-WRONG-LINE candidates (resolved, wrong line, RIGHT mechanism):")
    uwl = sorted(records, key=lambda d: (d["n_understood_wrong_line"], -d["n_fix_without_understanding"]),
                 reverse=True)
    print(f"  {'instance':<38} #uwl  #fwu  breakdown")
    for d in uwl[:12]:
        if d["n_understood_wrong_line"] == 0:
            continue
        print(f"  {d['instance']:<38} {d['n_understood_wrong_line']:>4} "
              f"{d['n_fix_without_understanding']:>5}  {d['breakdown']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
