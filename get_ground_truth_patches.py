#!/usr/bin/env python3
"""Fetch the ground-truth (gold) patches for our benchmark instances from SWE-bench Verified.

For each instance, the developer-written gold patch (the ``patch`` field of SWE-bench
Verified) is written to ground-truth-patches/<instance_id>.patch.

Instance list (first match wins):
    --instances FILE   explicit list, one id per line
    --all              every instance in SWE-bench Verified (500)
    default            the benchmark set, i.e. the ids under ground-truth-fl/*.json (130)

Usage:
    python get_ground_truth_patches.py
    python get_ground_truth_patches.py --instances annotation/instance_ids.txt
    python get_ground_truth_patches.py --all --overwrite
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

from datasets import load_dataset

REPO = os.path.dirname(os.path.abspath(__file__))
DATASET = "SWE-bench/SWE-bench_Verified"
SPLIT = "test"


def benchmark_ids() -> list[str]:
    """Benchmark instance ids = filenames under ground-truth-fl/*.json."""
    paths = glob.glob(os.path.join(REPO, "ground-truth-fl", "*.json"))
    return sorted({os.path.splitext(os.path.basename(p))[0] for p in paths})


def read_list(path: str) -> list[str]:
    with open(path, encoding="utf-8") as fh:
        return [ln.strip() for ln in fh if ln.strip()]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--instances", help="file with one instance id per line")
    p.add_argument("--all", action="store_true",
                   help="fetch patches for every SWE-bench Verified instance")
    p.add_argument("--out", default=os.path.join(REPO, "ground-truth-patches"),
                   help="output directory (default: ground-truth-patches)")
    p.add_argument("--ext", default="patch",
                   help="patch file extension (default: patch)")
    p.add_argument("--overwrite", action="store_true",
                   help="rewrite patches that already exist")
    args = p.parse_args(argv)

    if args.instances:
        wanted = read_list(args.instances)
        source = args.instances
    elif args.all:
        wanted = None  # filled after the dataset loads
        source = "SWE-bench Verified (all)"
    else:
        wanted = benchmark_ids()
        source = "ground-truth-fl/*.json"
        if not wanted:
            sys.exit("no ground-truth-fl/*.json found; pass --instances or --all")

    print(f"loading {DATASET} [{SPLIT}] ...")
    ds = load_dataset(DATASET, split=SPLIT)
    patches = {row["instance_id"]: row["patch"] for row in ds}

    if wanted is None:
        wanted = sorted(patches)

    os.makedirs(args.out, exist_ok=True)
    written = skipped = missing = empty = 0
    missing_ids: list[str] = []
    for iid in wanted:
        if iid not in patches:
            missing += 1
            missing_ids.append(iid)
            continue
        dest = os.path.join(args.out, f"{iid}.{args.ext}")
        if os.path.exists(dest) and not args.overwrite:
            skipped += 1
            continue
        patch = patches[iid] or ""
        if not patch.strip():
            empty += 1
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(patch if patch.endswith("\n") else patch + "\n")
        written += 1

    print(f"instance source     : {source}")
    print(f"instances requested : {len(wanted)}")
    print(f"patches written     : {written}   -> {args.out}")
    print(f"already present     : {skipped} (use --overwrite to refresh)")
    if empty:
        print(f"WARNING empty patch : {empty}")
    print(f"missing from dataset: {missing}")
    for iid in missing_ids:
        print(f"  MISSING {iid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
