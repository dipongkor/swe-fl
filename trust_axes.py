#!/usr/bin/env python3
"""Join the three trust axes into one per-cell table: FL x APR x reasoning.

Merges (by model, run, instance):
  * fl-apr-cells[-tag].csv   FL correctness (line-hit) + APR (resolved), from fl_apr_align.py
  * reasoning-cells[-tag].csv reasoning alignment vs ground truth, from reasoning_eval.py

Writes trust-cells[-tag].csv (one row per cell that appears in either source, with
a compact trust profile) and prints the cross-axis relationships that a bare
per-axis rate cannot show:

  * full-trust rate           FL correct AND resolved AND reasoning aligned
  * fix-without-understanding  resolved but FL wrong, or resolved but reasoning
                               not aligned - the trust red flag
  * P(reasoning aligned | FL correct) vs | FL wrong
  * P(reasoning aligned | resolved)    vs | unresolved

Because the axes are only weakly coupled, this joint view is what the robustness
experiment should diff: run with --tag base and --tag transformed, then compare
trust-cells-base.csv against trust-cells-transformed.csv.

Usage:
    python trust_axes.py
    python trust_axes.py --tag base
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.abspath(__file__))


def load_csv(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def as_bool(s):
    if s in ("True", "true", "1"):
        return True
    if s in ("False", "false", "0"):
        return False
    return None


def phi(a, b, c, d):
    """Matthews correlation for a 2x2 (a=++ b=+- c=-+ d=--)."""
    denom = math.sqrt((a + b) * (c + d) * (a + c) * (b + d))
    return (a * d - b * c) / denom if denom else 0.0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tag", default="", help="input/output suffix, e.g. base/transformed")
    p.add_argument("--fl-apr", default=None, help="override fl-apr-cells path")
    p.add_argument("--reasoning", default=None, help="override reasoning-cells path")
    args = p.parse_args(argv)

    suffix = f"-{args.tag}" if args.tag else ""
    fl_apr_path = args.fl_apr or os.path.join(REPO, f"fl-apr-cells{suffix}.csv")
    reason_path = args.reasoning or os.path.join(REPO, f"reasoning-cells{suffix}.csv")
    out_path = os.path.join(REPO, f"trust-cells{suffix}.csv")

    if not os.path.exists(fl_apr_path):
        sys.exit(f"missing {fl_apr_path} - run fl_apr_align.py")
    if not os.path.exists(reason_path):
        sys.exit(f"missing {reason_path} - run reasoning_eval.py")

    # ---- load both sources, keyed by (model, run, instance) ----
    fa = {}
    for r in load_csv(fl_apr_path):
        fa[(r["model"], r["run"], r["instance"])] = {
            "fl_line_hit": as_bool(r.get("fl_correct")),
            "resolved": as_bool(r.get("resolved")),
            "quadrant": r.get("quadrant", "")}
    re = {}
    for r in load_csv(reason_path):
        coded = as_bool(r.get("coded"))
        binlab = r.get("binary") or ""            # PRIMARY: consistent/conflicting
        re[(r["model"], r["run"], r["instance"])] = {
            "reason_fl_line_hit": as_bool(r.get("fl_line_hit")),
            "binary": binlab if coded else "",
            "alignment": r.get("alignment") or "",   # 4-way diagnostic
            "consistent": as_bool(r.get("consistent")) if coded else None}

    keys = sorted(set(fa) | set(re))

    # ---- write unified per-cell table ----
    def prof(fl, apr, binlab):
        f = "FL+" if fl is True else "FL-" if fl is False else "FL?"
        a = "APR+" if apr is True else "APR-" if apr is False else "APR?"
        r = f"R:{binlab}" if binlab else "R:?"       # consistent/conflicting
        return f"{f} {a} {r}"

    rows = []
    mism = 0
    for k in keys:
        m, run, inst = k
        f = fa.get(k, {})
        rr = re.get(k, {})
        fl = f.get("fl_line_hit")
        # cross-check FL agreement between the two sources when both present
        if (fl is not None and rr.get("reason_fl_line_hit") is not None
                and fl != rr["reason_fl_line_hit"]):
            mism += 1
        binlab = rr.get("binary", "")
        rows.append({"model": m, "run": run, "instance": inst,
                     "fl_line_hit": fl if fl is not None else "",
                     "resolved": f.get("resolved") if f.get("resolved") is not None else "",
                     "reasoning_binary": binlab,
                     "reasoning_consistent": rr.get("consistent")
                     if rr.get("consistent") is not None else "",
                     "reasoning_alignment_4way": rr.get("alignment", ""),
                     "quadrant": f.get("quadrant", ""),
                     "trust_profile": prof(fl, f.get("resolved"), binlab)})
    with open(out_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["model", "run", "instance",
                                           "fl_line_hit", "resolved",
                                           "reasoning_binary",
                                           "reasoning_consistent",
                                           "reasoning_alignment_4way", "quadrant",
                                           "trust_profile"])
        w.writeheader(); w.writerows(rows)

    if mism:
        print(f"WARNING: {mism} cells disagree on FL line-hit between the two "
              "sources (should be 0 - same fl_eval matching); investigate.")

    # ---- cross-axis summary over cells with all THREE axes defined ----
    def summarize(name, subset):
        n = len(subset)
        if not n:
            print(f"\n{name}: no cells with FL, APR, and reasoning all defined")
            return
        FLp = [s for s in subset if s["fl"]]
        FLn = [s for s in subset if not s["fl"]]
        APRp = [s for s in subset if s["apr"]]
        APRn = [s for s in subset if not s["apr"]]
        co = lambda xs: sum(1 for s in xs if s["consistent"])
        full = sum(1 for s in subset if s["fl"] and s["apr"] and s["consistent"])
        # fix without understanding
        fwu_fl = sum(1 for s in APRp if not s["fl"])
        fwu_r = sum(1 for s in APRp if not s["consistent"])
        # phi(reasoning-consistent, FL) and phi(reasoning-consistent, APR)
        def phi_with(pred):
            a = sum(1 for s in subset if s["consistent"] and pred(s))
            b = sum(1 for s in subset if s["consistent"] and not pred(s))
            c = sum(1 for s in subset if not s["consistent"] and pred(s))
            d = sum(1 for s in subset if not s["consistent"] and not pred(s))
            return phi(a, b, c, d)

        pr = lambda a, b: f"{a}/{b} = {a / b:.3f}" if b else "-"
        print(f"\n{name}  (n={n} cells with all 3 axes defined)")
        print(f"  full trust (FL+ & APR+ & consistent) : {pr(full, n)}")
        print(f"  P(consistent | FL correct)           : {pr(co(FLp), len(FLp))}")
        print(f"  P(consistent | FL wrong)             : {pr(co(FLn), len(FLn))}"
              f"   (phi FL~consistent = {phi_with(lambda s: s['fl']):+.3f})")
        print(f"  P(consistent | resolved)             : {pr(co(APRp), len(APRp))}")
        print(f"  P(consistent | unresolved)           : {pr(co(APRn), len(APRn))}"
              f"   (phi APR~consistent = {phi_with(lambda s: s['apr']):+.3f})")
        print(f"  fix-without-understanding (of {len(APRp)} resolved):")
        print(f"      resolved but FL wrong             : {pr(fwu_fl, len(APRp))}")
        print(f"      resolved but reasoning conflicting : {pr(fwu_r, len(APRp))}")

    triple = defaultdict(list)
    allthree = []
    for k in keys:
        f, rr = fa.get(k, {}), re.get(k, {})
        fl, apr, binlab = f.get("fl_line_hit"), f.get("resolved"), rr.get("binary")
        if fl is None or apr is None or not binlab:
            continue                      # need all three axes defined
        rec = {"fl": fl, "apr": apr, "consistent": binlab == "consistent"}
        allthree.append(rec)
        triple[k[0]].append(rec)

    print("=" * 60)
    print("THREE-AXIS TRUST SUMMARY  (FL x APR x reasoning)")
    print("=" * 60)
    summarize("OVERALL", allthree)
    for m in sorted(triple):
        summarize(m, triple[m])

    print(f"\n-> {out_path}  ({len(rows)} cells; "
          f"{len(allthree)} with all three axes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
