#!/usr/bin/env python3
"""Verify each ground-truth (file, line, statement) against the real source.

For every row of ground-truth-fl.csv we read the file at the instance's
base_commit (via ``git show <base_commit>:<file>``), pull the line at the
recorded line number, and classify how the recorded statement relates to the
real source.

Categories (first that applies wins):
  agree with source
    match       - source line, stripped, equals the recorded statement.
    whitespace  - equal after collapsing internal whitespace.
    multiline   - statement is the full logical line spanning several physical
                  lines starting at that line number (the common case for
                  wrapped conditions / calls).
    quote_diff  - equal after normalizing quote style (' vs ") + whitespace.
  needs review
    line_offset - statement text is at a *nearby* line, not the recorded one
                  (detail = actual line and delta).
    paraphrase  - recorded statement is shorthand (contains '...'), not literal.
    mismatch    - genuinely different text at and around that line.
  error / no_location - file/line/commit/repo unreadable, or blank location.

Outputs a per-row result CSV and prints a summary.

Usage:
    python check_statements.py
    python check_statements.py --csv ground-truth-fl.csv --repos repos --window 10
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
import sys
from collections import Counter

REPO = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV = os.path.join(REPO, "ground-truth-fl.csv")
DEFAULT_REPOS = os.path.join(REPO, "repos")
DEFAULT_OUT = os.path.join(REPO, "statement_check.csv")

OUT_COLUMNS = ["instance_id", "base_commit", "file", "line",
               "csv_statement", "repo_line", "status", "detail"]

AGREE = {"match", "whitespace", "multiline", "quote_diff"}
REVIEW = {"line_offset", "paraphrase", "mismatch"}


def repo_name(instance_id: str) -> str:
    """astropy__astropy-7606 -> astropy ; sphinx-doc__sphinx-8435 -> sphinx."""
    rest = instance_id.split("__", 1)[1] if "__" in instance_id else instance_id
    return re.sub(r"-\d+$", "", rest)


def collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def nospace(s: str) -> str:
    return re.sub(r"\s+", "", s)


def qunify(s: str) -> str:
    return s.replace('"', "'")


def qnorm(s: str) -> str:
    """Collapse whitespace and unify quote style."""
    return collapse(qunify(s))


def show_file(repo_path: str, commit: str, path: str, cache: dict):
    """Return (lines|None, error|None) for file `path` at `commit`."""
    key = (repo_path, commit, path)
    if key in cache:
        return cache[key]
    if not os.path.isdir(repo_path):
        res = (None, "repo_missing")
    else:
        p = subprocess.run(["git", "-C", repo_path, "show", f"{commit}:{path}"],
                           capture_output=True, text=True)
        res = ((None, "path_or_commit_missing") if p.returncode
               else (p.stdout.split("\n"), None))
    cache[key] = res
    return res


def classify(lines: list[str], n: int, stmt: str, window: int):
    """Return (status, repo_line, detail)."""
    src = lines[n - 1]
    s_src = src.strip()
    if s_src == stmt.strip():
        return "match", s_src, ""
    if collapse(src) == collapse(stmt) or nospace(src) == nospace(stmt):
        return "whitespace", s_src, ""

    # multiline: logical line wrapped over >=2 physical lines starting here
    # (whitespace-insensitive, since wrapping is ambiguous around punctuation).
    buf = [src]
    for i in range(n, min(len(lines), n - 1 + 25)):
        buf.append(lines[i])
        joined = " ".join(buf)
        if nospace(joined) == nospace(stmt) or nospace(qunify(joined)) == nospace(qunify(stmt)):
            return "multiline", s_src, f"spans {len(buf)} lines"

    if qnorm(src) == qnorm(stmt):
        return "quote_diff", s_src, ""

    # line_offset: exact/quote match at a nearby line
    for d in range(1, window + 1):
        for j in (n - 1 - d, n - 1 + d):
            if 0 <= j < len(lines) and (collapse(lines[j]) == collapse(stmt)
                                        or qnorm(lines[j]) == qnorm(stmt)):
                return "line_offset", src.strip(), f"actual line {j + 1} (Δ{j + 1 - n:+d})"

    if "..." in stmt:
        return "paraphrase", src.strip(), "recorded statement is shorthand"
    return "mismatch", src.strip(), ""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--csv", default=DEFAULT_CSV)
    p.add_argument("--repos", default=DEFAULT_REPOS)
    p.add_argument("--out", default=DEFAULT_OUT)
    p.add_argument("--window", type=int, default=10,
                   help="± lines to search for a line_offset (default 10)")
    args = p.parse_args(argv)

    with open(args.csv, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    cache: dict = {}
    results = []
    for r in rows:
        iid, commit = r["instance_id"], r.get("base_commit", "")
        path, line_s, stmt = r.get("file", ""), r.get("line", ""), r.get("statements", "")
        out = {"instance_id": iid, "base_commit": commit, "file": path,
               "line": line_s, "csv_statement": stmt, "repo_line": "",
               "status": "", "detail": ""}

        if not path or not line_s:
            out["status"] = "no_location"
        elif not commit:
            out["status"] = "error:no_base_commit"
        else:
            lines, err = show_file(os.path.join(args.repos, repo_name(iid)),
                                   commit, path, cache)
            if err:
                out["status"] = f"error:{err}"
            elif not line_s.isdigit():
                out["status"] = "error:bad_line"
            elif not (1 <= int(line_s) <= len(lines)):
                out["status"] = "error:line_out_of_range"
            else:
                out["status"], out["repo_line"], out["detail"] = classify(
                    lines, int(line_s), stmt, args.window)
        results.append(out)

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=OUT_COLUMNS)
        w.writeheader()
        w.writerows(results)

    # ---- summary ----
    counts = Counter(r["status"] for r in results)
    total = len(results)
    n_inst = len({r["instance_id"] for r in results})
    agree = sum(counts.get(k, 0) for k in AGREE)
    review = sum(counts.get(k, 0) for k in REVIEW)
    checked = agree + review

    print(f"\nchecked {total} location rows across {n_inst} instances")
    print("\nAGREE WITH SOURCE")
    for k in ("match", "whitespace", "multiline", "quote_diff"):
        print(f"  {k:12} {counts.get(k, 0)}")
    print(f"  {'subtotal':12} {agree}" + (f"  ({agree / checked:.1%} of checked)" if checked else ""))
    print("\nNEEDS REVIEW")
    for k in ("line_offset", "paraphrase", "mismatch"):
        print(f"  {k:12} {counts.get(k, 0)}")
    print(f"  {'subtotal':12} {review}")
    other = {k: v for k, v in counts.items() if k.startswith("error") or k == "no_location"}
    if other:
        print("\nOTHER")
        for k in sorted(other):
            print(f"  {k:22} {other[k]}")

    if review:
        print(f"\n=== {review} ROWS NEEDING REVIEW ===")
        for r in results:
            if r["status"] in REVIEW:
                print(f"\n[{r['status']}] {r['instance_id']}  {r['file']}:{r['line']}"
                      + (f"  — {r['detail']}" if r["detail"] else ""))
                print(f"  csv : {r['csv_statement']}")
                print(f"  repo: {r['repo_line']}")

    print(f"\nfull per-row results -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
