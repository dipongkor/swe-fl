#!/usr/bin/env python3
"""Evaluate model fault localization against the ground truth.

Each agent run writes ``agent-fl/swebench-fl-<model>-run<N>/<inst>/preds.json``
whose ``localization`` field has the SAME schema as the ground truth
(``root_cause: [{file, line, statement}]`` + ``reasoning``).  This script scores
those predicted locations against ``ground-truth-fl/<iid>.json`` at three
granularities and aggregates over the 3 runs per model.

Match rules (a prediction "hits" if ANY predicted location matches ANY GT one):
  * file       predicted file == GT file
  * line       same file AND the predicted line lies inside the GT statement's
               logical span (or the GT line lies inside the predicted
               statement's span, or the two line numbers are equal).  This
               matches our annotation unit -- "the statement containing the
               line" -- so a model citing a different physical line of the same
               multi-line statement still counts.  Exact line-number equality is
               reported separately as a stricter secondary.
  * statement  normalized statement text equal (whitespace/quote/comma-insensitive)

Missing / unparseable localizations are reported BOTH ways: as a miss out of the
full instance set, and excluded (rate over localization-present only), with a
coverage column.

line_hit is the primary metric for the cross-run aggregates (any@3 / majority@3
/ all@3), mirroring generate-result-summary.py.

Usage:
    python fl_eval.py
    python fl_eval.py --agent-fl agent-fl --gt-dir ground-truth-fl --repos repos
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import sys

from extract_statements import (repo_name, show_file, logical_spans,
                                 span_for_line, commit_map, collapse)

REPO = os.path.dirname(os.path.abspath(__file__))
DEFAULT_AGENT_FL = os.path.join(REPO, "agent-fl")
DEFAULT_GT_DIR = os.path.join(REPO, "ground-truth-fl")
DEFAULT_CSV = os.path.join(REPO, "ground-truth-fl.csv")
DEFAULT_REPOS = os.path.join(REPO, "repos")

COLUMN_LEGEND = """\
fl-summary.csv columns  (full reference: fl-columns.md)

Rows per model: run1/run2/run3, then mean, any@3 (hit in >=1 run),
majority@3 (>=2 runs), all@3 (all 3 runs).

Match rules (a "hit" = any predicted location matches any GT location):
  file   predicted file == GT file
  line   same file AND predicted line in GT statement's span (or GT line in
         predicted span, or equal line numbers)  -- "statement containing line"
  exact  same file AND predicted line == GT line exactly (subset of line)
  stmt   predicted statement == GT statement (whitespace/quote/comma-insensitive)

  model           model name
  run             run1/2/3 | mean | any@3 | majority@3 | all@3
  total           instances scored (130); denominator for *_rate
  evaluated       per-run: parseable localizations; aggregate: answered (>=1 run)
  file_hit        # instances with a file hit  (aggregate: hit in >=k runs)
  line_hit        # instances with a line hit  -- PRIMARY metric
  exact_line_hit  # instances with an exact-line hit  (per-run only)
  stmt_hit        # instances with a statement-text hit
  file_rate       file_hit / total
  line_rate       line_hit / total   (missing localization = miss)
  line_rate_eval  line_hit / evaluated   (quality when answered; not coverage)
  stmt_rate       stmt_hit / total
  precision       micro, line: matched predictions / all predictions
                  (aggregate: correct / (correct + spurious) surviving >=k runs)
  recall          micro, line: matched GT / all GT
                  (aggregate: GT matched in >=k runs / all GT)
  f1              harmonic mean of precision and recall
  resolved        # instances whose patch passed SWE-bench (report.json resolved)
  resolved_rate   resolved / total   (patch-fix success, independent of FL)

All *_rate and precision/recall/f1 are fractions in [0,1]; hits are counts."""

SUMMARY_CSV = os.path.join(REPO, "fl-summary.csv")
MATRIX_CSV = os.path.join(REPO, "fl-matrix.csv")
COUNTS_CSV = os.path.join(REPO, "fl-counts.csv")
DETAILS_CSV = os.path.join(REPO, "fl-details.csv")


def norm_stmt(s: str) -> str:
    """Whitespace/quote/comma-insensitive statement key for equality."""
    return re.sub(r"[\s,]+", "", (s or "").replace('"', "'"))


def norm_path(p: str) -> str:
    return (p or "").strip().lstrip("./").removeprefix("a/").removeprefix("b/")


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
def discover_runs(agent_fl: str):
    """[(model, run, dirpath)] for agent-fl/swebench-fl-<model>-run<N>."""
    pairs = []
    for path in glob.glob(os.path.join(agent_fl, "swebench-fl-*-run*")):
        if not os.path.isdir(path):
            continue
        m = re.match(r"swebench-fl-(.+)-run(\d+)$", os.path.basename(path))
        if m:
            pairs.append((m.group(1), int(m.group(2)), path))
    return sorted(pairs, key=lambda p: (p[0], p[1]))


def load_ground_truth(gt_dir: str):
    """{full_iid: [(file, line, statement), ...]} (integer lines only)."""
    gt = {}
    for path in sorted(glob.glob(os.path.join(gt_dir, "*.json"))):
        doc = json.load(open(path, encoding="utf-8"))
        iid = doc.get("instance_id") or os.path.splitext(os.path.basename(path))[0]
        locs = []
        for loc in doc.get("root_cause") or []:
            ln = loc.get("line")
            if isinstance(ln, int):
                locs.append((norm_path(loc.get("file", "")), ln,
                             loc.get("statement", "")))
        gt[iid] = locs
    return gt


def load_prediction(run_dir: str, short_inst: str):
    """(root_cause_locs, reasoning, status) from a run's preds.json.

    status in {"ok", "missing", "parse_error", "no_localization"}.
    locs = [(file, line_or_None, statement), ...].
    """
    pf = os.path.join(run_dir, short_inst, "preds.json")
    if not os.path.isfile(pf):
        return [], "", "missing"
    try:
        d = json.load(open(pf, encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return [], "", "missing"
    entry = next(iter(d.values()), {})
    if entry.get("localization_parse_error"):
        return [], "", "parse_error"
    loc = entry.get("localization")
    if not isinstance(loc, dict) or not (loc.get("root_cause")):
        return [], "", "no_localization"
    locs = []
    for r in loc.get("root_cause") or []:
        ln = r.get("line")
        locs.append((norm_path(r.get("file", "")),
                     ln if isinstance(ln, int) else None,
                     r.get("statement", "")))
    return locs, loc.get("reasoning", ""), "ok"


def load_resolved(run_dir: str, short_inst: str):
    """SWE-bench 'resolved' bool for one instance, or None if no report.json."""
    reports = glob.glob(os.path.join(run_dir, short_inst, "logs",
                                     "run_evaluation", "**", "report.json"),
                        recursive=True)
    if not reports:
        return None
    try:
        report = json.load(open(reports[0], encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    entry = next(iter(report.values()), {})
    return bool(entry.get("resolved", False))


# --------------------------------------------------------------------------- #
# matching
# --------------------------------------------------------------------------- #
def span_at(source: str, line, spans_cache: dict, key):
    """Logical-line span (s, e) containing `line`, or None."""
    if source is None or not isinstance(line, int):
        return None
    if key not in spans_cache:
        spans_cache[key] = logical_spans(source)
    return span_for_line(spans_cache[key], line)


def match_locations(pred_locs, gt_locs, iid, commit, repos, src_cache, spans_cache):
    """Return dict of hit booleans + line-level precision/recall/F1."""
    gt_files = {f for f, _, _ in gt_locs}

    def source_for(f):
        s, _ = show_file(os.path.join(repos, repo_name(iid)), commit, f, src_cache)
        return s

    # precompute GT spans
    gt_spans = []
    for gf, gl, _ in gt_locs:
        src = source_for(gf)
        gt_spans.append(span_at(src, gl, spans_cache, (iid, gf, "g", gl)))

    file_hit = any(pf in gt_files for pf, _, _ in pred_locs)

    matched_gt, matched_pred = set(), set()
    exact_line_hit = False
    for pi, (pf, pl, _) in enumerate(pred_locs):
        psrc = source_for(pf) if pf in gt_files else None
        pspan = span_at(psrc, pl, spans_cache, (iid, pf, "p", pl))
        for gi, (gf, gl, _) in enumerate(gt_locs):
            if pf != gf:
                continue
            gspan = gt_spans[gi]
            hit = (
                (pl is not None and pl == gl)
                or (gspan and pl is not None and gspan[0] <= pl <= gspan[1])
                or (pspan and pspan[0] <= gl <= pspan[1])
            )
            if hit:
                matched_gt.add(gi)
                matched_pred.add(pi)
                if pl is not None and pl == gl:
                    exact_line_hit = True

    gt_keys = {norm_stmt(s) for _, _, s in gt_locs if s}
    stmt_hit = any(norm_stmt(s) in gt_keys for _, _, s in pred_locs if s)

    # spurious = predicted locations that matched no GT (deduped by file,line)
    spurious = frozenset((pf, pl) for pi, (pf, pl, _) in enumerate(pred_locs)
                         if pi not in matched_pred)

    n_pred, n_gt = len(pred_locs), len(gt_locs)
    recall = len(matched_gt) / n_gt if n_gt else 0.0
    precision = len(matched_pred) / n_pred if n_pred else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) else 0.0)
    return {
        "matched_gt": frozenset(matched_gt),
        "spurious": spurious,
        "file_hit": file_hit,
        "line_hit": bool(matched_gt),
        "exact_line_hit": exact_line_hit,
        "stmt_hit": stmt_hit,
        "precision": precision, "recall": recall, "f1": f1,
        "matched_pred_n": len(matched_pred), "matched_gt_n": len(matched_gt),
        "n_pred": n_pred, "n_gt": n_gt,
    }


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--agent-fl", default=DEFAULT_AGENT_FL)
    p.add_argument("--gt-dir", default=DEFAULT_GT_DIR)
    p.add_argument("--csv", default=DEFAULT_CSV)
    p.add_argument("--repos", default=DEFAULT_REPOS)
    p.add_argument("--columns", action="store_true",
                   help="print fl-summary.csv column definitions and exit")
    args = p.parse_args(argv)

    if args.columns:
        print(COLUMN_LEGEND)
        return 0

    gt = load_ground_truth(args.gt_dir)
    commits = commit_map(args.csv)
    instances = sorted(gt)
    runs = discover_runs(args.agent_fl)
    if not runs:
        sys.exit(f"no swebench-fl-*-run* dirs under {args.agent_fl}")

    models = sorted({m for m, _, _ in runs})
    runs_of = {m: sorted(r for mm, r, _ in runs if mm == m) for m in models}
    dir_of = {(m, r): d for m, r, d in runs}

    src_cache, spans_cache = {}, {}
    # res[(model, run)][iid] = {hit dict, status}
    res: dict = {}
    details = []
    for m, r, d in runs:
        cell = {}
        for iid in instances:
            short = iid.split("__", 1)[-1]
            pred_locs, reasoning, status = load_prediction(d, short)
            resolved = load_resolved(d, short)
            commit = commits.get(iid, "")
            if status != "ok":
                cell[iid] = {"status": status, "line_hit": None, "resolved": resolved}
                details.append({"model": m, "run": r, "instance": iid,
                                "status": status, "file_hit": "", "line_hit": "",
                                "exact_line_hit": "", "stmt_hit": "",
                                "precision": "", "recall": "", "f1": "",
                                "n_pred": 0, "n_gt": len(gt[iid])})
                continue
            hit = match_locations(pred_locs, gt[iid], iid, commit, args.repos,
                                  src_cache, spans_cache)
            cell[iid] = {"status": "ok", "resolved": resolved, **hit}
            details.append({"model": m, "run": r, "instance": iid, "status": "ok",
                            "file_hit": hit["file_hit"], "line_hit": hit["line_hit"],
                            "exact_line_hit": hit["exact_line_hit"],
                            "stmt_hit": hit["stmt_hit"],
                            "precision": f"{hit['precision']:.3f}",
                            "recall": f"{hit['recall']:.3f}",
                            "f1": f"{hit['f1']:.3f}",
                            "n_pred": hit["n_pred"], "n_gt": hit["n_gt"]})
        res[(m, r)] = cell

    total = len(instances)

    def hits_over_runs(model, iid, key):
        """How many of a model's runs have hit `key` True for this instance."""
        return sum(1 for r in runs_of[model]
                   if res[(model, r)][iid].get(key) is True)

    def line_hits(model, iid):
        return hits_over_runs(model, iid, "line_hit")

    def agg_hit_count(model, key, k):
        """# instances whose `key` is hit in >= k of the model's runs."""
        return sum(1 for iid in instances if hits_over_runs(model, iid, key) >= k)

    def micro(correct, n_pred, n_gt):
        """Micro P/R/F1 from pooled counts (undefined ratios -> 0)."""
        precision = correct / n_pred if n_pred else 0.0
        recall = correct / n_gt if n_gt else 0.0
        f1 = (2 * precision * recall / (precision + recall)
              if (precision + recall) else 0.0)
        return precision, recall, f1

    def agg_prf(model, k):
        """Micro P/R/F1 under a k-of-R policy, pooled over instances the model
        localized in >= 1 run.  A GT location counts as recalled if matched in
        >= k runs; a spurious location survives (a false positive) if predicted
        in >= k runs.  Predicted total = surviving correct + surviving spurious."""
        correct = pred = ngt = 0
        for iid in instances:
            ok = [r for r in runs_of[model] if res[(model, r)][iid]["status"] == "ok"]
            if not ok:
                continue
            ngt += len(gt[iid])
            gcount, scount = {}, {}
            for r in ok:
                for gi in res[(model, r)][iid]["matched_gt"]:
                    gcount[gi] = gcount.get(gi, 0) + 1
                for loc in res[(model, r)][iid]["spurious"]:
                    scount[loc] = scount.get(loc, 0) + 1
            c = sum(1 for v in gcount.values() if v >= k)
            s = sum(1 for v in scount.values() if v >= k)
            correct += c
            pred += c + s
        return micro(correct, pred, ngt)

    def run_prf(model, r):
        """Micro P/R/F1 over that run's evaluated (localization-present) set.
        Precision counts matched predictions / all predictions; recall counts
        matched GT / all GT (the two numerators differ when several predicted
        locations map to one GT)."""
        cell = res[(model, r)]
        ok = [iid for iid in instances if cell[iid]["status"] == "ok"]
        mp = sum(cell[i]["matched_pred_n"] for i in ok)
        mg = sum(cell[i]["matched_gt_n"] for i in ok)
        pred = sum(cell[i]["n_pred"] for i in ok)
        ngt = sum(cell[i]["n_gt"] for i in ok)
        precision = mp / pred if pred else 0.0
        recall = mg / ngt if ngt else 0.0
        f1 = (2 * precision * recall / (precision + recall)
              if (precision + recall) else 0.0)
        return precision, recall, f1

    def resolved_hits(model, iid):
        return sum(1 for r in runs_of[model]
                   if res[(model, r)][iid].get("resolved") is True)

    def frac(num, den):
        return f"{num / den:.3f}" if den else "-"

    # ---- model summary: per-run + cross-run aggregates ----
    # all *_rate columns are fractions in [0, 1] (like precision/recall/f1).
    #   *_rate       = hits / total (130); missing localization counts as a miss
    #   line_rate_eval = line hits / evaluated (localization-present only)
    #   resolved_rate  = SWE-bench patch resolutions / total (130)
    header = ["model", "run", "total", "evaluated",
              "file_hit", "line_hit", "exact_line_hit", "stmt_hit",
              "file_rate", "line_rate", "line_rate_eval", "stmt_rate",
              "precision", "recall", "f1", "resolved", "resolved_rate"]
    rows = []
    print(f"{'model':22}{'run':>11}{'eval':>5}{'file':>5}{'line':>5}"
          f"{'stmt':>5}{'fileR':>7}{'lineR':>7}{'lnRev':>7}{'stmtR':>7}"
          f"{'P':>6}{'R':>6}{'F1':>6}{'reslv':>7}")
    for m in models:
        R = len(runs_of[m])
        for r in runs_of[m]:
            cell = res[(m, r)]
            evaluated = sum(1 for iid in instances if cell[iid]["status"] == "ok")
            fh = sum(1 for iid in instances if cell[iid].get("file_hit") is True)
            lh = sum(1 for iid in instances if cell[iid].get("line_hit") is True)
            eh = sum(1 for iid in instances if cell[iid].get("exact_line_hit") is True)
            sh = sum(1 for iid in instances if cell[iid].get("stmt_hit") is True)
            rv = sum(1 for iid in instances if cell[iid].get("resolved") is True)
            pr, rc, f1 = run_prf(m, r)
            rows.append([m, f"run{r}", total, evaluated, fh, lh, eh, sh,
                         frac(fh, total), frac(lh, total), frac(lh, evaluated),
                         frac(sh, total), f"{pr:.3f}", f"{rc:.3f}", f"{f1:.3f}",
                         rv, frac(rv, total)])
            print(f"{m:22}{('run'+str(r)):>11}{evaluated:>5}{fh:>5}{lh:>5}{sh:>5}"
                  f"{frac(fh,total):>7}{frac(lh,total):>7}{frac(lh,evaluated):>7}"
                  f"{frac(sh,total):>7}{pr:>6.2f}{rc:>6.2f}{f1:>6.2f}"
                  f"{frac(rv,total):>7}")

        # ---- cross-run aggregates ----
        answered = sum(1 for iid in instances
                       if any(res[(m, r)][iid]["status"] == "ok" for r in runs_of[m]))
        # mean row: average of per-run rates and per-run P/R/F1
        def per_run_rate(key, den_key):
            vals = []
            for r in runs_of[m]:
                cell = res[(m, r)]
                num = sum(1 for iid in instances if cell[iid].get(key) is True)
                den = (total if den_key == "total"
                       else sum(1 for iid in instances if cell[iid]["status"] == "ok"))
                vals.append(num / den if den else 0.0)
            return sum(vals) / len(vals) if vals else 0.0
        prf_runs = [run_prf(m, r) for r in runs_of[m]]
        mpr = sum(x[0] for x in prf_runs) / R
        mrc = sum(x[1] for x in prf_runs) / R
        mf1 = sum(x[2] for x in prf_runs) / R
        m_file, m_line = per_run_rate("file_hit", "total"), per_run_rate("line_hit", "total")
        m_line_ev = per_run_rate("line_hit", "eval")
        m_stmt, m_res = per_run_rate("stmt_hit", "total"), per_run_rate("resolved", "total")
        rows.append([m, "mean", total, "-", "-", "-", "-", "-",
                     f"{m_file:.3f}", f"{m_line:.3f}", f"{m_line_ev:.3f}",
                     f"{m_stmt:.3f}", f"{mpr:.3f}", f"{mrc:.3f}", f"{mf1:.3f}",
                     "-", f"{m_res:.3f}"])
        print(f"{m:22}{'mean':>11}{'-':>5}{'-':>5}{'-':>5}{'-':>5}"
              f"{m_file:>7.3f}{m_line:>7.3f}{m_line_ev:>7.3f}{m_stmt:>7.3f}"
              f"{mpr:>6.2f}{mrc:>6.2f}{mf1:>6.2f}{m_res:>7.3f}")

        for label, k in [(f"any@{R}", 1), (f"majority@{R}", R // 2 + 1),
                         (f"all@{R}", R)]:
            fh = agg_hit_count(m, "file_hit", k)
            lh = agg_hit_count(m, "line_hit", k)
            sh = agg_hit_count(m, "stmt_hit", k)
            rv = sum(1 for iid in instances if resolved_hits(m, iid) >= k)
            pr, rc, f1 = agg_prf(m, k)
            rows.append([m, label, total, answered, fh, lh, "-", sh,
                         frac(fh, total), frac(lh, total), frac(lh, answered),
                         frac(sh, total), f"{pr:.3f}", f"{rc:.3f}", f"{f1:.3f}",
                         rv, frac(rv, total)])
            print(f"{m:22}{label:>11}{answered:>5}{fh:>5}{lh:>5}{sh:>5}"
                  f"{frac(fh,total):>7}{frac(lh,total):>7}{frac(lh,answered):>7}"
                  f"{frac(sh,total):>7}{pr:>6.2f}{rc:>6.2f}{f1:>6.2f}"
                  f"{frac(rv,total):>7}")
        print()

    with open(SUMMARY_CSV, "w", newline="") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)

    # ---- per-instance matrix (line_hit) ----
    col_pairs = [(m, r) for m in models for r in runs_of[m]]
    with open(MATRIX_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["instance"] + [f"{m}/run{r}" for m, r in col_pairs])
        for iid in instances:
            row = [iid]
            for m, r in col_pairs:
                c = res[(m, r)][iid]
                row.append(c["status"] if c.get("line_hit") is None
                           else str(c["line_hit"]))
            w.writerow(row)

    # ---- per-instance counts (k/N line_hit) ----
    with open(COUNTS_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["instance"] + models)
        for iid in instances:
            w.writerow([iid] + [f"{line_hits(m, iid)}/{len(runs_of[m])}"
                                for m in models])

    # ---- per (model,run,instance) details ----
    with open(DETAILS_CSV, "w", newline="") as f:
        cols = ["model", "run", "instance", "status", "file_hit", "line_hit",
                "exact_line_hit", "stmt_hit", "precision", "recall", "f1",
                "n_pred", "n_gt"]
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(details)

    print(f"Model summary (per-run + agg) -> {SUMMARY_CSV}")
    print(f"Per-instance matrix (line)    -> {MATRIX_CSV}")
    print(f"Per-instance counts (k/N)     -> {COUNTS_CSV}")
    print(f"Per-(model,run,inst) details  -> {DETAILS_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
