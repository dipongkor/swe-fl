#!/usr/bin/env python3
"""Extract the exact statement (single- or multi-line) that contains each line.

For every (file, line) in ground-truth-fl.csv we read the file at the instance's
base_commit and return the full *logical line* (= one Python statement) spanning
that physical line.  Python's ``tokenize`` gives logical lines directly, so a
wrapped condition / call / dict literal comes back whole, while compound-
statement headers and their bodies stay separate — which matches how a human
means "the statement at this line".

All ground-truth repos are Python, so no external parser (tree-sitter) is
needed; a non-.py file is reported as skipped.

Outputs:
  * statements_extracted.csv  - per location: current vs extracted statement,
    the line span, and whether it changed / needs a look.
  * statements_extracted.json - {instance_id: [{file, line, start_line,
    end_line, statement}, ...]} for programmatic use.

Usage:
    python extract_statements.py
    python extract_statements.py --csv ground-truth-fl.csv --repos repos
"""

from __future__ import annotations

import argparse
import csv
import glob
import io
import json
import os
import re
import subprocess
import sys
import textwrap
import tokenize

REPO = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV = os.path.join(REPO, "ground-truth-fl.csv")
DEFAULT_REPOS = os.path.join(REPO, "repos")
DEFAULT_GT = os.path.join(REPO, "ground-truth-fl")
OUT_CSV = os.path.join(REPO, "statements_extracted.csv")
OUT_JSON = os.path.join(REPO, "statements_extracted.json")

OUT_COLUMNS = ["instance_id", "base_commit", "file", "line",
               "start_line", "end_line", "n_lines",
               "current_statement", "extracted_statement", "note"]


def repo_name(instance_id: str) -> str:
    rest = instance_id.split("__", 1)[1] if "__" in instance_id else instance_id
    return re.sub(r"-\d+$", "", rest)


def collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def show_file(repo_path: str, commit: str, path: str, cache: dict):
    """(source|None, error|None) for file `path` at `commit`."""
    key = (repo_path, commit, path)
    if key in cache:
        return cache[key]
    if not os.path.isdir(repo_path):
        res = (None, "repo_missing")
    else:
        p = subprocess.run(["git", "-C", repo_path, "show", f"{commit}:{path}"],
                           capture_output=True, text=True)
        res = ((None, "path_or_commit_missing") if p.returncode else (p.stdout, None))
    cache[key] = res
    return res


def logical_spans(src: str) -> list[tuple[int, int]]:
    """List of (start_line, end_line) for each logical line (statement)."""
    spans, start = [], None
    skip = {tokenize.NL, tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT,
            tokenize.ENCODING, tokenize.ENDMARKER}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.NEWLINE:          # end of a logical line
                if start is not None:
                    spans.append((start, tok.start[0]))
                    start = None
            elif tok.type in skip:
                continue
            elif start is None:                       # first real token of a stmt
                start = tok.start[0]
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return spans


def span_for_line(spans: list[tuple[int, int]], line: int):
    for s, e in spans:
        if s <= line <= e:
            return s, e
    return None


def parse_line(line_s: str):
    """line must be a single integer; a list (data error) is ignored -> None."""
    line_s = line_s.strip()
    return int(line_s) if line_s.isdigit() else None


def extract(source: str, line: int):
    """Full statement text containing `line`; (text, start, end) or None."""
    lines = source.split("\n")
    span = span_for_line(logical_spans(source), line)
    if span is None:
        return None
    s, e = span
    block = "\n".join(lines[s - 1:e])
    return textwrap.dedent(block).strip("\n").rstrip(), s, e


def commit_map(csv_path: str) -> dict[str, str]:
    m: dict[str, str] = {}
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            m.setdefault(r["instance_id"], r.get("base_commit", ""))
    return m


def apply_ground_truth(args) -> int:
    """Rewrite each root_cause['statement'] to the verbatim source statement,
    but only where it does not already match.  Integer lines only; list/other
    lines are ignored.  Backs up each changed file to <name>.bak."""
    commits = commit_map(args.csv)
    cache: dict = {}
    changes, ignored, problems = [], [], []
    files_changed = 0

    for path in sorted(glob.glob(os.path.join(args.gt_dir, "*.json"))):
        with open(path, encoding="utf-8") as fh:
            orig_text = fh.read()
        doc = json.loads(orig_text)
        iid = doc.get("instance_id") or os.path.splitext(os.path.basename(path))[0]
        commit = commits.get(iid, "")
        if not commit:
            problems.append(f"{iid}: no base_commit in {os.path.basename(args.csv)}")
            continue

        file_changed = False
        for loc in doc.get("root_cause") or []:
            ln, f = loc.get("line"), loc.get("file", "")
            if not isinstance(ln, int):
                ignored.append(f"{iid}  {f}:{ln}  (line not int)")
                continue
            if not f.endswith(".py"):
                problems.append(f"{iid}  {f}  (not python)")
                continue
            src, err = show_file(os.path.join(args.repos, repo_name(iid)),
                                 commit, f, cache)
            if err:
                problems.append(f"{iid}  {f}  ({err})")
                continue
            got = extract(src, ln)
            if got is None:
                problems.append(f"{iid}  {f}:{ln}  (no statement at line)")
                continue
            verbatim = got[0]
            if loc.get("statement") != verbatim:
                changes.append((iid, f, ln, loc.get("statement"), verbatim))
                loc["statement"] = verbatim
                file_changed = True

        if file_changed:
            with open(path + ".bak", "w", encoding="utf-8") as bf:
                bf.write(orig_text)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            files_changed += 1

    print(f"\nreplaced {len(changes)} statement(s) across {files_changed} file(s)")
    for iid, f, ln, old, new in changes:
        print(f"\n{iid}  {f}:{ln}")
        print(f"  old: {collapse(old or '')[:130]}")
        print(f"  new: {collapse(new)[:130]}" + ("  [multiline]" if "\n" in new else ""))
    if ignored:
        print(f"\nignored {len(ignored)} non-integer line(s):")
        for x in ignored:
            print(f"  {x}")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for x in problems:
            print(f"  {x}")
    print(f"\nbackups written as <file>.bak next to each changed file")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--csv", default=DEFAULT_CSV)
    p.add_argument("--repos", default=DEFAULT_REPOS)
    p.add_argument("--gt-dir", default=DEFAULT_GT,
                   help="ground-truth JSON dir (for --apply)")
    p.add_argument("--apply", action="store_true",
                   help="rewrite ground-truth statements to verbatim source "
                        "where they differ (backs up to <file>.bak)")
    p.add_argument("--out-csv", default=OUT_CSV)
    p.add_argument("--out-json", default=OUT_JSON)
    args = p.parse_args(argv)

    if args.apply:
        return apply_ground_truth(args)

    with open(args.csv, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    cache: dict = {}
    results, by_instance = [], {}
    for r in rows:
        iid, commit = r["instance_id"], r.get("base_commit", "")
        path, line_s, cur = r.get("file", ""), r.get("line", ""), r.get("statements", "")
        out = {"instance_id": iid, "base_commit": commit, "file": path,
               "line": line_s, "start_line": "", "end_line": "", "n_lines": "",
               "current_statement": cur, "extracted_statement": "", "note": ""}

        line = parse_line(line_s)
        if not path or line is None:
            out["note"] = "no_location" if not path else "line_not_int (ignored)"
            results.append(out)
            continue
        if not path.endswith(".py"):
            out["note"] = "not_python (needs tree-sitter)"
            results.append(out)
            continue
        if not commit:
            out["note"] = "no_base_commit"
            results.append(out)
            continue

        source, err = show_file(os.path.join(args.repos, repo_name(iid)),
                                commit, path, cache)
        if err:
            out["note"] = err
            results.append(out)
            continue

        got = extract(source, line)
        if got is None:
            out["note"] = "no_statement_at_line (blank/comment?)"
            results.append(out)
            continue

        stmt, s, e = got
        out["extracted_statement"] = stmt
        out["start_line"], out["end_line"], out["n_lines"] = s, e, e - s + 1
        if e > s:
            out["note"] = "multiline"
        if cur and collapse(cur) not in collapse(stmt):
            # the recorded statement text isn't contained in the extracted
            # statement -> the line number may point at the wrong statement
            out["note"] = (out["note"] + "; " if out["note"] else "") + "current_not_contained"

        results.append(out)
        by_instance.setdefault(iid, []).append(
            {"file": path, "line": line_s, "start_line": s,
             "end_line": e, "statement": stmt})

    with open(args.out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=OUT_COLUMNS)
        w.writeheader()
        w.writerows(results)
    with open(args.out_json, "w", encoding="utf-8") as fh:
        json.dump(by_instance, fh, indent=2, ensure_ascii=False)

    # ---- summary ----
    total = len(results)
    extracted = sum(1 for r in results if r["extracted_statement"])
    multiline = sum(1 for r in results if "multiline" in r["note"])
    flagged = [r for r in results if "current_not_contained" in r["note"]]
    problems = [r for r in results if not r["extracted_statement"]]

    print(f"\nextracted statements for {extracted}/{total} locations "
          f"({multiline} multi-line)")
    if problems:
        print(f"\ncould not extract ({len(problems)}):")
        for r in problems:
            print(f"  {r['instance_id']}  {r['file']}:{r['line']}  -> {r['note']}")
    if flagged:
        print(f"\nrecorded statement NOT inside the extracted statement "
              f"({len(flagged)}) - line number may be off:")
        for r in flagged:
            print(f"  {r['instance_id']}  {r['file']}:{r['line']} "
                  f"(stmt spans {r['start_line']}-{r['end_line']})")
            print(f"    current  : {r['current_statement']}")
            print(f"    extracted: {collapse(r['extracted_statement'])[:120]}")

    print(f"\n-> {args.out_csv}\n-> {args.out_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
