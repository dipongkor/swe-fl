#!/usr/bin/env python3
"""Instance-level alignment between fault localization (FL) and repair (APR).

FL correctness = the model's stated localization hits the ground truth (line
granularity by default, reusing fl_eval's matching).  APR success = the
generated patch passes the SWE-bench evaluation (report.json ``resolved``).

For every (model, run, instance) cell where BOTH signals are defined we build a
2x2 contingency and report, overall and per model:

    P(resolved | FL correct)  vs  P(resolved | FL wrong)      (+ lift)
    P(FL correct | resolved)
    raw agreement
    phi / Matthews correlation

Weak alignment means FL and APR are complementary (neither is a proxy for the
other).  The off-diagonal cells are the trust-relevant ones:
    apr_only  = patched WITHOUT correctly localizing ("fix without understanding")
    fl_only   = localized but did NOT repair

Run it on the base set and again on a transformed set (``--tag base`` /
``--tag transformed``) to measure how robustness perturbations move these cells.

Usage:
    python fl_apr_align.py
    python fl_apr_align.py --granularity file --tag base
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys

import fl_eval as F

REPO = os.path.dirname(os.path.abspath(__file__))

QUADRANT = {(True, True): "both", (True, False): "fl_only",
            (False, True): "apr_only", (False, False): "neither"}

OUT_COLUMNS = ["scope", "n",
               "fl_correct_resolved", "fl_correct_unresolved",
               "fl_wrong_resolved", "fl_wrong_unresolved",
               "p_resolved_if_fl_correct", "p_resolved_if_fl_wrong", "lift",
               "p_fl_correct_if_resolved", "agreement", "phi"]


def stats(a: int, b: int, c: int, d: int) -> dict:
    """a=correct&resolved b=correct&~res c=wrong&resolved d=wrong&~res."""
    n = a + b + c + d
    hit, nohit, res = a + b, c + d, a + c
    p_res_hit = a / hit if hit else 0.0
    p_res_nohit = c / nohit if nohit else 0.0
    p_hit_res = a / res if res else 0.0
    agree = (a + d) / n if n else 0.0
    denom = math.sqrt((a + b) * (c + d) * (a + c) * (b + d))
    phi = (a * d - b * c) / denom if denom else 0.0
    return {"n": n, "a": a, "b": b, "c": c, "d": d,
            "p_res_hit": p_res_hit, "p_res_nohit": p_res_nohit,
            "lift": p_res_hit - p_res_nohit, "p_hit_res": p_hit_res,
            "agree": agree, "phi": phi}


def row(scope: str, s: dict) -> list:
    return [scope, s["n"], s["a"], s["b"], s["c"], s["d"],
            f"{s['p_res_hit']:.3f}", f"{s['p_res_nohit']:.3f}", f"{s['lift']:+.3f}",
            f"{s['p_hit_res']:.3f}", f"{s['agree']:.3f}", f"{s['phi']:.3f}"]


def show(scope: str, s: dict) -> None:
    if not s["n"]:
        return
    print(f"\n{scope}  (n={s['n']} cells)")
    print(f"  both (FL correct & resolved) = {s['a']:>4}   "
          f"fl_only (correct, NOT resolved) = {s['b']:>4}")
    print(f"  apr_only (WRONG, resolved)   = {s['c']:>4}   "
          f"neither                          = {s['d']:>4}")
    print(f"  P(resolved | FL correct) = {s['p_res_hit']:.3f}")
    print(f"  P(resolved | FL wrong)   = {s['p_res_nohit']:.3f}   "
          f"(lift = {s['lift']:+.3f})")
    print(f"  P(FL correct | resolved) = {s['p_hit_res']:.3f}")
    print(f"  raw agreement            = {s['agree']:.3f}")
    print(f"  phi / MCC                = {s['phi']:.3f}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--agent-fl", default=F.DEFAULT_AGENT_FL)
    p.add_argument("--gt-dir", default=F.DEFAULT_GT_DIR)
    p.add_argument("--csv", default=F.DEFAULT_CSV)
    p.add_argument("--repos", default=F.DEFAULT_REPOS)
    p.add_argument("--granularity", choices=["file", "line", "stmt"],
                   default="line", help="FL-correct definition (default: line)")
    p.add_argument("--tag", default="",
                   help="label for outputs, e.g. base / transformed")
    args = p.parse_args(argv)

    hit_key = {"file": "file_hit", "line": "line_hit", "stmt": "stmt_hit"}[args.granularity]
    suffix = f"-{args.tag}" if args.tag else ""
    out_summary = os.path.join(REPO, f"fl-apr-align{suffix}.csv")
    out_cells = os.path.join(REPO, f"fl-apr-cells{suffix}.csv")

    gt = F.load_ground_truth(args.gt_dir)
    commits = F.commit_map(args.csv)
    instances = sorted(gt)
    runs = F.discover_runs(args.agent_fl)
    if not runs:
        sys.exit(f"no swebench-fl-*-run* dirs under {args.agent_fl}")
    src_cache, spans_cache = {}, {}

    # counts[scope] = [a, b, c, d]
    overall = [0, 0, 0, 0]
    per_model: dict[str, list[int]] = {}
    cells = []
    n_total = n_used = 0

    for m, r, d in runs:
        pm = per_model.setdefault(m, [0, 0, 0, 0])
        for iid in instances:
            n_total += 1
            short = iid.split("__", 1)[-1]
            pred_locs, _, status = F.load_prediction(d, short)
            resolved = F.load_resolved(d, short)
            if status != "ok" or resolved is None:
                continue  # need both signals defined
            n_used += 1
            fl = F.match_locations(pred_locs, gt[iid], iid, commits.get(iid, ""),
                                   args.repos, src_cache, spans_cache)[hit_key]
            idx = 0 if (fl and resolved) else 1 if (fl and not resolved) \
                else 2 if (not fl and resolved) else 3
            overall[idx] += 1
            pm[idx] += 1
            cells.append({"model": m, "run": f"run{r}", "instance": iid,
                          "fl_correct": fl, "resolved": resolved,
                          "quadrant": QUADRANT[(fl, resolved)]})

    print(f"FL-APR alignment  (granularity={args.granularity}"
          f"{', tag='+args.tag if args.tag else ''})")
    print(f"cells with both signals defined: {n_used}/{n_total} "
          f"({n_total - n_used} skipped: no localization or no report)")

    summary_rows = []
    s = stats(*overall)
    show("OVERALL", s)
    summary_rows.append(row("OVERALL", s))
    for m in sorted(per_model):
        sm = stats(*per_model[m])
        show(m, sm)
        summary_rows.append(row(m, sm))

    with open(out_summary, "w", newline="") as f:
        w = csv.writer(f); w.writerow(OUT_COLUMNS); w.writerows(summary_rows)
    with open(out_cells, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["model", "run", "instance",
                                          "fl_correct", "resolved", "quadrant"])
        w.writeheader(); w.writerows(cells)

    print(f"\nsummary -> {out_summary}")
    print(f"cells   -> {out_cells}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
