#!/usr/bin/env python3
"""Build the human-labeled validation sheet for the reasoning judge.

The human has already labeled the agreed instances in ``reasoning_alignment.csv``
(columns ``InstanceId,Label`` with Label in the four-level rubric).  This script
joins those labels with each annotator's reasoning text and writes a completed
``validation_sheet.csv`` (``human_alignment`` pre-filled) plus a key file that
records which annotator is shown as "1" vs "2" (randomized per instance so
position carries no signal).  Then run judge_validation.py to compute
judge-human agreement (Cohen's k).

By default every labeled agreed instance is included; pass ``--n`` to draw a
fixed, reproducible sub-sample instead.

Usage:
    python make_validation_sheet.py                 # all labeled instances
    python make_validation_sheet.py --n 20 --seed 42
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

HUMAN_LABELS = os.path.join(REPO, "reasoning_alignment.csv")

OUT_DIR = os.path.join(REPO, "annotation", "reasoning_alignment", "validation")
SHEET_FILE = os.path.join(OUT_DIR, "validation_sheet.csv")
KEY_FILE = os.path.join(OUT_DIR, "validation_key.json")

LABELS = ["aligned", "partial", "divergent", "contradictory"]


def read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def reasoning_of(directory: str, iid: str) -> str:
    return str(read_json(os.path.join(directory, iid + ".json")).get("reasoning") or "")


def read_human_labels(path: str) -> dict[str, str]:
    """{instance_id: normalized_label} from reasoning_alignment.csv."""
    labels: dict[str, str] = {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            iid = (r.get("InstanceId") or "").strip()
            lab = (r.get("Label") or "").strip().lower()
            if not iid:
                continue
            if lab not in LABELS:
                sys.exit(f"{iid}: invalid Label {lab!r} in {os.path.basename(path)} "
                         f"(use one of {LABELS})")
            labels[iid] = lab
    return labels


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--n", type=int, default=None,
                   help="sub-sample size (default: all labeled instances)")
    p.add_argument("--seed", type=int, default=42, help="RNG seed (default 42)")
    args = p.parse_args(argv)

    report = read_json(REPORT_JSON)
    agreed = {i["instance_id"] for i in report["instances"]
              if i["status"] == "agree"}
    human = read_human_labels(HUMAN_LABELS)

    # labeled instances must be part of the agreed set the judge runs on
    not_agreed = sorted(set(human) - agreed)
    unlabeled = sorted(agreed - set(human))
    if not_agreed:
        print(f"WARNING: {len(not_agreed)} labeled instance(s) are not in the "
              f"agreed set (skipped): {', '.join(not_agreed)}")
    if unlabeled:
        print(f"note: {len(unlabeled)} agreed instance(s) have no human label "
              f"(excluded): {', '.join(unlabeled)}")

    labeled = sorted(set(human) & agreed)
    if not labeled:
        sys.exit("no labeled instances overlap the agreed set")

    rng = random.Random(args.seed)
    if args.n is not None:
        if args.n > len(labeled):
            sys.exit(f"requested {args.n} but only {len(labeled)} labeled "
                     f"agreed instances")
        labeled = sorted(rng.sample(labeled, args.n))

    os.makedirs(OUT_DIR, exist_ok=True)
    key = {"seed": args.seed, "n": len(labeled), "source": os.path.basename(HUMAN_LABELS),
           "instances": {}}
    rows = []
    for iid in labeled:
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
            "human_alignment": human[iid],
            "human_notes": "",
        })

    with open(SHEET_FILE, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    with open(KEY_FILE, "w", encoding="utf-8") as fh:
        json.dump(key, fh, indent=2)

    dist = {lab: sum(1 for r in rows if r["human_alignment"] == lab) for lab in LABELS}
    print(f"\nwrote {len(rows)}-instance validation sheet -> {SHEET_FILE}")
    print(f"identity key (keep separate from labelers) -> {KEY_FILE}")
    print("human label distribution: "
          + ", ".join(f"{lab}={dist[lab]}" for lab in LABELS if dist[lab]))
    print("run judge_validation.py to compute judge-human Cohen's kappa")
    return 0


if __name__ == "__main__":
    sys.exit(main())
