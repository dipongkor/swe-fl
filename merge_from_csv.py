#!/usr/bin/env python3
"""Build ground-truth annotations from the two annotators + decision CSVs.

Inputs (in this folder):
  agreed.csv     - InstanceId, FinalReasoning   (FinalReasoning in {Both, Atish, Eshgin})
  conflicts.csv  - "Instance ID", Final_FL       (Final_FL in {Atish, Eshgin})

Rules:
  annotator1 = Atish, annotator2 = Eshgin.

  Agreed instances:
    * root_cause + confidence  <- Atish (they agree on the location).
    * reasoning: FinalReasoning == "Both"  -> both filled
                                 == "Atish" -> annotator1 only
                                 == "Eshgin"-> annotator2 only
    * comments = "both agreed".

  Conflict instances:
    * root_cause + confidence + reasoning  <- the annotator named in Final_FL
      (that annotator's reasoning slot filled, the other left "").
    * comments = that annotator's name.

Output schema (one file per instance -> ground-truth-fl/<instance_id>.json):
  {
    "instance_id": ...,
    "root_cause": [{"file": ..., "line": ..., "statement": ...}, ...],
    "confidence": ...,
    "comments": ...,
    "reasoning": {"annotator1": ..., "annotator2": ...}
  }
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
A_DIR = os.path.join(REPO, "annotation", "Atish_Annotation")   # annotator1
B_DIR = os.path.join(REPO, "annotation", "Eshgin_Annotation")  # annotator2
AGREED_CSV = os.path.join(REPO, "agreed.csv")
CONFLICTS_CSV = os.path.join(REPO, "conflicts.csv")
OUT_DIR = os.path.join(REPO, "ground-truth-fl")

DIR_OF = {"Atish": A_DIR, "Eshgin": B_DIR}
ANNOTATOR_OF = {"Atish": "annotator1", "Eshgin": "annotator2"}


def load(directory: str, iid: str) -> dict:
    with open(os.path.join(directory, iid + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


def root_cause_of(doc: dict) -> list[dict]:
    return [{"file": loc.get("file", ""), "line": loc.get("line"),
             "statement": loc.get("statement", "")}
            for loc in (doc.get("root_cause") or [])]


def reasoning_of(doc: dict) -> str:
    return str(doc.get("reasoning") or "")


def write_gt(out_dir: str, iid: str, root_cause, confidence, comments, reasoning) -> None:
    obj = {
        "instance_id": iid,
        "root_cause": root_cause,
        "confidence": confidence,
        "comments": comments,
        "reasoning": reasoning,
    }
    with open(os.path.join(out_dir, iid + ".json"), "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--agreed", default=AGREED_CSV)
    p.add_argument("--conflicts", default=CONFLICTS_CSV)
    p.add_argument("--out", default=OUT_DIR)
    args = p.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    out = args.out

    seen: dict[str, str] = {}
    warnings: list[str] = []
    n_agreed = n_conflict = 0

    # ---- agreed ----
    with open(args.agreed, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            iid = row["InstanceId"].strip()
            final = row["FinalReasoning"].strip()
            if not iid:
                continue
            if final not in ("Both", "Atish", "Eshgin"):
                warnings.append(f"agreed {iid}: unexpected FinalReasoning={final!r}, skipped")
                continue
            seen[iid] = "agreed"
            a, b = load(A_DIR, iid), load(B_DIR, iid)
            reasoning = {
                "annotator1": reasoning_of(a) if final in ("Both", "Atish") else "",
                "annotator2": reasoning_of(b) if final in ("Both", "Eshgin") else "",
            }
            write_gt(out, iid, root_cause_of(a), a.get("confidence"),
                     "both agreed", reasoning)
            n_agreed += 1

    # ---- conflicts ----
    with open(args.conflicts, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            iid = row["Instance ID"].strip()
            who = row["Final_FL"].strip()
            if not iid:
                continue
            if who not in DIR_OF:
                warnings.append(f"conflict {iid}: unexpected Final_FL={who!r}, skipped")
                continue
            if iid in seen:
                warnings.append(f"conflict {iid}: also in agreed.csv, overwriting")
            seen[iid] = "conflict"
            src = load(DIR_OF[who], iid)
            reasoning = {
                "annotator1": reasoning_of(src) if who == "Atish" else "",
                "annotator2": reasoning_of(src) if who == "Eshgin" else "",
            }
            write_gt(out, iid, root_cause_of(src), src.get("confidence"),
                     ANNOTATOR_OF[who], reasoning)
            n_conflict += 1

    print(f"wrote {n_agreed + n_conflict} ground-truth files to {out}")
    print(f"  agreed:    {n_agreed}")
    print(f"  conflict:  {n_conflict}")
    if warnings:
        print(f"\n{len(warnings)} warning(s):")
        for w in warnings:
            print(f"  {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
