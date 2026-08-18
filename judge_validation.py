#!/usr/bin/env python3
"""Validate the LLM jury against the human gold labels.

Reads the human-labeled validation sheet and the jury's report, aligns them by
instance_id, and reports:

  * raw agreement, unweighted Cohen's kappa, Gwet's AC1, PABAK - each with a
    percentile bootstrap CI.  Kappa is primary; AC1/PABAK are reported beside it
    because the label distribution is skewed and kappa is depressed under high
    prevalence (the "kappa paradox", Feinstein & Cicchetti 1990).  AC1/PABAK use
    the FULL four-category rubric (k = 4); both are sensitive to the number of
    categories, so they are not directly comparable to the collapsed-binary
    values below (which are k = 2).  Report the convention, not the best number.
  * NO ordinal/linearly-weighted kappa.  The four labels are nominal:
    `divergent` and `contradictory` differ in kind (compatible vs incompatible
    mechanisms), not in degree, so linear weights are not defensible.  A
    collapsed BINARY view (aligned+partial vs divergent+contradictory) is
    reported instead as the principled way to credit near-misses.
  * per-class precision / recall / F1 and macro-F1 (macro matters: the rare
    classes carry no weight in raw agreement).
  * marginal distributions for both raters plus a Stuart-Maxwell test of
    marginal homogeneity - detects a systematic directional shift between human
    and jury (e.g. humans over-calling `aligned` from recall of what they meant).
  * per-juror kappa against gold, each juror's order-swap flip rate, and a
    paired bootstrap CI on (jury kappa - best single juror kappa).  Without this
    the three-model panel is unjustified.
  * a coverage curve: kappa as low-confidence instances are progressively
    abstained on, ranked by vote entropy.  Abstentions are NOT silently dropped;
    coverage is always reported next to kappa.

Everything printed is also written to validation_metrics.json so the numbers in
the paper are traceable to a file in the replication package.

Pure standard library - no numpy/scipy required.

Usage:
    python judge_validation.py
    python judge_validation.py --bootstrap 10000 --seed 42
    python judge_validation.py --sheet path/to/sheet.csv --report path/to/report.json
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import sys
from collections import Counter

REPO = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(REPO, "annotation", "reasoning_alignment")
SHEET_FILE = os.path.join(OUT_DIR, "validation", "validation_sheet.csv")
REPORT_JSON = os.path.join(OUT_DIR, "reasoning_alignment_report.json")
METRICS_FILE = os.path.join(OUT_DIR, "validation", "validation_metrics.json")

LABELS = ["aligned", "partial", "divergent", "contradictory"]
IDX = {lab: i for i, lab in enumerate(LABELS)}

# collapsed binary view: is there a conflict between the two annotators or not?
BINARY_MAP = {"aligned": "consistent", "partial": "consistent",
              "divergent": "conflicting", "contradictory": "conflicting"}
BINARY_LABELS = ["consistent", "conflicting"]


# --------------------------------------------------------------------------- #
# agreement statistics
# --------------------------------------------------------------------------- #

def confusion(pairs, labels):
    """rows = first rater (human), cols = second rater (judge)."""
    k = len(labels)
    idx = {lab: i for i, lab in enumerate(labels)}
    m = [[0] * k for _ in range(k)]
    for a, b in pairs:
        m[idx[a]][idx[b]] += 1
    return m


def _margins(m):
    k = len(m)
    n = sum(sum(r) for r in m)
    row = [sum(m[i]) for i in range(k)]
    col = [sum(m[i][c] for i in range(k)) for c in range(k)]
    return n, row, col


def p_observed(m):
    n, _, _ = _margins(m)
    if not n:
        return float("nan")
    return sum(m[i][i] for i in range(len(m))) / n


def cohen_kappa(m):
    """Unweighted Cohen's kappa.  nan when chance agreement is degenerate."""
    n, row, col = _margins(m)
    if not n:
        return float("nan")
    po = p_observed(m)
    pe = sum(row[i] * col[i] for i in range(len(m))) / (n * n)
    if abs(1.0 - pe) < 1e-12:
        return float("nan")          # both raters used one category: undefined
    return (po - pe) / (1.0 - pe)


def gwet_ac1(m):
    """Gwet's AC1 - chance correction that is stable under skewed prevalence."""
    n, row, col = _margins(m)
    k = len(m)
    if not n or k < 2:
        return float("nan")
    po = p_observed(m)
    pi = [(row[j] + col[j]) / (2.0 * n) for j in range(k)]
    pe = sum(p * (1.0 - p) for p in pi) / (k - 1)
    if abs(1.0 - pe) < 1e-12:
        return float("nan")
    return (po - pe) / (1.0 - pe)


def pabak(m):
    """Prevalence-adjusted bias-adjusted kappa, k-category generalization."""
    k = len(m)
    if k < 2:
        return float("nan")
    return (k * p_observed(m) - 1.0) / (k - 1)


def per_class(m, labels):
    """precision / recall / F1 per class, treating the human as reference."""
    n, row, col = _margins(m)
    out = {}
    for i, lab in enumerate(labels):
        tp = m[i][i]
        rec = tp / row[i] if row[i] else None
        prec = tp / col[i] if col[i] else None
        if prec and rec:
            f1 = 2 * prec * rec / (prec + rec)
        elif row[i] or col[i]:
            f1 = 0.0
        else:
            f1 = None
        out[lab] = {"support_human": row[i], "support_judge": col[i],
                    "tp": tp, "precision": prec, "recall": rec, "f1": f1}
    return out


def macro_f1(pc):
    """Mean F1 over classes that either rater actually used."""
    vals = [v["f1"] for v in pc.values() if v["f1"] is not None]
    return sum(vals) / len(vals) if vals else float("nan")


# --------------------------------------------------------------------------- #
# Stuart-Maxwell test of marginal homogeneity (pure stdlib)
# --------------------------------------------------------------------------- #

def _gammln(x):
    return math.lgamma(x)


def _gser(a, x):
    ap, s, d = a, 1.0 / a, 1.0 / a
    for _ in range(500):
        ap += 1.0
        d *= x / ap
        s += d
        if abs(d) < abs(s) * 1e-12:
            break
    return s * math.exp(-x + a * math.log(x) - _gammln(a))


def _gcf(a, x):
    tiny = 1e-300
    b, c, d = x + 1.0 - a, 1.0 / tiny, 1.0 / (x + 1.0 - a)
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-12:
            break
    return math.exp(-x + a * math.log(x) - _gammln(a)) * h


def chi2_sf(x, df):
    """Upper tail of the chi-square distribution."""
    if x <= 0:
        return 1.0
    a, xx = df / 2.0, x / 2.0
    if xx < a + 1.0:
        return 1.0 - _gser(a, xx)
    return _gcf(a, xx)


def _inv(mat):
    """Gauss-Jordan inverse; returns None if singular."""
    n = len(mat)
    a = [row[:] + [1.0 if i == j else 0.0 for j in range(n)]
         for i, row in enumerate(mat)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[piv][col]) < 1e-10:
            return None
        a[col], a[piv] = a[piv], a[col]
        pv = a[col][col]
        a[col] = [v / pv for v in a[col]]
        for r in range(n):
            if r != col and a[r][col]:
                f = a[r][col]
                a[r] = [v - f * w for v, w in zip(a[r], a[col])]
    return [row[n:] for row in a]


def stuart_maxwell(m, labels, shift_zeros=False):
    """Test H0: human and judge marginal distributions are identical.

    A significant result means the disagreement is directional (one rater
    systematically favours some categories), not symmetric noise.  Categories
    unused by both raters are dropped first.

    `shift_zeros` adds 0.5 to empty cells before testing - statsmodels'
    SquareTable does this by DEFAULT.  On sparse tables (rare classes, mostly
    empty off-diagonal) the two conventions can land on opposite sides of
    alpha=0.05, so both are computed and reported.  With shift_zeros=False this
    function reproduces statsmodels' `SquareTable(m, shift_zeros=False)
    .homogeneity('stuart_maxwell')` exactly.
    """
    n, row, col = _margins(m)
    keep = [i for i in range(len(m)) if row[i] or col[i]]
    if len(keep) < 2 or not n:
        return {"available": False, "reason": "fewer than two used categories"}
    sub = [[m[i][j] for j in keep] for i in keep]
    if shift_zeros:
        sub = [[(v if v else 0.5) for v in r] for r in sub]
    k = len(keep)
    _, r, c = _margins(sub)

    if k == 2:  # degenerates to McNemar
        b, cc = sub[0][1], sub[1][0]
        if b + cc == 0:
            return {"available": False, "reason": "no off-diagonal cells"}
        stat = (abs(b - cc) - 1) ** 2 / (b + cc)   # continuity-corrected
        return {"available": True, "test": "mcnemar_cc", "statistic": stat,
                "df": 1, "p_value": chi2_sf(stat, 1),
                "shift_zeros": shift_zeros,
                "categories": [labels[i] for i in keep]}

    d = [r[i] - c[i] for i in range(k - 1)]
    S = [[0.0] * (k - 1) for _ in range(k - 1)]
    for i in range(k - 1):
        for j in range(k - 1):
            if i == j:
                S[i][j] = r[i] + c[i] - 2 * sub[i][i]
            else:
                S[i][j] = -(sub[i][j] + sub[j][i])
    inv = _inv(S)
    if inv is None:
        return {"available": False,
                "reason": "singular covariance matrix (sparse off-diagonal)"}
    stat = sum(d[i] * inv[i][j] * d[j]
               for i in range(k - 1) for j in range(k - 1))
    if stat < 0:
        return {"available": False, "reason": "non-positive-definite covariance"}
    return {"available": True, "test": "stuart_maxwell", "statistic": stat,
            "df": k - 1, "p_value": chi2_sf(stat, k - 1),
            "shift_zeros": shift_zeros,
            "categories": [labels[i] for i in keep]}


# --------------------------------------------------------------------------- #
# bootstrap
# --------------------------------------------------------------------------- #

def bootstrap_ci(pairs, labels, stat_fn, reps, seed, alpha=0.05):
    """Percentile CI by resampling instances with replacement.

    Degenerate resamples (statistic undefined) are counted and excluded; a large
    count is itself worth reporting - it means n is too small for the estimate.
    """
    if not pairs:
        return {"point": float("nan"), "lo": None, "hi": None,
                "reps": 0, "degenerate": 0}
    point = stat_fn(confusion(pairs, labels))
    rng = random.Random(seed)
    n = len(pairs)
    vals, degen = [], 0
    for _ in range(reps):
        sample = [pairs[rng.randrange(n)] for _ in range(n)]
        v = stat_fn(confusion(sample, labels))
        if v != v:                       # nan
            degen += 1
        else:
            vals.append(v)
    if not vals:
        return {"point": point, "lo": None, "hi": None,
                "reps": reps, "degenerate": degen}
    vals.sort()
    lo = vals[max(0, int(math.floor((alpha / 2) * len(vals))))]
    hi = vals[min(len(vals) - 1, int(math.ceil((1 - alpha / 2) * len(vals))) - 1)]
    return {"point": point, "lo": lo, "hi": hi,
            "reps": reps, "degenerate": degen}


def bootstrap_delta(pairs_a, pairs_b, labels, stat_fn, reps, seed, alpha=0.05):
    """Paired bootstrap on stat(a) - stat(b) over the SAME resampled instances.

    pairs_a / pairs_b are parallel lists indexed by instance, so the two systems
    are compared on identical resamples (paired, not independent).
    """
    n = len(pairs_a)
    if n == 0 or n != len(pairs_b):
        return {"point": float("nan"), "lo": None, "hi": None, "reps": 0}
    point = stat_fn(confusion(pairs_a, labels)) - stat_fn(confusion(pairs_b, labels))
    rng = random.Random(seed)
    vals = []
    for _ in range(reps):
        idx = [rng.randrange(n) for _ in range(n)]
        va = stat_fn(confusion([pairs_a[i] for i in idx], labels))
        vb = stat_fn(confusion([pairs_b[i] for i in idx], labels))
        if va == va and vb == vb:
            vals.append(va - vb)
    if not vals:
        return {"point": point, "lo": None, "hi": None, "reps": reps}
    vals.sort()
    lo = vals[max(0, int(math.floor((alpha / 2) * len(vals))))]
    hi = vals[min(len(vals) - 1, int(math.ceil((1 - alpha / 2) * len(vals))) - 1)]
    return {"point": point, "lo": lo, "hi": hi, "reps": reps,
            "excludes_zero": (lo > 0 or hi < 0)}


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #

def load_sheet(path):
    human, unlabeled, bad = {}, [], []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            iid = (r.get("instance_id") or "").strip()
            lab = (r.get("human_alignment") or "").strip().lower()
            if not iid:
                continue
            if not lab:
                unlabeled.append(iid)
                continue
            if lab not in IDX:
                bad.append((iid, lab))
                continue
            human[iid] = lab
    if bad:
        sys.exit("invalid human_alignment values:\n" +
                 "\n".join(f"  {i}: {l!r}" for i, l in bad) +
                 f"\nuse one of {LABELS}")
    return human, unlabeled


def vote_entropy(label_counts):
    """Normalized Shannon entropy of the jury's votes (0 = unanimous, 1 = max)."""
    total = sum(label_counts.values())
    if total <= 0:
        return 1.0
    h = 0.0
    for c in label_counts.values():
        if c:
            p = c / total
            h -= p * math.log(p)
    return h / math.log(len(LABELS))


def juror_labels(votes):
    """{juror_key: label} - each juror's own majority across its orderings.

    A juror that splits across the two orderings abstains (None) rather than
    being broken toward any label; see the tie-break note in the report script.
    """
    by_juror = {}
    for v in votes:
        lab = v.get("alignment")
        if lab not in IDX:
            continue
        key = f"{v.get('provider')}:{v.get('model')}"
        by_juror.setdefault(key, []).append(lab)
    out = {}
    for key, labs in by_juror.items():
        counts = Counter(labs)
        top = max(counts.values())
        tied = [l for l, c in counts.items() if c == top]
        out[key] = tied[0] if len(tied) == 1 else None
    return out


def juror_flipped(votes):
    """{juror_key: bool} - did this juror change its label across orderings?"""
    by = {}
    for v in votes:
        lab = v.get("alignment")
        if lab not in IDX:
            continue
        key = f"{v.get('provider')}:{v.get('model')}"
        by.setdefault(key, {})[v.get("ordering")] = lab
    return {k: (len(set(d.values())) > 1) for k, d in by.items() if len(d) >= 2}


# --------------------------------------------------------------------------- #
# reporting helpers
# --------------------------------------------------------------------------- #

def band(k):
    if k != k:
        return "undefined"
    for thr, name in [(0.81, "almost perfect"), (0.61, "substantial"),
                      (0.41, "moderate"), (0.21, "fair"), (0.0, "slight")]:
        if k >= thr:
            return name
    return "poor (< chance)"


def fmt_ci(d, digits=3):
    p = d.get("point", float("nan"))
    if p != p:
        return "undefined"
    if d.get("lo") is None:
        return f"{p:.{digits}f}"
    return f"{p:.{digits}f}  [{d['lo']:.{digits}f}, {d['hi']:.{digits}f}]"


def print_matrix(m, labels, title):
    print(f"\n{title}")
    width = max(len(l) for l in labels) + 2
    print(" " * (width + 2) + "".join(f"{l[:6]:>9}" for l in labels) + "     total")
    for i, lab in enumerate(labels):
        print(f"  {lab:>{width}}" + "".join(f"{m[i][c]:>9}" for c in range(len(labels)))
              + f"{sum(m[i]):>10}")
    col = [sum(m[i][c] for i in range(len(labels))) for c in range(len(labels))]
    print(f"  {'total':>{width}}" + "".join(f"{c:>9}" for c in col)
          + f"{sum(col):>10}")


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sheet", default=SHEET_FILE)
    p.add_argument("--report", default=REPORT_JSON)
    p.add_argument("--out", default=METRICS_FILE)
    p.add_argument("--bootstrap", type=int, default=10000,
                   help="bootstrap resamples (0 to disable)")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args(argv)

    if not os.path.exists(args.sheet):
        sys.exit(f"no validation sheet at {args.sheet} - run make_validation_sheet.py")
    if not os.path.exists(args.report):
        sys.exit(f"no jury report at {args.report} - run reasoning_judge.py --run")

    with open(args.report, encoding="utf-8") as fh:
        report = json.load(fh)
    human, unlabeled = load_sheet(args.sheet)

    if unlabeled:
        print(f"note: {len(unlabeled)} sheet row(s) have no human label (skipped)")

    # ---------------- align human labels with jury verdicts ----------------- #
    # PRIMARY = binary consistent/conflicting; 4-way is the order-sensitive
    # diagnostic. jury binary uses the report's final_binary when present, else
    # falls back to collapsing final_alignment (older reports).
    no_report, abstained, pairs, records = [], [], [], []
    bpairs, b_abstained = [], []
    for iid, h in sorted(human.items()):
        entry = report.get(iid)
        if entry is None:
            no_report.append(iid)
            continue
        j = entry.get("final_alignment")
        jb = entry.get("final_binary")
        if jb not in BINARY_LABELS:            # fallback for pre-binary reports
            jb = BINARY_MAP.get(j) if j in IDX else None
        hb = BINARY_MAP[h]
        counts = entry.get("label_counts") or {}
        rec = {"instance_id": iid, "human": h, "judge": j, "judge_binary": jb,
               "human_binary": hb,
               "entropy": vote_entropy(counts),
               "label_counts": counts,
               "flagged": bool(entry.get("flagged")),
               "flag_reason": entry.get("flag_reason", ""),
               "model_disagreement": bool(entry.get("model_disagreement")),
               "order_disagreement": bool(entry.get("order_disagreement")),
               "juror_labels": juror_labels(entry.get("votes") or []),
               "juror_flipped": juror_flipped(entry.get("votes") or [])}
        records.append(rec)
        if jb in BINARY_LABELS:
            bpairs.append((hb, jb))
        else:
            b_abstained.append(iid)
        if j not in IDX:
            abstained.append(iid)
            continue
        pairs.append((h, j))

    n_gold = len(human)
    n_scored = len(pairs)
    coverage = n_scored / n_gold if n_gold else 0.0
    b_scored = len(bpairs)
    b_coverage = b_scored / n_gold if n_gold else 0.0

    if no_report:
        print(f"WARNING: {len(no_report)} gold instance(s) absent from the jury "
              f"report (excluded from the denominator): {', '.join(no_report[:10])}"
              + (" ..." if len(no_report) > 10 else ""))
    if not pairs:
        sys.exit("no comparable (human, judge) pairs")

    reps, seed = args.bootstrap, args.seed
    out = {"n_gold_labeled": n_gold, "n_scored": n_scored,
           "n_abstained": len(abstained), "n_missing_from_report": len(no_report),
           "coverage": coverage, "bootstrap_reps": reps, "seed": seed,
           "abstained_instances": abstained}

    print("\n" + "=" * 72)
    print("JURY vs HUMAN GOLD")
    print("=" * 72)
    print(f"  gold-labeled instances       : {n_gold}")
    print(f"  scored (binary, PRIMARY)     : {b_scored}   coverage {b_coverage:.1%}")
    print(f"  scored (4-way, diagnostic)   : {n_scored}   coverage {coverage:.1%}")

    # ================= PRIMARY: binary consistent vs conflicting ============= #
    bm = confusion(bpairs, BINARY_LABELS) if bpairs else [[0, 0], [0, 0]]
    if bpairs and reps:
        bstats = {"cohen_kappa": bootstrap_ci(bpairs, BINARY_LABELS, cohen_kappa, reps, seed + 4),
                  "gwet_ac1": bootstrap_ci(bpairs, BINARY_LABELS, gwet_ac1, reps, seed + 5),
                  "raw_agreement": bootstrap_ci(bpairs, BINARY_LABELS, p_observed, reps, seed + 6)}
    else:
        bstats = {k: {"point": fn(bm)} for k, fn in
                  (("cohen_kappa", cohen_kappa), ("gwet_ac1", gwet_ac1),
                   ("raw_agreement", p_observed))}
    out["binary"] = {"mapping": BINARY_MAP, "n_scored": b_scored,
                     "coverage": b_coverage, "statistics": bstats,
                     "confusion_matrix": {"labels": BINARY_LABELS, "matrix": bm},
                     "marginal_homogeneity": stuart_maxwell(bm, BINARY_LABELS)}
    print("\n-- PRIMARY: consistent (aligned+partial) vs conflicting "
          "(divergent+contradictory) --")
    print(f"  raw agreement      {fmt_ci(bstats['raw_agreement'])}")
    print(f"  Cohen's kappa      {fmt_ci(bstats['cohen_kappa'])}"
          f"   ({band(bstats['cohen_kappa']['point'])})   <- PRIMARY")
    print(f"  Gwet's AC1         {fmt_ci(bstats['gwet_ac1'])}")
    _bp = per_class(bm, BINARY_LABELS)
    print("  per-class (human = reference):")
    for lab in BINARY_LABELS:
        v = _bp[lab]
        g = lambda x: f"{x:.3f}" if x is not None else "-"
        print(f"    {lab:>12}  n_human={v['support_human']:>3}  "
              f"P={g(v['precision'])}  R={g(v['recall'])}  F1={g(v['f1'])}")
    if _bp["conflicting"]["support_human"] == 0:
        print("  NOTE: gold has no `conflicting` instances (agreed-only set), so")
        print("  binary kappa is degenerate (one class). Raw agreement is the")
        print("  meaningful number here; the conflicting code needs non-agreed data")
        print("  to validate. This is expected, not a failure.")
    print_matrix(bm, BINARY_LABELS, "  binary confusion (rows = human, cols = jury)")

    # ============ DIAGNOSTIC: 4-way split (ORDER-SENSITIVE) ================== #
    m = confusion(pairs, LABELS)
    raw = p_observed(m)
    stats = {}
    if reps:
        stats["cohen_kappa"] = bootstrap_ci(pairs, LABELS, cohen_kappa, reps, seed)
        stats["gwet_ac1"] = bootstrap_ci(pairs, LABELS, gwet_ac1, reps, seed + 1)
        stats["pabak"] = bootstrap_ci(pairs, LABELS, pabak, reps, seed + 2)
        stats["raw_agreement"] = bootstrap_ci(pairs, LABELS, p_observed, reps, seed + 3)
    else:
        for name, fn in [("cohen_kappa", cohen_kappa), ("gwet_ac1", gwet_ac1),
                         ("pabak", pabak), ("raw_agreement", p_observed)]:
            stats[name] = {"point": fn(m), "lo": None, "hi": None, "reps": 0}
    out["four_class"] = {"statistics": stats}

    print("\n-- DIAGNOSTIC: 4-way agreement (ORDER-SENSITIVE; do not report alone) --")
    print(f"  raw agreement      {fmt_ci(stats['raw_agreement'])}"
          f"   ({sum(m[i][i] for i in range(4))}/{n_scored})")
    print(f"  Cohen's kappa      {fmt_ci(stats['cohen_kappa'])}"
          f"   ({band(stats['cohen_kappa']['point'])})")
    print(f"  Gwet's AC1         {fmt_ci(stats['gwet_ac1'])}")
    print(f"  PABAK              {fmt_ci(stats['pabak'])}")
    if stats["cohen_kappa"].get("degenerate"):
        print(f"  note: {stats['cohen_kappa']['degenerate']} of {reps} resamples were "
              "degenerate (kappa undefined) - n is small for this label set")
    print("  The aligned<->partial boundary is position-sensitive; this 4-way")
    print("  kappa is depressed by that instability AND by skewed prevalence")
    print("  (Feinstein & Cicchetti 1990). Reported for diagnosis only - the")
    print("  binary result above is the one to cite. AC1/PABAK use k=4 (not")
    print("  comparable to the k=2 binary values).")

    # ---------------- marginals + confusion --------------------------------- #
    _, row, col = _margins(m)
    out["four_class"]["confusion_matrix"] = {"labels": LABELS, "matrix": m}
    out["four_class"]["marginals"] = {
        "human": {LABELS[i]: row[i] for i in range(4)},
        "judge": {LABELS[i]: col[i] for i in range(4)}}
    print_matrix(m, LABELS, "-- confusion matrix (rows = human gold, cols = jury) --")

    print("\n-- marginal distributions --")
    print(f"  {'label':>15}{'human':>10}{'jury':>10}{'delta':>10}")
    for i, lab in enumerate(LABELS):
        print(f"  {lab:>15}{row[i]:>10}{col[i]:>10}{col[i] - row[i]:>+10}")

    sm = stuart_maxwell(m, LABELS, shift_zeros=False)
    sm_shift = stuart_maxwell(m, LABELS, shift_zeros=True)
    out["four_class"]["marginal_homogeneity"] = sm
    out["four_class"]["marginal_homogeneity_shift_zeros"] = sm_shift
    print("\n-- marginal homogeneity (is the disagreement directional?) --")
    if sm.get("available"):
        print(f"  uncorrected      {sm['test']}: chi2 = {sm['statistic']:.3f}, "
              f"df = {sm['df']}, p = {sm['p_value']:.4f}")
    else:
        print(f"  uncorrected      unavailable ({sm.get('reason')})")
    if sm_shift.get("available"):
        print(f"  zeros +0.5       {sm_shift['test']}: chi2 = "
              f"{sm_shift['statistic']:.3f}, df = {sm_shift['df']}, "
              f"p = {sm_shift['p_value']:.4f}")
    else:
        print(f"  zeros +0.5       unavailable ({sm_shift.get('reason')})")
    ps = [s["p_value"] for s in (sm, sm_shift) if s.get("available")]
    if ps and all(p < 0.05 for p in ps):
        print("  SIGNIFICANT under both conventions: human and jury marginals")
        print("  differ systematically. Report this as a finding, not a nuisance -")
        print("  it is the expected signature of annotators recalling what they")
        print("  meant while the jury sees only the written text.")
    elif ps and all(p >= 0.05 for p in ps):
        print("  Not significant under either convention: no detectable systematic")
        print("  shift in marginals.")
    elif ps:
        print("  CONVENTION-DEPENDENT: the two disagree at alpha = 0.05. Your table")
        print("  is too sparse for this test to be decisive. Report both p-values,")
        print("  state which convention you preregistered, and lean on the marginal")
        print("  deltas above rather than on significance.")
    print("  (statsmodels' SquareTable applies the +0.5 shift by default; the")
    print("   uncorrected value is the textbook Stuart-Maxwell statistic.)")

    # ---------------- per-class -------------------------------------------- #
    pc = per_class(m, LABELS)
    mf1 = macro_f1(pc)
    out["four_class"]["per_class"] = pc
    out["four_class"]["macro_f1"] = mf1
    print("\n-- per-class agreement (human = reference) --")
    print(f"  {'label':>15}{'n_human':>9}{'n_jury':>8}{'precision':>12}"
          f"{'recall':>10}{'F1':>8}")
    for lab in LABELS:
        v = pc[lab]
        f = lambda x: f"{x:.3f}" if x is not None else "-"
        print(f"  {lab:>15}{v['support_human']:>9}{v['support_judge']:>8}"
              f"{f(v['precision']):>12}{f(v['recall']):>10}{f(v['f1']):>8}")
    print(f"  macro-F1 (used classes only): {mf1:.3f}")
    rare = [l for l in LABELS if pc[l]["support_human"] < 10]
    if rare:
        print(f"  CAUTION: {', '.join(rare)} have < 10 gold instances; per-class")
        print("  figures and their contribution to macro-F1 are unstable.")

    # (binary agreement is reported up front as the PRIMARY result)

    # ---------------- per-juror --------------------------------------------- #
    all_jurors = sorted({k for r in records for k in r["juror_labels"]})
    juror_out = {}
    print("\n-- per-juror agreement with gold (does the panel earn its keep?) --")
    if not all_jurors:
        print("  no per-juror votes found in the report")
    else:
        print(f"  {'juror':>34}{'n':>6}{'cov':>8}{'kappa':>22}{'flip%':>8}")
        for jk in all_jurors:
            jp = [(r["human"], r["juror_labels"][jk]) for r in records
                  if r["juror_labels"].get(jk) in IDX]
            flips = [r["juror_flipped"].get(jk) for r in records
                     if jk in r["juror_flipped"]]
            flip_rate = (sum(1 for f in flips if f) / len(flips)) if flips else None
            if jp:
                ci = (bootstrap_ci(jp, LABELS, cohen_kappa, reps, seed + 7)
                      if reps else {"point": cohen_kappa(confusion(jp, LABELS))})
            else:
                ci = {"point": float("nan"), "lo": None, "hi": None}
            cov = len(jp) / n_gold if n_gold else 0.0
            juror_out[jk] = {"n_scored": len(jp), "coverage": cov,
                             "cohen_kappa": ci,
                             "order_flip_rate": flip_rate,
                             "n_with_both_orderings": len(flips)}
            fr = f"{flip_rate:.1%}" if flip_rate is not None else "-"
            print(f"  {jk:>34}{len(jp):>6}{cov:>8.1%}{fmt_ci(ci):>22}{fr:>8}")

        # jury vs best single juror, paired on the instances both scored
        best, best_k = None, float("-inf")
        for jk, v in juror_out.items():
            kv = v["cohen_kappa"]["point"]
            if kv == kv and kv > best_k:
                best, best_k = jk, kv
        if best is not None and reps:
            common = [r for r in records
                      if r["judge"] in IDX and r["juror_labels"].get(best) in IDX]
            pa = [(r["human"], r["judge"]) for r in common]
            pb = [(r["human"], r["juror_labels"][best]) for r in common]
            delta = bootstrap_delta(pa, pb, LABELS, cohen_kappa, reps, seed + 8)
            out["jury_vs_best_juror"] = {"best_juror": best, "n_paired": len(common),
                                         "delta_kappa": delta}
            print(f"\n  jury kappa - best single juror ({best}), paired on "
                  f"{len(common)} instances:")
            print(f"    delta = {fmt_ci(delta)}")
            small_n = len(common) < 50 or any(v["support_human"] < 10
                                              for v in pc.values() if v["support_human"])
            if delta.get("excludes_zero") and delta["point"] > 0:
                print("    CI excludes zero: the panel measurably beats its best member.")
            elif delta.get("excludes_zero"):
                print("    CI excludes zero AND is negative: on this sample the best")
                print("    single juror scores higher. Treat as suggestive, not final,")
                print("    unless n and the rare-class counts are adequate.")
            else:
                print("    CI includes zero: at this n the panel and the best single")
                print("    juror are statistically indistinguishable - this is an")
                print("    UNDERPOWERED result, not evidence the panel is redundant.")
                if small_n:
                    print("    (n < 50 and/or rare classes < 10: the per-juror kappas")
                    print("     have very wide CIs; do not drop the panel on this basis.)")
    out["per_juror"] = juror_out

    # ---------------- coverage curve ---------------------------------------- #
    scored = [r for r in records if r["judge"] in IDX]
    scored.sort(key=lambda r: (r["entropy"], r["flagged"]))
    curve = []
    print("\n-- selective evaluation: abstain on the least-confident instances --")
    print("  (ranked by jury vote entropy; coverage is over all gold instances)")
    print(f"  {'keep':>7}{'n':>6}{'coverage':>11}{'raw':>9}{'kappa':>10}")
    for frac in [1.0, 0.95, 0.9, 0.8, 0.7, 0.6, 0.5]:
        take = max(2, int(round(frac * len(scored))))
        subset = scored[:take]
        sp = [(r["human"], r["judge"]) for r in subset]
        sm_ = confusion(sp, LABELS)
        kv, rv = cohen_kappa(sm_), p_observed(sm_)
        cov = len(sp) / n_gold if n_gold else 0.0
        curve.append({"keep_fraction": frac, "n": len(sp), "coverage": cov,
                      "raw_agreement": rv, "cohen_kappa": kv})
        kd = f"{kv:.3f}" if kv == kv else "undef"
        print(f"  {frac:>7.0%}{len(sp):>6}{cov:>11.1%}{rv:>9.1%}{kd:>10}")
    out["coverage_curve"] = curve
    print("  Report the operating point you actually intend to use, e.g. \"at 80%")
    print("  coverage the pipeline agrees with expert consensus at kappa = X\".")

    # ---------------- flag diagnostics -------------------------------------- #
    fl = [r for r in scored if r["flagged"]]
    nf = [r for r in scored if not r["flagged"]]
    diag = {}
    for name, grp in [("flagged", fl), ("not_flagged", nf)]:
        if grp:
            gp = [(r["human"], r["judge"]) for r in grp]
            gm = confusion(gp, LABELS)
            diag[name] = {"n": len(gp), "raw_agreement": p_observed(gm),
                          "cohen_kappa": cohen_kappa(gm)}
    out["flag_diagnostics"] = diag
    if len(diag) == 2:
        print("\n-- is the `flagged` heuristic selecting the errors it should? --")
        for name in ("not_flagged", "flagged"):
            d = diag[name]
            kd = f"{d['cohen_kappa']:.3f}" if d["cohen_kappa"] == d["cohen_kappa"] else "undef"
            print(f"  {name:>12}: n={d['n']:>4}  raw={d['raw_agreement']:.1%}  kappa={kd}")
        print("  Agreement should be clearly LOWER on flagged instances. If it is not,")
        print("  the flag is not identifying the cases that need human adjudication.")

    # ---------------- disagreement listing ---------------------------------- #
    errs = [r for r in scored if r["human"] != r["judge"]]
    errs.sort(key=lambda r: -r["entropy"])
    out["disagreements"] = [{"instance_id": r["instance_id"], "human": r["human"],
                             "judge": r["judge"], "entropy": r["entropy"],
                             "label_counts": r["label_counts"],
                             "flag_reason": r["flag_reason"]} for r in errs]
    print(f"\n-- {len(errs)} disagreement(s), highest vote entropy first --")
    for r in errs[:20]:
        print(f"  {r['instance_id']:<28} human={r['human']:<14}"
              f"jury={r['judge']:<14}H={r['entropy']:.2f}  {r['flag_reason']}")
    if len(errs) > 20:
        print(f"  ... {len(errs) - 20} more in {os.path.basename(args.out)}")

    # ---------------- write ------------------------------------------------- #
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print(f"\nmetrics written to {args.out}")

    print("\n" + "=" * 72)
    print("REMINDERS FOR THE WRITE-UP")
    print("=" * 72)
    print("  * The gold labels were produced by the same two people who wrote the")
    print("    reasonings being judged. State this as a threat to validity and")
    print("    cite the marginal-homogeneity result above as evidence for or")
    print("    against a systematic recall bias.")
    print("  * These 94 instances are a DEV set if you tuned any prompt or anchor")
    print("    example against them. Reserve the next annotation batch as held-out")
    print("    test and report both numbers separately.")
    print("  * Report kappa WITH its CI and WITH coverage. A bare point estimate at")
    print("    this n is not interpretable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
