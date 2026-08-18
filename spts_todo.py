#!/usr/bin/env python3
"""List which sampled instances still need SPTs generated.

Diffs the robustness panel (robustness-sample.txt) against the already-generated
SPT directories under spts/, and writes the instances that still need SPTs to
spts-to-generate.txt (one id per line).  Optionally also writes the SPTs that
exist but are NOT in the current sample (orphans) so nothing is deleted blindly.

Usage:
    python spts_todo.py
    python spts_todo.py --sample robustness-sample.txt --spts-dir spts
    python spts_todo.py --write-unused        # also emit spts-unused.txt
"""

from __future__ import annotations

import argparse
import os
import sys

REPO = os.path.dirname(os.path.abspath(__file__))


def read_sample(path: str) -> list[str]:
    with open(path, encoding="utf-8") as fh:
        return [ln.strip() for ln in fh if ln.strip()]


def existing_spts(spts_dir: str) -> set[str]:
    """Instance ids that already have an SPT directory (dirs only)."""
    if not os.path.isdir(spts_dir):
        return set()
    return {name for name in os.listdir(spts_dir)
            if os.path.isdir(os.path.join(spts_dir, name))}


def write_list(path: str, ids: list[str]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(ids) + ("\n" if ids else ""))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sample", default=os.path.join(REPO, "robustness-sample.txt"),
                   help="panel instance list (one id per line)")
    p.add_argument("--spts-dir", default=os.path.join(REPO, "spts"),
                   help="directory holding one subdir per already-generated SPT")
    p.add_argument("--out", default=os.path.join(REPO, "spts-to-generate.txt"),
                   help="output file for instances still needing SPTs")
    p.add_argument("--write-unused", action="store_true",
                   help="also write spts-unused.txt (SPTs not in the sample)")
    args = p.parse_args(argv)

    if not os.path.exists(args.sample):
        sys.exit(f"missing {args.sample} - run select_robustness_sample.py first")

    sample = read_sample(args.sample)
    sample_set = set(sample)
    have = existing_spts(args.spts_dir)

    need = sorted(sample_set - have)          # in sample, no SPT yet
    covered = sorted(sample_set & have)       # in sample, SPT exists
    unused = sorted(have - sample_set)        # SPT exists, not in this sample

    write_list(args.out, need)

    print(f"sample instances   : {len(sample_set)}")
    if len(sample) != len(sample_set):
        print(f"  note: {len(sample) - len(sample_set)} duplicate id(s) in sample")
    print(f"existing SPTs       : {len(have)}")
    print(f"already covered     : {len(covered)}")
    print(f"NEED SPTs           : {len(need)}   -> {args.out}")
    print(f"unused SPTs         : {len(unused)}"
          f"{'   -> ' + os.path.join(REPO, 'spts-unused.txt') if args.write_unused else ''}")

    if args.write_unused:
        write_list(os.path.join(REPO, "spts-unused.txt"), unused)

    return 0


if __name__ == "__main__":
    sys.exit(main())
