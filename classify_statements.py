#!/usr/bin/env python3
"""Bucket each ground-truth location by how its statement relates to source.

Reuses the verbatim extractor.  For every (file, line) it compares the recorded
statement to the statement actually containing that line at base_commit, and
writes three CSVs:

  statements-good.csv          recorded == extracted  (already verbatim)
  statements-safe-apply.csv    differs, but same statement reformatted
                               (collapsed multi-line / quotes / trailing comma)
                               -> `extract_statements.py --apply` is safe
  statements-unsafe-apply.csv  extracted balloons to a much larger enclosing
                               statement (sub-statement pointer), a paraphrase,
                               or an extraction error -> DO NOT auto-apply

Usage:
    python classify_statements.py
    python classify_statements.py --csv ground-truth-fl.csv --repos repos
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys

from extract_statements import repo_name, show_file, extract, parse_line, collapse

REPO = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV = os.path.join(REPO, "ground-truth-fl.csv")
DEFAULT_REPOS = os.path.join(REPO, "repos")

RATIO = 1.5  # extracted this-much-longer than recorded => balloon, not a reformat

COLUMNS = ["instance_id", "base_commit", "file", "line",
           "start_line", "end_line", "n_lines",
           "current_statement", "extracted_statement", "reason"]


def squash(s: str) -> str:
    return re.sub(r"\s+", "", s.replace('"', "'"))


def classify(cur: str, ext: str):
    """Return (bucket, reason).  bucket in {good, safe, unsafe}."""
    if cur.strip() == ext.strip():
        return "good", "exact match"
    if squash(cur) == squash(ext):
        return "safe", "whitespace/quote only"
    cN, eN = collapse(cur), collapse(ext)
    ratio = len(eN) / max(1, len(cN))
    if ratio <= RATIO:
        return "safe", f"same statement reformatted (x{ratio:.2f})"
    if cN and cN in eN:
        return "unsafe", f"sub-statement pointer, balloons x{ratio:.2f}"
    return "unsafe", f"differs / paraphrase (x{ratio:.2f})"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--csv", default=DEFAULT_CSV)
    p.add_argument("--repos", default=DEFAULT_REPOS)
    args = p.parse_args(argv)

    with open(args.csv, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    cache: dict = {}
    buckets: dict[str, list[dict]] = {"good": [], "safe": [], "unsafe": []}

    for r in rows:
        iid, commit = r["instance_id"], r.get("base_commit", "")
        path, line_s, cur = r.get("file", ""), r.get("line", ""), r.get("statements", "")
        out = {"instance_id": iid, "base_commit": commit, "file": path,
               "line": line_s, "start_line": "", "end_line": "", "n_lines": "",
               "current_statement": cur, "extracted_statement": "", "reason": ""}

        line = parse_line(line_s)
        if not path or line is None:
            out["reason"] = "no_location" if not path else "line_not_int"
            buckets["unsafe"].append(out); continue
        if not path.endswith(".py"):
            out["reason"] = "not_python"; buckets["unsafe"].append(out); continue
        if not commit:
            out["reason"] = "no_base_commit"; buckets["unsafe"].append(out); continue

        src, err = show_file(os.path.join(args.repos, repo_name(iid)),
                             commit, path, cache)
        if err:
            out["reason"] = err; buckets["unsafe"].append(out); continue
        got = extract(src, line)
        if got is None:
            out["reason"] = "no_statement_at_line"; buckets["unsafe"].append(out); continue

        stmt, s, e = got
        out["extracted_statement"] = stmt
        out["start_line"], out["end_line"], out["n_lines"] = s, e, e - s + 1
        bucket, reason = classify(cur, stmt)
        out["reason"] = reason
        buckets[bucket].append(out)

    files = {"good": "statements-good.csv",
             "safe": "statements-safe-apply.csv",
             "unsafe": "statements-unsafe-apply.csv"}
    for bucket, name in files.items():
        with open(os.path.join(REPO, name), "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(buckets[bucket])

    total = sum(len(v) for v in buckets.values())
    print(f"classified {total} location rows across "
          f"{len({r['instance_id'] for r in rows})} instances\n")
    print(f"  1. good (already verbatim)     {len(buckets['good']):>4}  -> {files['good']}")
    print(f"  2. not good, SAFE to --apply   {len(buckets['safe']):>4}  -> {files['safe']}")
    print(f"  3. not good, UNSAFE to --apply {len(buckets['unsafe']):>4}  -> {files['unsafe']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
