#!/usr/bin/env python3
"""Evaluate model *reasoning* against the ground-truth reasoning (trust axis 3).

For each agent run, ``preds.json``'s ``localization.reasoning`` is the model's
account of the fault mechanism.  This scores it against the ground-truth
reasoning (``ground-truth-fl/<iid>.json`` -> ``reasoning.{annotator1,
annotator2}``) on the same 4-level rubric used for inter-annotator agreement,
reusing the LLM jury in reasoning_judge.py.

The jury is BLIND to which side is the model: the ground-truth reasoning and the
model reasoning are fed as the two "annotators", order-swapped, so no position
or identity signal leaks.  Only the pairing and the data source change.

Design choices (see --help):
  * unit = (model, run, instance): every localized cell is judged, so reasoning
    alignment can be sliced by FL correctness (right mechanism with the wrong
    line, and vice-versa, are both visible).
  * --condition {all,line,file}: which cells to judge.  `all` judges every cell
    with a localization; `line`/`file` restrict to FL-correct cells.
  * --gt-reference {single,both}: `single` judges against one annotator
    (annotator1 preferred) - on agreed instances the two annotators' reasonings
    are themselves aligned, so a single reference suffices at half the cost;
    `both` judges against each and keeps the best-aligned verdict.
  * PRIMARY metric = binary %consistent (aligned+partial) vs %conflicting
    (divergent+contradictory); the aligned<->partial 4-way split is a
    position-sensitive diagnostic only (reported as aligned_4way).

Outputs (with an optional --tag suffix, for base vs transformed robustness sets):
  reasoning-summary.csv   per (model, run) + mean/any@3/majority@3 aggregates
  reasoning-cells.csv     per (model, run, instance): fl hits, per-annotator and
                          final alignment, abstain flag

Verdicts are cached on disk (reasoning_eval/verdict_cache.jsonl), so a run
resumes for free and re-runs cost nothing.

Usage:
    python reasoning_eval.py --dry-run
    python reasoning_eval.py --run
    python reasoning_eval.py --condition line --run
    python reasoning_eval.py --mock 3 --limit 5 --run     # offline pipeline test
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import sys
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import fl_eval as FE
import reasoning_judge as RJ

REPO = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(REPO, "reasoning_eval")
# redirect the reused jury's cache/raw/out to this tool's own directory so the
# annotator-agreement study's artifacts are never touched (separate process).
RJ.OUT_DIR = OUT_DIR
RJ.CACHE_FILE = os.path.join(OUT_DIR, "verdict_cache.jsonl")
RJ.RAW_FILE = os.path.join(OUT_DIR, "raw_results.json")

MANIFEST_FILE = os.path.join(OUT_DIR, "manifest.json")
CONFIG_FILE = os.path.join(OUT_DIR, "run_config.json")

LABELS = RJ.LABELS
LABEL_SET = RJ.LABEL_SET
MIN_CHARS = RJ.MIN_REASONING_CHARS
# ordinal rank ONLY for picking the best-aligned reference under --gt-reference both.
ALIGN_RANK = {"aligned": 3, "partial": 2, "divergent": 1, "contradictory": 0}
CONSISTENT = {"aligned", "partial"}


# --------------------------------------------------------------------------- #
# loading model reasoning + FL correctness + ground-truth reasoning
# --------------------------------------------------------------------------- #

def gt_reasoning(gt_dir: str) -> dict:
    """{instance_id: {"annotator1": str, "annotator2": str}}."""
    out = {}
    import glob
    for path in glob.glob(os.path.join(gt_dir, "*.json")):
        doc = json.load(open(path, encoding="utf-8"))
        iid = doc.get("instance_id") or os.path.splitext(os.path.basename(path))[0]
        r = doc.get("reasoning") or {}
        if isinstance(r, str):                       # tolerate a flat string
            r = {"annotator1": r, "annotator2": ""}
        out[iid] = {"annotator1": str(r.get("annotator1") or ""),
                    "annotator2": str(r.get("annotator2") or "")}
    return out


def gt_references(reasoning: dict, mode: str):
    """[(annotator_key, text)] to judge against; honours --gt-reference."""
    a1, a2 = reasoning.get("annotator1", ""), reasoning.get("annotator2", "")
    have = [(k, t) for k, t in (("annotator1", a1), ("annotator2", a2))
            if len(t.strip()) >= MIN_CHARS]
    if not have:
        return []
    return have[:1] if mode == "single" else have


# --------------------------------------------------------------------------- #
# request building
# --------------------------------------------------------------------------- #

def build_specs(args, jurors):
    """Build jury requests over qualifying cells; return (specs, manifest, skips)."""
    gt_locs = FE.load_ground_truth(args.gt_dir)
    gt_reas = gt_reasoning(args.gt_dir)
    commits = FE.commit_map(args.csv)
    instances = sorted(gt_locs)
    runs = FE.discover_runs(args.agent_fl)
    if not runs:
        sys.exit(f"no swebench-fl-*-run* dirs under {args.agent_fl}")
    if args.limit:
        instances = instances[:args.limit]

    src_cache, spans_cache = {}, {}
    specs, manifest = [], {}
    skips = Counter()
    idx = 0
    for m, r, d in runs:
        for iid in instances:
            short = iid.split("__", 1)[-1]
            pred_locs, reasoning, status = FE.load_prediction(d, short)
            if status != "ok":
                skips["no_localization"] += 1
                continue
            if len(reasoning.strip()) < MIN_CHARS:
                skips["model_reasoning_too_short"] += 1
                continue
            fl = FE.match_locations(pred_locs, gt_locs[iid], iid,
                                    commits.get(iid, ""), args.repos,
                                    src_cache, spans_cache)
            if args.condition == "line" and not fl["line_hit"]:
                skips["fl_line_miss"] += 1
                continue
            if args.condition == "file" and not fl["file_hit"]:
                skips["fl_file_miss"] += 1
                continue
            refs = gt_references(gt_reas.get(iid, {}), args.gt_reference)
            if not refs:
                skips["no_gt_reasoning"] += 1
                continue

            for ann_key, ref_text in refs:
                # ordering 0: reference is Annotator 1; ordering 1: swapped.
                for ordering, (r1, r2) in enumerate(
                        [(ref_text, reasoning), (reasoning, ref_text)]):
                    user = RJ.build_user_content(r1, r2)
                    for juror in jurors:
                        for rep in range(args.repeats):
                            cid = f"c{idx}"
                            idx += 1
                            spec = {"cid": cid, "user": user,
                                    "instance_id": iid, "ordering": ordering,
                                    "provider": juror["provider"],
                                    "model": juror["model"],
                                    "temperature": juror.get("temperature"),
                                    "repeat": rep}
                            specs.append(spec)
                            manifest[cid] = {"model_under_test": m, "run": r,
                                             "instance": iid, "annotator": ann_key,
                                             "ordering": ordering, "repeat": rep,
                                             "provider": juror["provider"],
                                             "model": juror["model"],
                                             "fl_line_hit": fl["line_hit"],
                                             "fl_file_hit": fl["file_hit"]}
    return specs, manifest, skips, runs


# --------------------------------------------------------------------------- #
# run (reuse the jury's cached, retrying request path)
# --------------------------------------------------------------------------- #

def run_specs(specs, use_cache):
    cache = RJ.load_cache() if use_cache else {}
    if cache:
        print(f"  cache: {len(cache)} verdict(s) on disk")
    sems = {p: threading.Semaphore(n)
            for p, n in RJ.PROVIDER_CONCURRENCY.items()}
    workers = sum(RJ.PROVIDER_CONCURRENCY.get(p, 4)
                  for p in {s["provider"] for s in specs})
    raw, done, hits, total = {}, 0, 0, len(specs)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = [ex.submit(RJ.run_request, s, sems, cache, use_cache) for s in specs]
        for fut in as_completed(futs):
            res = fut.result()
            raw[res["cid"]] = res
            done += 1
            hits += bool(res.get("cached"))
            if done % 50 == 0 or done == total:
                errs = sum(1 for v in raw.values() if "alignment" not in v)
                print(f"  {done}/{total} verdicts ({hits} cached, {errs} failed)")
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(RJ.RAW_FILE, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, indent=2, ensure_ascii=False)
    return raw


# --------------------------------------------------------------------------- #
# aggregation
# --------------------------------------------------------------------------- #

def _panel(labels_per_juror):
    """Panel strict majority over jurors' own strict-majority labels."""
    jlabels = [RJ.strict_majority(labs) for labs in labels_per_juror.values()]
    jlabels = [l for l in jlabels if l is not None]
    return RJ.strict_majority(jlabels)


def panel_label(votes):
    """4-way panel label (diagnostic); None = abstain."""
    good = [v for v in votes if v.get("alignment") in LABEL_SET]
    if not good:
        return None
    by_juror = defaultdict(list)
    for v in good:
        by_juror[f"{v['provider']}:{v['model']}"].append(v["alignment"])
    return _panel(by_juror)


def panel_label_binary(votes):
    """PRIMARY binary panel label (consistent/conflicting), order-invariant."""
    good = [v for v in votes if v.get("alignment") in LABEL_SET]
    if not good:
        return None
    by_juror = defaultdict(list)
    for v in good:
        by_juror[f"{v['provider']}:{v['model']}"].append(RJ.BINARY_OF[v["alignment"]])
    return _panel(by_juror)


BIN_RANK = {"consistent": 1, "conflicting": 0}


def aggregate(raw, manifest):
    """-> cells keyed (model, run, instance): fl hits, per-annotator 4-way and
    binary labels, and best-of-annotators final (4-way diagnostic) + final_binary
    (PRIMARY)."""
    by_cell_ann = defaultdict(list)
    fl_of = {}
    for cid, ctx in manifest.items():
        v = raw.get(cid, {})
        key = (ctx["model_under_test"], ctx["run"], ctx["instance"], ctx["annotator"])
        by_cell_ann[key].append({**ctx, **v})
        fl_of[(ctx["model_under_test"], ctx["run"], ctx["instance"])] = (
            ctx["fl_line_hit"], ctx["fl_file_hit"])

    per_ann = defaultdict(dict)          # (m,r,iid) -> {ann: 4way}
    per_ann_bin = defaultdict(dict)      # (m,r,iid) -> {ann: binary}
    for (m, r, iid, ann), votes in by_cell_ann.items():
        per_ann[(m, r, iid)][ann] = panel_label(votes)
        per_ann_bin[(m, r, iid)][ann] = panel_label_binary(votes)

    cells = {}
    for cell, ann_labels in per_ann.items():
        labeled = {a: l for a, l in ann_labels.items() if l in LABEL_SET}
        if labeled:
            best_ann = max(labeled, key=lambda a: ALIGN_RANK[labeled[a]])
            final = labeled[best_ann]
        else:
            best_ann, final = None, None
        # PRIMARY binary: model counts as consistent if consistent with EITHER annotator
        blabeled = {a: l for a, l in per_ann_bin[cell].items()
                    if l in set(RJ.BINARY_LABELS)}
        final_binary = (max(blabeled.values(), key=lambda l: BIN_RANK[l])
                        if blabeled else None)
        line_hit, file_hit = fl_of[cell]
        cells[cell] = {"fl_line_hit": line_hit, "fl_file_hit": file_hit,
                       "per_annotator": ann_labels,
                       "per_annotator_binary": per_ann_bin[cell],
                       "chosen_annotator": best_ann,
                       "final": final, "final_binary": final_binary}
    return cells


# --------------------------------------------------------------------------- #
# summary
# --------------------------------------------------------------------------- #

def write_outputs(cells, runs, tag):
    suffix = f"-{tag}" if tag else ""
    summary_csv = os.path.join(REPO, f"reasoning-summary{suffix}.csv")
    cells_csv = os.path.join(REPO, f"reasoning-cells{suffix}.csv")

    models = sorted({m for m, _, _ in runs})
    runs_of = {m: sorted(r for mm, r, _ in runs if mm == m) for m in models}

    # ---- cells csv (columns `alignment`/`consistent`/`coded` kept for trust_axes) ----
    with open(cells_csv, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["model", "run", "instance", "fl_line_hit", "fl_file_hit",
                    "binary", "consistent", "alignment", "chosen_annotator",
                    "annotator1", "annotator2", "coded"])
        for (m, r, iid), c in sorted(cells.items()):
            fb, fin = c["final_binary"], c["final"]
            w.writerow([m, f"run{r}", iid, c["fl_line_hit"], c["fl_file_hit"],
                        fb or "", (fb == "consistent") if fb else "",
                        fin or "", c["chosen_annotator"] or "",
                        c["per_annotator"].get("annotator1") or "",
                        c["per_annotator"].get("annotator2") or "",
                        fb is not None])

    def frac(a, b):
        return f"{a / b:.3f}" if b else "-"

    # coded = has a PRIMARY (binary) label
    def coded_of(m, r):
        return [c for (mm, rr, _), c in cells.items()
                if mm == m and rr == r and c["final_binary"] is not None]

    def consistent_runs(m, iid):
        return sum(1 for r in runs_of[m]
                   if cells.get((m, r, iid), {}).get("final_binary") == "consistent")

    # ---- per (model,run) + aggregates :: PRIMARY = consistent/conflicting ----
    header = ["model", "run", "attempted", "coded", "abstained",
              "consistent", "conflicting", "pct_consistent", "pct_conflicting",
              "aligned_4way", "pct_aligned_4way"]
    rows = []
    print(f"{'model':22}{'run':>11}{'attn':>6}{'code':>6}{'abst':>6}"
          f"{'cons':>6}{'conf':>6}{'%cons':>8}{'%conf':>8}{'%algn4':>8}")

    for m in models:
        R = len(runs_of[m])
        for r in runs_of[m]:
            attempted = sum(1 for (mm, rr, _) in cells if mm == m and rr == r)
            coded = coded_of(m, r)
            n = len(coded)
            cons = sum(1 for c in coded if c["final_binary"] == "consistent")
            conf = sum(1 for c in coded if c["final_binary"] == "conflicting")
            # 4-way aligned (diagnostic), over cells with a 4-way label
            c4 = [c for c in coded if c["final"] is not None]
            al = sum(1 for c in c4 if c["final"] == "aligned")
            rows.append([m, f"run{r}", attempted, n, attempted - n, cons, conf,
                         frac(cons, n), frac(conf, n), al, frac(al, len(c4))])
            print(f"{m:22}{('run'+str(r)):>11}{attempted:>6}{n:>6}{attempted - n:>6}"
                  f"{cons:>6}{conf:>6}{frac(cons, n):>8}{frac(conf, n):>8}"
                  f"{frac(al, len(c4)):>8}")

        insts = sorted({iid for (mm, rr, iid) in cells if mm == m})
        judged = [i for i in insts
                  if any(cells.get((m, r, i), {}).get("final_binary") is not None
                         for r in runs_of[m])]
        nj = len(judged)
        run_co = [(sum(1 for c in coded_of(m, r) if c["final_binary"] == "consistent"),
                   len(coded_of(m, r))) for r in runs_of[m]]
        mean_co = sum(a / b for a, b in run_co if b) / R
        rows.append([m, "mean", nj, "-", "-", "-", "-", f"{mean_co:.3f}", "-", "-", "-"])
        print(f"{m:22}{'mean':>11}{nj:>6}{'-':>6}{'-':>6}{'-':>6}{'-':>6}"
              f"{mean_co:>8.3f}{'-':>8}{'-':>8}")
        for label, k in [(f"any@{R}", 1), (f"majority@{R}", R // 2 + 1),
                         (f"all@{R}", R)]:
            co = sum(1 for i in judged if consistent_runs(m, i) >= k)
            rows.append([m, label, nj, "-", "-", co, "-", frac(co, nj), "-", "-", "-"])
            print(f"{m:22}{label:>11}{nj:>6}{'-':>6}{'-':>6}{co:>6}{'-':>6}"
                  f"{frac(co, nj):>8}{'-':>8}{'-':>8}")
        print()

    with open(summary_csv, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)

    # ---- FL slice: is reasoning CONSISTENT when the line is right vs wrong? ----
    print("-- reasoning CONSISTENCY sliced by FL line-hit (primary-coded cells) --")
    print(f"  {'model':22}{'line-hit %consistent':>22}{'line-miss %consistent':>23}")
    for m in models:
        hit = [c for (mm, _, _), c in cells.items()
               if mm == m and c["final_binary"] is not None and c["fl_line_hit"]]
        miss = [c for (mm, _, _), c in cells.items()
                if mm == m and c["final_binary"] is not None and not c["fl_line_hit"]]
        hc = sum(1 for c in hit if c["final_binary"] == "consistent")
        mc = sum(1 for c in miss if c["final_binary"] == "consistent")
        print(f"  {m:22}{f'{hc}/{len(hit)} = ' + frac(hc, len(hit)):>22}"
              f"{f'{mc}/{len(miss)} = ' + frac(mc, len(miss)):>23}")

    print(f"\n-> {summary_csv}")
    print(f"-> {cells_csv}")


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def cost_estimate(specs, jurors):
    per_in, per_out = 1200, 500
    approx = len(specs) * (per_in / 1e6 * 5.0 + per_out / 1e6 * 25.0)
    print(f"  {len(specs)} jury requests across {len(jurors)} juror(s)")
    print(f"  rough order-of-magnitude cost: ${approx:.2f} "
          "(Opus-tier stand-in; cache + cheaper jurors lower it)")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--agent-fl", default=FE.DEFAULT_AGENT_FL)
    p.add_argument("--gt-dir", default=FE.DEFAULT_GT_DIR)
    p.add_argument("--csv", default=FE.DEFAULT_CSV)
    p.add_argument("--repos", default=FE.DEFAULT_REPOS)
    p.add_argument("--condition", choices=["all", "line", "file"], default="all",
                   help="which localized cells to judge (default: all)")
    p.add_argument("--gt-reference", choices=["single", "both"], default="single",
                   help="judge against one annotator or keep the best of both")
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--jurors", default=None,
                   help="comma-separated provider subset (default: all)")
    p.add_argument("--tag", default="", help="output suffix, e.g. base/transformed")
    p.add_argument("--limit", type=int, default=None,
                   help="only the first N instances (smoke test)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--run", action="store_true")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--mock", type=int, default=0, metavar="N",
                   help="replace jurors with N offline mock jurors")
    args = p.parse_args(argv)

    jurors = [dict(j) for j in RJ.JURORS]
    if args.mock:
        jurors = [{"provider": "mock", "model": f"mock-{i}", "temperature": 0.0}
                  for i in range(args.mock)]
    elif args.jurors:
        want = {s.strip() for s in args.jurors.split(",") if s.strip()}
        jurors = [j for j in jurors if j["provider"] in want]
        if not jurors:
            sys.exit(f"no jurors match {sorted(want)}")

    specs, manifest, skips, runs = build_specs(args, jurors)
    print(f"condition={args.condition}  gt-reference={args.gt_reference}  "
          f"repeats={args.repeats}")
    print(f"cells judged: {len({(c['model_under_test'], c['run'], c['instance']) for c in manifest.values()})}"
          f"  ->  {len(specs)} jury requests")
    if skips:
        print("skipped: " + ", ".join(f"{k}={v}" for k, v in skips.most_common()))
    cost_estimate(specs, jurors)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(MANIFEST_FILE, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
        json.dump({"condition": args.condition, "gt_reference": args.gt_reference,
                   "repeats": args.repeats, "jurors": jurors,
                   "rubric_hash": RJ.RUBRIC_HASH, "tag": args.tag,
                   "skips": dict(skips)}, fh, indent=2)

    if args.dry_run:
        print(f"dry run - manifest -> {MANIFEST_FILE}")
        return 0
    if not args.run:
        p.error("choose --dry-run or --run")

    RJ.preflight([j["provider"] for j in jurors])
    raw = run_specs(specs, use_cache=not args.no_cache)
    cells = aggregate(raw, manifest)
    write_outputs(cells, runs, args.tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
