#!/usr/bin/env python3
"""Flatten the ground-truth fault-localization annotations into a CSV.

One row per root_cause location; the instance_id repeats across an instance's
locations.  Columns: instance_id, base_commit, file, line, statements.

base_commit is looked up per instance from SWE-bench/SWE-bench_Verified (loaded
from the local HF datasets cache; needs a one-time download otherwise).

Usage:
    python ground_truth_to_csv.py                        # -> ground-truth-fl.csv
    python ground_truth_to_csv.py --out somewhere.csv
    python ground_truth_to_csv.py --dir ground-truth-fl
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DIR = os.path.join(REPO, "ground-truth-fl")
DEFAULT_OUT = os.path.join(REPO, "ground-truth-fl.csv")

SWEBENCH_DATASET = "SWE-bench/SWE-bench_Verified"
COLUMNS = ["instance_id", "base_commit", "file", "line", "statements"]


def base_commit_map() -> dict[str, str]:
    """instance_id -> base_commit from SWE-bench_Verified (HF cache)."""
    try:
        from datasets import load_dataset
    except ModuleNotFoundError:
        sys.exit("datasets not installed - run: pip install datasets")
    ds = load_dataset(SWEBENCH_DATASET, split="test")
    return {r["instance_id"]: r["base_commit"] for r in ds}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dir", default=DEFAULT_DIR, help="ground-truth JSON directory")
    p.add_argument("--out", default=DEFAULT_OUT, help="output CSV path")
    args = p.parse_args(argv)

    files = sorted(glob.glob(os.path.join(args.dir, "*.json")))
    if not files:
        sys.exit(f"no .json files in {args.dir}")

    commits = base_commit_map()

    rows, no_rc, no_commit = [], [], []
    for path in files:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        iid = doc.get("instance_id") or os.path.splitext(os.path.basename(path))[0]
        base_commit = commits.get(iid, "")
        if not base_commit:
            no_commit.append(iid)
        locs = doc.get("root_cause") or []
        if not locs:
            no_rc.append(iid)
            rows.append({"instance_id": iid, "base_commit": base_commit,
                         "file": "", "line": "", "statements": ""})
            continue
        for loc in locs:
            rows.append({
                "instance_id": iid,
                "base_commit": base_commit,
                "file": loc.get("file", ""),
                "line": loc.get("line", ""),
                "statements": loc.get("statement", ""),
            })

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"{len(files)} instances -> {len(rows)} rows -> {args.out}")
    if no_rc:
        print(f"WARNING: {len(no_rc)} instance(s) had no root_cause "
              f"(blank row written): {', '.join(no_rc)}")
    if no_commit:
        print(f"WARNING: {len(no_commit)} instance(s) not found in "
              f"{SWEBENCH_DATASET} (blank base_commit): {', '.join(no_commit)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
