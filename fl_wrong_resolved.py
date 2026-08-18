#!/usr/bin/env python3
"""Identify fl_wrong_resolved instances (``fix without understanding``) across models and runs.

An fl_wrong_resolved cell is a (model, run, instance) where the agent's patch passes
the tests (``resolved``) but its fault localization misses the ground truth
(``fl_correct`` is False).  In fl_apr_align.py's contingency this is the ``apr_only``
quadrant.  FL-correctness granularity (file/line/stmt) is fixed when fl-apr-cells.csv
is generated (line by default); this script only reads that table.

Reads:
    fl-apr-cells[-<tag>].csv   (model, run, instance, fl_correct, resolved, quadrant)

Writes:
    fl-wrong-resolved-cells[-<tag>].csv      one row per fl_wrong_resolved cell
    fl-wrong-resolved-instances[-<tag>].csv  per-instance aggregation across models/runs

Per instance, a model "flags" the instance under a reduction rule over that model's
runs present:
    any       >= 1 run is fl_wrong_resolved
    majority  strict majority of runs are fl_wrong_resolved
    all       every run present is fl_wrong_resolved

Usage:
    python fl_wrong_resolved.py
    python fl_wrong_resolved.py --tag base
    python fl_wrong_resolved.py --rule all --min-models 2      # strongest candidates
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.abspath(__file__))
FWR = "apr_only"  # fl_wrong_resolved quadrant in fl-apr-cells.csv


def reduce_rule(n_fwr: int, n_runs: int, rule: str) -> bool:
    """Does a model flag an instance, given n_fwr fl_wrong_resolved runs of n_runs present?"""
    if n_runs == 0:
        return False
    if rule == "any":
        return n_fwr >= 1
    if rule == "majority":
        return n_fwr * 2 > n_runs
    if rule == "all":
        return n_fwr == n_runs
    raise ValueError(rule)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--tag", default="", help="read fl-apr-cells-<tag>.csv, write -<tag> outputs")
    p.add_argument("--cells", default=None, help="explicit cells CSV (overrides --tag)")
    p.add_argument("--rule", choices=["any", "majority", "all"], default="majority",
                   help="per-model rule for the 'models'/'flagged' columns (default majority)")
    p.add_argument("--min-models", type=int, default=1,
                   help="only list instances flagged (under --rule) in >= this many models")
    args = p.parse_args(argv)

    suffix = f"-{args.tag}" if args.tag else ""
    cells_path = args.cells or os.path.join(REPO, f"fl-apr-cells{suffix}.csv")
    if not os.path.exists(cells_path):
        sys.exit(f"missing {cells_path} - run fl_apr_align.py first")

    # rows[instance][model] = {run: is_fwr}
    rows: dict[str, dict[str, dict[str, bool]]] = defaultdict(lambda: defaultdict(dict))
    fwr_cells: list[dict[str, str]] = []
    with open(cells_path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            inst, model, run = r["instance"], r["model"], r["run"]
            is_fwr = (r["quadrant"] == FWR)
            rows[inst][model][run] = is_fwr
            if is_fwr:
                fwr_cells.append(r)

    # --- per-cell output ---
    out_cells = os.path.join(REPO, f"fl-wrong-resolved-cells{suffix}.csv")
    fwr_cells.sort(key=lambda r: (r["instance"], r["model"], r["run"]))
    with open(out_cells, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["model", "run", "instance"])
        for r in fwr_cells:
            w.writerow([r["model"], r["run"], r["instance"]])

    # --- per-instance aggregation ---
    records = []
    for inst, per_model in rows.items():
        n_fwr_cells = sum(v for runs in per_model.values() for v in runs.values())
        if n_fwr_cells == 0:
            continue
        n_cells_total = sum(len(runs) for runs in per_model.values())
        flags = {}  # rule -> set(models)
        for rule in ("any", "majority", "all"):
            flags[rule] = {
                m for m, runs in per_model.items()
                if reduce_rule(sum(runs.values()), len(runs), rule)
            }
        breakdown = ";".join(
            f"{m}:{sum(runs.values())}/{len(runs)}"
            for m, runs in sorted(per_model.items())
            if any(runs.values())
        )
        records.append({
            "instance": inst,
            "n_fwr_cells": n_fwr_cells,
            "n_cells_total": n_cells_total,
            "n_models_any": len(flags["any"]),
            "n_models_majority": len(flags["majority"]),
            "n_models_all": len(flags["all"]),
            "models_flagged": ";".join(sorted(flags[args.rule])),
            "breakdown": breakdown,
        })

    # strongest, most reproducible candidates first
    records.sort(key=lambda d: (d["n_models_all"], d["n_models_majority"],
                                d["n_fwr_cells"], d["n_models_any"]), reverse=True)
    selected = [d for d in records if len(d["models_flagged"].split(";")) >= args.min_models
                and d["models_flagged"]]

    out_inst = os.path.join(REPO, f"fl-wrong-resolved-instances{suffix}.csv")
    cols = ["instance", "n_fwr_cells", "n_cells_total", "n_models_any",
            "n_models_majority", "n_models_all", "models_flagged", "breakdown"]
    with open(out_inst, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(selected)

    # --- stdout summary ---
    print(f"cells source        : {cells_path}")
    print(f"fl_wrong_resolved cells (apr_only) : {len(fwr_cells)}")
    print(f"distinct instances (>=1 fwr cell)  : {len(records)}")
    print(f"instances flagged under '{args.rule}' in >= {args.min_models} model(s): {len(selected)}")
    print(f"cells    -> {out_cells}")
    print(f"instances-> {out_inst}")
    print()
    print(f"top candidates (most reproducible fix-without-understanding):")
    print(f"  {'instance':<40} any maj all  cells  breakdown")
    for d in records[:15]:
        print(f"  {d['instance']:<40} "
              f"{d['n_models_any']:>3} {d['n_models_majority']:>3} {d['n_models_all']:>3} "
              f"{d['n_fwr_cells']:>5}  {d['breakdown']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
