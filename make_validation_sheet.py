#!/usr/bin/env python3
"""Sample agreed instances for human validation of the reasoning judge.

Draws a fixed, reproducible sample of the ``agree`` instances and writes a
blinded CSV for a human to label against the SAME four-level rubric the judge
uses.  A separate key file records which annotator is "1" vs "2" (randomized per
instance so position carries no signal).  Fill in ``human_alignment`` for each
row, then run judge_validation.py to compute judge-human agreement (Cohen's k).

Usage:
    python make_validation_sheet.py                 # 20-instance sample, seed 42
    python make_validation_sheet.py --n 25 --seed 7
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
REPORT_JSON = os.path.join(REPO, "annotation", "merge_report.json")
DIR_A = os.path.join(REPO, "annotation", "Atish_Annotation")
DIR_B = os.path.join(REPO, "annotation", "Eshgin_Annotation")
NAME_A, NAME_B = "Atish", "Eshgin"

OUT_DIR = os.path.join(REPO, "annotation", "reasoning_alignment", "validation")
SHEET_FILE = os.path.join(OUT_DIR, "validation_sheet.csv")
KEY_FILE = os.path.join(OUT_DIR, "validation_key.json")

LABELS = ["aligned", "partial", "divergent", "contradictory"]


def read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def reasoning_of(directory: str, iid: str) -> str:
    return str(read_json(os.path.join(directory, iid + ".json")).get("reasoning") or "")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--n", type=int, default=20, help="sample size (default 20)")
    p.add_argument("--seed", type=int, default=42, help="RNG seed (default 42)")
    args = p.parse_args(argv)

    report = read_json(REPORT_JSON)
    agreed = sorted(i["instance_id"] for i in report["instances"]
                    if i["status"] == "agree")
    if args.n > len(agreed):
        sys.exit(f"requested {args.n} but only {len(agreed)} agreed instances")

    rng = random.Random(args.seed)
    sample = sorted(rng.sample(agreed, args.n))

    os.makedirs(OUT_DIR, exist_ok=True)
    key = {"seed": args.seed, "n": args.n, "instances": {}}
    rows = []
    for iid in sample:
        ra, rb = reasoning_of(DIR_A, iid), reasoning_of(DIR_B, iid)
        # randomize which annotator is shown as "1" so position is uninformative
        if rng.random() < 0.5:
            r1, r2, who1, who2 = ra, rb, NAME_A, NAME_B
        else:
            r1, r2, who1, who2 = rb, ra, NAME_B, NAME_A
        key["instances"][iid] = {"annotator_1": who1, "annotator_2": who2}
        rows.append({
            "instance_id": iid,
            "annotator_1_reasoning": " ".join(r1.split()),
            "annotator_2_reasoning": " ".join(r2.split()),
            "human_alignment": "",
            "human_notes": "",
        })

    with open(SHEET_FILE, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    with open(KEY_FILE, "w", encoding="utf-8") as fh:
        json.dump(key, fh, indent=2)

    print(f"wrote {len(rows)}-instance validation sheet -> {SHEET_FILE}")
    print(f"identity key (keep separate from labelers) -> {KEY_FILE}")
    print(f"label each row's 'human_alignment' with one of: {', '.join(LABELS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
