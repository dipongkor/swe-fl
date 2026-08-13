#!/usr/bin/env python3
"""Compute judge-human agreement (Cohen's kappa) on the validation sample.

Reads the human-labeled validation sheet and the judge's report, aligns them by
instance_id, and reports raw agreement, unweighted Cohen's kappa, and
linearly-weighted kappa (the labels are ordinal: aligned < partial < divergent <
contradictory), plus a confusion matrix.  A substantial kappa is what licenses
reporting the judge's full-set verdicts in the paper.

Usage:
    python judge_validation.py
"""

from __future__ import annotations

import csv
import json
import os
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(REPO, "annotation", "reasoning_alignment")
SHEET_FILE = os.path.join(OUT_DIR, "validation", "validation_sheet.csv")
REPORT_JSON = os.path.join(OUT_DIR, "reasoning_alignment_report.json")

LABELS = ["aligned", "partial", "divergent", "contradictory"]
RANK = {lab: i for i, lab in enumerate(LABELS)}


def cohen_kappa(pairs: list[tuple[str, str]], weighted: bool) -> float:
    n = len(pairs)
    k = len(LABELS)
    obs = [[0.0] * k for _ in range(k)]
    for h, j in pairs:
        obs[RANK[h]][RANK[j]] += 1
    row = [sum(obs[i]) for i in range(k)]
    col = [sum(obs[i][c] for i in range(k)) for c in range(k)]

    def d(i, c):  # disagreement weight
        return abs(i - c) / (k - 1) if weighted else (0.0 if i == c else 1.0)

    obs_dis = sum(d(i, c) * obs[i][c] for i in range(k) for c in range(k))
    exp_dis = sum(d(i, c) * row[i] * col[c] / n
                  for i in range(k) for c in range(k))
    return 1.0 - obs_dis / exp_dis if exp_dis else 1.0


def band(kappa: float) -> str:
    for thr, name in [(0.81, "almost perfect"), (0.61, "substantial"),
                      (0.41, "moderate"), (0.21, "fair"), (0.0, "slight")]:
        if kappa >= thr:
            return name
    return "poor (< chance)"


def main() -> int:
    if not os.path.exists(SHEET_FILE):
        sys.exit(f"no validation sheet at {SHEET_FILE} - run make_validation_sheet.py")
    if not os.path.exists(REPORT_JSON):
        sys.exit(f"no judge report at {REPORT_JSON} - run reasoning_judge.py --collect")

    with open(REPORT_JSON, encoding="utf-8") as fh:
        judge = json.load(fh)

    pairs, unlabeled, missing = [], [], []
    with open(SHEET_FILE, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            iid = r["instance_id"]
            h = (r.get("human_alignment") or "").strip().lower()
            if not h:
                unlabeled.append(iid)
                continue
            if h not in RANK:
                sys.exit(f"{iid}: invalid human_alignment '{h}' "
                         f"(use one of {LABELS})")
            j = judge.get(iid, {}).get("final_alignment")
            if j not in RANK:
                missing.append(iid)
                continue
            pairs.append((h, j))

    if unlabeled:
        print(f"WARNING: {len(unlabeled)} rows have no human label "
              f"(skipped): {', '.join(unlabeled)}")
    if missing:
        print(f"WARNING: {len(missing)} instances lack a judge verdict "
              f"(skipped): {', '.join(missing)}")
    if not pairs:
        sys.exit("no comparable (human, judge) pairs")

    n = len(pairs)
    agree = sum(1 for h, j in pairs if h == j)
    k_un = cohen_kappa(pairs, weighted=False)
    k_w = cohen_kappa(pairs, weighted=True)

    print(f"\njudge-human validation on {n} labeled instances")
    print(f"  raw agreement:        {agree}/{n} = {agree / n:.1%}")
    print(f"  Cohen's kappa:        {k_un:.3f}  ({band(k_un)})")
    print(f"  weighted kappa (lin): {k_w:.3f}  ({band(k_w)})")

    print("\nconfusion matrix (rows = human, cols = judge)")
    k = len(LABELS)
    obs = [[0] * k for _ in range(k)]
    for h, j in pairs:
        obs[RANK[h]][RANK[j]] += 1
    head = "  " + "".join(f"{lab[:5]:>7}" for lab in LABELS)
    print("            " + head)
    for i, lab in enumerate(LABELS):
        print(f"  {lab:>13}" + "".join(f"{obs[i][c]:>7}" for c in range(k)))

    # ---- per-class precision / recall (only for classes that appear) ----
    # recall    = diagonal / human total for that class  (of the human's X, how
    #             many the judge also called X)
    # precision = diagonal / judge total for that class  (of the judge's X, how
    #             many were truly X)
    row = [sum(obs[i]) for i in range(k)]                     # human totals
    col = [sum(obs[i][c] for i in range(k)) for c in range(k)]  # judge totals
    used = [i for i in range(k) if row[i] or col[i]]
    print("\nper-class agreement (only classes used by either rater)")
    print(f"  {'class':>13}{'recall':>16}{'precision':>16}")
    for i in used:
        tp = obs[i][i]
        recall = f"{tp}/{row[i]} = {tp / row[i]:.1%}" if row[i] else "-  (n=0)"
        prec = f"{tp}/{col[i]} = {tp / col[i]:.1%}" if col[i] else "-  (n=0)"
        print(f"  {LABELS[i]:>13}{recall:>16}{prec:>16}")
    print("  recall  = of the human's X, how many the judge also called X")
    print("  precision = of the judge's X, how many were truly X")
    return 0


if __name__ == "__main__":
    sys.exit(main())
