#!/usr/bin/env python3
"""Diff base vs transformed trust-cells to measure robustness, per transform.

Robustness axis (trust axis 4): does a model's behaviour survive a
semantics-controlled transformation of the base instance?  For each transform
and each trust axis (FL, APR, reasoning-aligned, reasoning-consistent,
full-trust), this compares the model on the SAME instances before and after the
transform.

Pairing is per (model, instance): each side is reduced to a boolean by majority
vote over its runs ("reliably correct on base" vs the transformed run(s)), so a
1-run transformed set pairs cleanly against a 3-run base.  The contingency is:

    a = correct on both              b = broke  (base correct -> transformed wrong)
    c = gained (base wrong->correct) d = wrong on both

The headline robustness number is the BREAK RATE b/(a+b): of what the model got
right on the base, how much the transform broke.  Significance is an EXACT
two-sided McNemar (binomial) test - appropriate at panel size ~50 where the
chi-square approximation is unreliable.

Inputs are trust-cells CSVs from trust_axes.py: one base file and one file per
transform (transform name = the part after "trust-cells-").

Usage:
    python robustness_diff.py --base trust-cells-base.csv trust-cells-rename.csv
    python robustness_diff.py --base trust-cells-base.csv trust-cells-*.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.abspath(__file__))


def as_bool(s):
    if s in ("True", "true", "1"):
        return True
    if s in ("False", "false", "0"):
        return False
    return None


# axis -> function(row) -> bool | None  (None = axis undefined for this cell)
def _consistent(row):
    return as_bool(row.get("reasoning_consistent"))


def _aligned4(row):                          # 4-way diagnostic (order-sensitive)
    a = row.get("reasoning_alignment_4way") or ""
    return (a == "aligned") if a else None


def _full(row):
    fl = as_bool(row.get("fl_line_hit"))
    ap = as_bool(row.get("resolved"))
    c = as_bool(row.get("reasoning_consistent"))
    if fl is None or ap is None or c is None:
        return None
    return fl and ap and c


AXES = {
    "FL": lambda r: as_bool(r.get("fl_line_hit")),
    "APR": lambda r: as_bool(r.get("resolved")),
    "reasoning_consistent": _consistent,
    "full_trust": _full,
    "reasoning_aligned_4way": _aligned4,     # diagnostic only
}
AXIS_ORDER = ["FL", "APR", "reasoning_consistent", "full_trust",
              "reasoning_aligned_4way"]


def load_cells(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def majority(vals):
    """Strict majority over the runs where the axis is defined; None if none."""
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return sum(vals) * 2 > len(vals)


def per_instance_axis(rows, axis_fn):
    """{(model, instance): bool|None} by majority vote over that cell's runs."""
    buckets = defaultdict(list)
    for r in rows:
        buckets[(r["model"], r["instance"])].append(axis_fn(r))
    return {k: majority(v) for k, v in buckets.items()}


def mcnemar_exact(b, c):
    """Exact two-sided McNemar (binomial) p-value on the discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) * (0.5 ** n)
    return min(1.0, 2.0 * tail)


def contingency(base_map, tf_map):
    """a,b,c,d over (model,instance) keys defined on BOTH sides."""
    a = b = c = d = 0
    for k, bv in base_map.items():
        tv = tf_map.get(k)
        if bv is None or tv is None:
            continue
        if bv and tv:
            a += 1
        elif bv and not tv:
            b += 1
        elif not bv and tv:
            c += 1
        else:
            d += 1
    return a, b, c, d


def transform_name(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    if stem.startswith("trust-cells-"):
        return stem[len("trust-cells-"):]
    return stem


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", default=os.path.join(REPO, "trust-cells.csv"),
                   help="base trust-cells CSV (default: trust-cells.csv)")
    p.add_argument("transformed", nargs="+",
                   help="one or more transformed trust-cells CSVs")
    p.add_argument("--out", default=os.path.join(REPO, "robustness-diff.csv"))
    p.add_argument("--per-model", action="store_true",
                   help="also print per-model rows (always written to CSV)")
    args = p.parse_args(argv)

    if not os.path.exists(args.base):
        sys.exit(f"missing base {args.base} - run trust_axes.py --tag base")
    base_rows = load_cells(args.base)
    base_models = sorted({r["model"] for r in base_rows})

    # precompute base per-instance booleans per axis, overall and per model
    def maps_for(rows):
        out = {}
        for ax, fn in AXES.items():
            out[ax] = {"OVERALL": per_instance_axis(rows, fn)}
            for m in sorted({r["model"] for r in rows}):
                out[ax][m] = per_instance_axis([r for r in rows if r["model"] == m], fn)
        return out

    base_maps = maps_for(base_rows)
    csv_rows = []

    for tf_path in args.transformed:
        if not os.path.exists(tf_path):
            print(f"skip (missing): {tf_path}")
            continue
        name = transform_name(tf_path)
        tf_rows = load_cells(tf_path)
        tf_maps = maps_for(tf_rows)

        print("=" * 74)
        print(f"TRANSFORM: {name}")
        print("=" * 74)
        scopes = ["OVERALL"] + (base_models if args.per_model else [])
        for scope in ["OVERALL"] + base_models:      # CSV gets all; console gated
            header_printed = False
            for ax in AXIS_ORDER:
                bmap = base_maps[ax].get(scope, {})
                tmap = tf_maps[ax].get(scope, {})
                a, b, c, d = contingency(bmap, tmap)
                n = a + b + c + d
                if not n:
                    continue
                base_rate = (a + b) / n
                tf_rate = (a + c) / n
                delta = tf_rate - base_rate
                break_rate = b / (a + b) if (a + b) else 0.0
                gain_rate = c / (c + d) if (c + d) else 0.0
                pval = mcnemar_exact(b, c)
                csv_rows.append([name, scope, ax, n, a, b, c, d,
                                 f"{base_rate:.3f}", f"{tf_rate:.3f}", f"{delta:+.3f}",
                                 f"{break_rate:.3f}", f"{gain_rate:.3f}", f"{pval:.4f}"])
                if scope in scopes:
                    if not header_printed:
                        tag = "" if scope == "OVERALL" else f"  [{scope}]"
                        print(f"\n  {scope}{tag}")
                        print(f"    {'axis':22}{'n':>5}{'base':>7}{'tf':>7}"
                              f"{'delta':>8}{'broke':>7}{'gain':>6}{'break%':>8}"
                              f"{'McNemar p':>11}")
                        header_printed = True
                    star = " *" if pval < 0.05 else ""
                    print(f"    {ax:22}{n:>5}{base_rate:>7.2f}{tf_rate:>7.2f}"
                          f"{delta:>+8.2f}{b:>7}{c:>6}{break_rate:>8.2f}"
                          f"{pval:>11.4f}{star}")
        print()

    with open(args.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["transform", "scope", "axis", "n", "a_both", "b_broke",
                    "c_gained", "d_neither", "base_rate", "transformed_rate",
                    "delta", "break_rate", "gain_rate", "mcnemar_p"])
        w.writerows(csv_rows)
    print(f"-> {args.out}  ({len(csv_rows)} transform x scope x axis rows)")
    print("  break_rate = b/(a+b): of what worked on base, fraction the transform broke.")
    print("  '*' marks McNemar p < 0.05 (exact binomial on discordant pairs).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
