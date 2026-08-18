#!/usr/bin/env python3
"""Select a stratified instance panel for the robustness experiment.

We can't run all instances x 13 transforms x models x runs, so we sample a
panel of base instances to transform.  Robustness of fault localization is only
observable where the base localization was CORRECT, so we draw from two
FL-correct behavioural groups (a model "reliably" achieves an outcome = majority
of its 3 base runs; an instance qualifies for a group if >= --min-models models
do):

  A  both     FL correct AND resolved      -> observe APR robustness too
  B  fl_only  FL correct AND NOT resolved   -> observe FL robustness under a
                                              known base-repair failure

Groups are made disjoint (an instance in both goes to A).  Within each group the
sample is stratified by repo x difficulty (SWE-bench Verified human difficulty)
with proportional, largest-remainder allocation, so the panel mirrors the pool's
project and difficulty mix.  The same panel is transformed by all 13 rules
(within-subjects), so base-vs-transform is paired per instance.

Inputs:
  fl-apr-cells.csv                     (from fl_apr_align.py)
  SWE-bench/SWE-bench_Verified         (repo + difficulty per instance)

Usage:
    python select_robustness_sample.py                    # 25 + 25, seed 42
    python select_robustness_sample.py --n-both 30 --n-fl-only 20 --seed 7
"""

from __future__ import annotations

import argparse
import collections
import csv
import os
import random
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
CELLS_CSV = os.path.join(REPO, "fl-apr-cells.csv")
REASON_CSV = os.path.join(REPO, "reasoning-cells-base.csv")
OUT_CSV = os.path.join(REPO, "robustness-sample.csv")
OUT_LIST = os.path.join(REPO, "robustness-sample.txt")

DIFF_SHORT = {"<15 min fix": "<15m", "15 min - 1 hour": "15m-1h",
              "1-4 hours": "1-4h", ">4 hours": ">4h"}


def load_meta():
    """{instance_id: (repo_short, difficulty_short)} from SWE-bench Verified."""
    from datasets import load_dataset
    ds = load_dataset("SWE-bench/SWE-bench_Verified", split="test")
    meta = {}
    for r in ds:
        meta[r["instance_id"]] = (r["repo"].split("/")[-1],
                                  DIFF_SHORT.get(r["difficulty"], r["difficulty"]))
    return meta


def model_reliability(cells_csv: str):
    """{instance: {model: (fl_true_runs, resolved_true_runs)}} over base runs."""
    by = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    with open(cells_csv, newline="") as fh:
        for r in csv.DictReader(fh):
            b = by[r["instance"]][r["model"]]
            b[0] += r["fl_correct"] == "True"
            b[1] += r["resolved"] == "True"
    return by


def reasoning_reliability(path: str):
    """{instance: {model: consistent_true_runs}} over base runs; {} if absent.

    Reasoning is NOT a selection criterion (FL-correct instances are already
    ~93% base-consistent) - this feeds a coverage diagnostic only, so we can
    confirm the reasoning and full-trust robustness axes have enough
    base-positive cells for the paired McNemar test to have power.
    """
    if not path or not os.path.exists(path):
        return {}
    by = collections.defaultdict(lambda: collections.defaultdict(int))
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("consistent") == "True":
                by[r["instance"]][r["model"]] += 1
    return by


def coverage_diagnostic(rows, by, rby):
    """Base-positive (model x instance) CELL counts per robustness axis in the
    drawn panel.  These are the a+b denominators of each axis's break-rate."""
    print("=" * 62)
    print("BASE COVERAGE DIAGNOSTIC  (robustness-axis power)")
    print("=" * 62)
    print("break-rate b/(a+b) is defined over base-CORRECT cells, so each axis")
    print("needs enough base-positive (model x instance) cells to test.\n")
    have_reason = bool(rby)
    scopes = [("PANEL", rows)] + [(g, [r for r in rows if r["group"] == g])
                                  for g in ("both", "fl_only")]
    hdr = f"  {'scope':9}{'inst':>6}{'cells':>7}{'FL+':>7}{'APR+':>7}"
    hdr += f"{'reas+':>7}{'full+':>7}" if have_reason else ""
    print(hdr)
    for name, subset in scopes:
        insts = [r["instance_id"] for r in subset]
        fl = apr = cons = full = ncells = 0
        for i in insts:
            for m in by[i]:
                ncells += 1
                f = by[i][m][0] >= 2
                a = by[i][m][1] >= 2
                c = rby.get(i, {}).get(m, 0) >= 2
                fl += f; apr += a; cons += c
                full += (f and a and c)
        line = f"  {name:9}{len(insts):>6}{ncells:>7}{fl:>7}{apr:>7}"
        line += f"{cons:>7}{full:>7}" if have_reason else ""
        print(line)
    if have_reason:
        # per-model reasoning-consistent coverage across the panel
        models = sorted({m for r in rows for m in by[r["instance_id"]]})
        print(f"\n  reasoning-consistent base cells per model (of panel instances):")
        for m in models:
            c = sum(1 for r in rows if rby.get(r["instance_id"], {}).get(m, 0) >= 2)
            tot = sum(1 for r in rows if m in by[r["instance_id"]])
            print(f"    {m:24}{c:>4}/{tot} localized-base cells consistent")
    else:
        print("  (reasoning-cells-base.csv not found - run reasoning_eval.py "
              "--tag base;\n   reasoning/full-trust axes cannot be power-checked yet)")
    print()


def build_pools(by, min_models: int):
    """Disjoint A(both)/B(fl_only) pools -> {instance: counts dict}."""
    A, B = {}, {}
    for inst, models in by.items():
        n_both = sum(1 for f, rz in models.values() if f >= 2 and rz >= 2)
        n_flon = sum(1 for f, rz in models.values() if f >= 2 and rz < 2)
        n_flc = sum(1 for f, rz in models.values() if f >= 2)
        rec = {"n_both": n_both, "n_fl_only": n_flon, "n_fl_correct": n_flc}
        if n_both >= min_models:
            A[inst] = rec
        elif n_flon >= min_models:          # 'elif' -> disjoint, A wins ties
            B[inst] = rec
    return A, B


def allocate(strata_sizes: dict, n: int, rng: random.Random):
    """Proportional largest-remainder allocation, capped at each stratum size."""
    total = sum(strata_sizes.values())
    n = min(n, total)
    raw = {k: n * v / total for k, v in strata_sizes.items()}
    alloc = {k: int(x) for k, x in raw.items()}
    rem = n - sum(alloc.values())
    order = sorted(strata_sizes, key=lambda k: (raw[k] - alloc[k],
                                                rng.random()), reverse=True)
    i = 0
    while rem > 0 and order:
        k = order[i % len(order)]
        if alloc[k] < strata_sizes[k]:
            alloc[k] += 1
            rem -= 1
        i += 1
        if i > 100000:
            break
    return alloc


def sample_group(pool: dict, meta: dict, n: int, rng: random.Random):
    """Stratified sample of `n` instances from a pool by (repo, difficulty)."""
    strata = collections.defaultdict(list)
    for inst in pool:
        repo, diff = meta.get(inst, ("?", "?"))
        strata[(repo, diff)].append(inst)
    sizes = {k: len(v) for k, v in strata.items()}
    alloc = allocate(sizes, n, rng)
    picked = []
    for k, members in strata.items():
        take = alloc.get(k, 0)
        if take:
            picked.extend(rng.sample(sorted(members), take))
    return sorted(picked), sizes, alloc


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cells", default=CELLS_CSV)
    p.add_argument("--reasoning-cells", default=REASON_CSV,
                   help="reasoning-cells-base.csv for the base-coverage diagnostic")
    p.add_argument("--n-both", type=int, default=25, help="sample size for group A")
    p.add_argument("--n-fl-only", type=int, default=25, help="sample size for group B")
    p.add_argument("--min-models", type=int, default=2,
                   help="min models reliably in the group (default 2)")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args(argv)

    if not os.path.exists(args.cells):
        sys.exit(f"missing {args.cells} - run fl_apr_align.py first")

    meta = load_meta()
    by = model_reliability(args.cells)
    rby = reasoning_reliability(args.reasoning_cells)
    A, B = build_pools(by, args.min_models)
    rng = random.Random(args.seed)

    print(f"eligible pools (>= {args.min_models} models, majority of 3 runs):")
    print(f"  A both    : {len(A)} instances")
    print(f"  B fl_only : {len(B)} instances (disjoint from A)\n")

    rows = []
    for gname, gcode, pool, n in [("both", "A", A, args.n_both),
                                  ("fl_only", "B", B, args.n_fl_only)]:
        picked, sizes, alloc = sample_group(pool, meta, n, rng)
        print(f"group {gcode} ({gname}): sampled {len(picked)}/{len(pool)} "
              f"(requested {n})")
        # stratum table
        diffs = ["<15m", "15m-1h", "1-4h", ">4h"]
        repos = sorted({r for r, _ in sizes})
        print(f"  {'repo':16}" + "".join(f"{d:>9}" for d in diffs) + f"{'picked':>8}")
        for repo in repos:
            cells = [f"{alloc.get((repo,d),0)}/{sizes.get((repo,d),0)}"
                     if (repo, d) in sizes else "-" for d in diffs]
            got = sum(alloc.get((repo, d), 0) for d in diffs)
            print(f"  {repo:16}" + "".join(f"{c:>9}" for c in cells) + f"{got:>8}")
        print()
        for inst in picked:
            repo, diff = meta.get(inst, ("?", "?"))
            rec = pool[inst]
            n_cons = sum(1 for m in rby.get(inst, {}) if rby[inst][m] >= 2)
            rows.append({"instance_id": inst, "group": gname, "repo": repo,
                         "difficulty": diff, "n_models_both": rec["n_both"],
                         "n_models_fl_only": rec["n_fl_only"],
                         "n_models_fl_correct": rec["n_fl_correct"],
                         "n_models_reasoning_consistent": n_cons})

    coverage_diagnostic(rows, by, rby)

    with open(OUT_CSV, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["instance_id", "group", "repo",
                                           "difficulty", "n_models_both",
                                           "n_models_fl_only", "n_models_fl_correct",
                                           "n_models_reasoning_consistent"])
        w.writeheader(); w.writerows(rows)
    with open(OUT_LIST, "w") as fh:
        fh.write("\n".join(r["instance_id"] for r in rows) + "\n")

    print(f"panel size: {len(rows)} instances "
          f"-> transform x13 x {len(by[next(iter(by))])} models")
    print(f"-> {OUT_CSV}")
    print(f"-> {OUT_LIST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
