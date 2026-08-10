#!/usr/bin/env python3
"""Merge two annotators' fault-localization annotations and report conflicts.

Conflicts are decided purely from the ``root_cause`` list: the (file, line,
statement) triple of each entry.  Everything else (reasoning, confidence, hunk
flags, fault_triggering_call_site) is reported as informational only and never
blocks a merge.

Usage:
    python merge_annotations.py                       # report only
    python merge_annotations.py --write               # also write merged/ files
    python merge_annotations.py --resolutions res.json --write
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any

REPO = os.path.dirname(os.path.abspath(__file__))

DEFAULT_A = os.path.join(REPO, "annotation", "Atish_Annotation")
DEFAULT_B = os.path.join(REPO, "annotation", "Eshgin_Annotation")
DEFAULT_OUT = os.path.join(REPO, "annotation", "merged")
DEFAULT_REPORT = os.path.join(REPO, "annotation", "merge_report")

# A line difference at or below this, with an identical statement, is treated as
# the same location shifted by patch context rather than a real disagreement.
LINE_SHIFT_TOLERANCE = 10


# --------------------------------------------------------------------------- #
# normalisation
# --------------------------------------------------------------------------- #

def norm_file(path: Any) -> str:
    if path is None:
        return ""
    return str(path).strip().replace("\\", "/").lstrip("./")


def norm_stmt(stmt: Any) -> str:
    """Whitespace-insensitive form used for exact statement equality."""
    if stmt is None:
        return ""
    return " ".join(str(stmt).split())


def loose_stmt(stmt: Any) -> str:
    """Punctuation/whitespace-insensitive form used for near-match detection."""
    s = norm_stmt(stmt).replace(" ", "")
    return s.rstrip(",:;").rstrip()


def norm_line(line: Any) -> int | None:
    try:
        return int(line)
    except (TypeError, ValueError):
        return None


@dataclass
class Loc:
    """One root-cause location from one annotator."""

    idx: int
    file: str
    line: int | None
    statement: str
    raw: dict

    @property
    def key(self) -> tuple:
        return (self.file, self.line, self.statement)

    def __str__(self) -> str:
        return f"{self.file}:{self.line}  {self.statement}"


def load_locs(doc: dict) -> list[Loc]:
    out = []
    for i, entry in enumerate(doc.get("root_cause") or []):
        if not isinstance(entry, dict):
            continue
        out.append(
            Loc(
                idx=i,
                file=norm_file(entry.get("file")),
                line=norm_line(entry.get("line")),
                statement=norm_stmt(entry.get("statement")),
                raw=entry,
            )
        )
    return out


# --------------------------------------------------------------------------- #
# comparison
# --------------------------------------------------------------------------- #

@dataclass
class Comparison:
    instance_id: str
    agreed: list[dict] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    informational: list[dict] = field(default_factory=list)

    @property
    def blocking(self) -> list[dict]:
        return [c for c in self.conflicts if c["severity"] == "blocking"]

    @property
    def minor(self) -> list[dict]:
        return [c for c in self.conflicts if c["severity"] == "minor"]

    @property
    def status(self) -> str:
        if self.blocking:
            return "conflict"
        if self.minor:
            return "minor_conflict"
        return "agree"


def compare_root_causes(instance_id: str, a: list[Loc], b: list[Loc], name_a: str,
                        name_b: str) -> Comparison:
    """Order-insensitive greedy match of two root-cause lists.

    Match passes, most to least specific:
      1. (file, line, statement)  -> agreement
      2. (file, statement)        -> line_mismatch  (minor if within tolerance)
      3. (file, line)             -> statement_mismatch
      4. (file, loose statement)  -> statement_formatting (minor)
    Whatever is left over is an extra location on one side only.
    """
    cmp = Comparison(instance_id)
    left, right = list(a), list(b)

    def take(pred, pool):
        for i, loc in enumerate(pool):
            if pred(loc):
                return pool.pop(i)
        return None

    # pass 1 - exact
    for la in list(left):
        lb = take(lambda x: x.key == la.key, right)
        if lb is not None:
            left.remove(la)
            cmp.agreed.append({"file": la.file, "line": la.line,
                               "statement": la.statement})

    # pass 2 - same file + statement, different line
    for la in list(left):
        lb = take(lambda x: x.file == la.file and x.statement == la.statement, right)
        if lb is None:
            continue
        left.remove(la)
        delta = (abs(la.line - lb.line)
                 if la.line is not None and lb.line is not None else None)
        minor = delta is not None and delta <= LINE_SHIFT_TOLERANCE
        cmp.conflicts.append({
            "type": "line_mismatch",
            "severity": "minor" if minor else "blocking",
            "file": la.file,
            "statement": la.statement,
            "line_delta": delta,
            name_a: {"line": la.line, "note": la.raw.get("note")},
            name_b: {"line": lb.line, "note": lb.raw.get("note")},
        })

    # pass 3 - same file + line, different statement
    for la in list(left):
        lb = take(lambda x: x.file == la.file and x.line == la.line, right)
        if lb is None:
            continue
        left.remove(la)
        minor = loose_stmt(la.statement) == loose_stmt(lb.statement)
        cmp.conflicts.append({
            "type": "statement_formatting" if minor else "statement_mismatch",
            "severity": "minor" if minor else "blocking",
            "file": la.file,
            "line": la.line,
            name_a: {"statement": la.statement, "note": la.raw.get("note")},
            name_b: {"statement": lb.statement, "note": lb.raw.get("note")},
        })

    # pass 4 - same file, statement equal ignoring punctuation, line differs
    for la in list(left):
        lb = take(lambda x: x.file == la.file
                  and loose_stmt(x.statement) == loose_stmt(la.statement), right)
        if lb is None:
            continue
        left.remove(la)
        delta = (abs(la.line - lb.line)
                 if la.line is not None and lb.line is not None else None)
        minor = delta is not None and delta <= LINE_SHIFT_TOLERANCE
        cmp.conflicts.append({
            "type": "line_and_formatting_mismatch",
            "severity": "minor" if minor else "blocking",
            "file": la.file,
            "line_delta": delta,
            name_a: {"line": la.line, "statement": la.statement},
            name_b: {"line": lb.line, "statement": lb.statement},
        })

    # leftovers - a location only one annotator reported
    for la in left:
        cmp.conflicts.append({
            "type": "extra_location",
            "severity": "blocking",
            "only_in": name_a,
            "file": la.file,
            "line": la.line,
            "statement": la.statement,
            "note": la.raw.get("note"),
            "same_file_as_other_side": any(x.file == la.file for x in b),
        })
    for lb in right:
        cmp.conflicts.append({
            "type": "extra_location",
            "severity": "blocking",
            "only_in": name_b,
            "file": lb.file,
            "line": lb.line,
            "statement": lb.statement,
            "note": lb.raw.get("note"),
            "same_file_as_other_side": any(x.file == lb.file for x in a),
        })

    return cmp


def compare_metadata(doc_a: dict, doc_b: dict, name_a: str, name_b: str) -> list[dict]:
    """Non-blocking differences outside root_cause."""
    out = []
    if doc_a.get("confidence") != doc_b.get("confidence"):
        out.append({"type": "confidence_differs",
                    name_a: doc_a.get("confidence"),
                    name_b: doc_b.get("confidence")})

    def ftcs(doc):
        triples = (
            (norm_file(e.get("file")), norm_line(e.get("line")),
             norm_stmt(e.get("statement")))
            for e in (doc.get("fault_triggering_call_site") or [])
            if isinstance(e, dict)
        )
        # line may be None, so sort with a key that never compares int to None
        return sorted(triples, key=lambda t: (t[0], t[1] is None, t[1] or 0, t[2]))

    fa, fb = ftcs(doc_a), ftcs(doc_b)
    if fa != fb:
        out.append({
            "type": "ftcs_differs",
            name_a: [f"{f}:{l}  {s}" for f, l, s in fa],
            name_b: [f"{f}:{l}  {s}" for f, l, s in fb],
        })

    for flag in ("multi_rc", "rc_ftcs_same", "hunk_type", "fault_inducing",
                 "rc_in_this_hunk", "is_defensive"):
        va, vb = doc_a.get(flag), doc_b.get(flag)
        if va is not None and vb is not None and va != vb:
            out.append({"type": f"{flag}_differs", name_a: va, name_b: vb})
    return out


# --------------------------------------------------------------------------- #
# per-location agreement metrics
# --------------------------------------------------------------------------- #

# root-cause locations are set-valued, so instance-level agree/conflict throws
# away partial overlap.  These metrics score agreement per location instead, at
# four granularities from coarsest to finest.  Statement level is shift-
# invariant (ignores line numbers) and is the recommended headline number.
GRANULARITIES = ("file", "statement", "line", "full")


def loc_sets(locs: list[Loc]) -> dict[str, set]:
    """Map each granularity to the set of elements one annotator selected."""
    return {
        "file": {l.file for l in locs},
        "statement": {(l.file, l.statement) for l in locs},
        "line": {(l.file, l.line) for l in locs},
        "full": {(l.file, l.line, l.statement) for l in locs},
    }


def masi_distance(a: set, b: set) -> float:
    """MASI distance (Passonneau 2006): 0 = identical, 1 = disjoint.

    distance = 1 - Jaccard * M, where the monotonicity term M is 1 for equal
    sets, 2/3 when one contains the other, 1/3 for other overlap, 0 when
    disjoint.  Used as the distance function for Krippendorff's alpha.
    """
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    j = inter / union if union else 0.0
    if a == b:
        m = 1.0
    elif a <= b or b <= a:
        m = 2 / 3
    elif inter:
        m = 1 / 3
    else:
        m = 0.0
    return 1.0 - j * m


def agreement_metrics(pairs: list[tuple[dict, dict]]) -> dict:
    """Per-granularity agreement over (loc_sets_a, loc_sets_b) instance pairs.

    For each granularity reports:
      - jaccard_micro : pooled |A&B| / |A|B| across all instances (weights by
                        number of locations)
      - jaccard_macro : mean of per-instance Jaccard (weights each instance
                        equally; instances where neither side has locations are
                        skipped)
      - dice_micro    : pooled 2|A&B| / (|A|+|B|)  (a.k.a. F1)
      - alpha_masi    : Krippendorff's alpha with MASI distance, chance-corrected
    """
    out = {}
    for g in GRANULARITIES:
        inter_sum = union_sum = a_sum = b_sum = 0
        per_instance = []
        pool = []
        for sa, sb in pairs:
            A, B = sa[g], sb[g]
            inter, union = len(A & B), len(A | B)
            inter_sum += inter
            union_sum += union
            a_sum += len(A)
            b_sum += len(B)
            if union:
                per_instance.append(inter / union)
            pool.append(A)
            pool.append(B)

        # Krippendorff alpha = 1 - Do/De.  With exactly two coders per unit,
        # observed disagreement Do is the mean MASI distance between the two
        # annotators' sets; expected disagreement De is the mean MASI distance
        # over all cross pairs in the pool of 2N sets.
        do = (sum(masi_distance(sa[g], sb[g]) for sa, sb in pairs) / len(pairs)
              if pairs else 0.0)
        n = len(pool)
        if n > 1:
            de = (sum(masi_distance(pool[i], pool[j])
                      for i in range(n) for j in range(n) if i != j)
                  / (n * (n - 1)))
        else:
            de = 0.0
        alpha = 1.0 - do / de if de else 1.0

        out[g] = {
            "jaccard_micro": inter_sum / union_sum if union_sum else 1.0,
            "jaccard_macro": (sum(per_instance) / len(per_instance)
                              if per_instance else 1.0),
            "dice_micro": (2 * inter_sum) / (a_sum + b_sum) if (a_sum + b_sum) else 1.0,
            "alpha_masi": alpha,
        }
    return out


# --------------------------------------------------------------------------- #
# merging
# --------------------------------------------------------------------------- #

def merge_docs(doc_a: dict, doc_b: dict, name_a: str, name_b: str,
               cmp: Comparison | None, primary: str) -> dict:
    """Build the merged document.

    The primary annotator's document is kept verbatim so the downstream schema
    is unchanged; provenance and the other annotator's reasoning/notes are
    recorded under ``merge_metadata``.
    """
    base, other = (doc_a, doc_b) if primary == name_a else (doc_b, doc_a)
    base_name, other_name = ((name_a, name_b) if primary == name_a
                             else (name_b, name_a))

    merged = json.loads(json.dumps(base))
    meta = {
        "status": cmp.status if cmp else "agree",
        "annotators": [name_a, name_b],
        "primary": base_name,
        "root_cause_agreement": {
            "exact_matches": len(cmp.agreed),
            f"locations_{name_a}": len(doc_a.get("root_cause") or []),
            f"locations_{name_b}": len(doc_b.get("root_cause") or []),
        } if cmp else None,
        f"reasoning_{other_name}": other.get("reasoning"),
    }
    if cmp and cmp.conflicts:
        meta["unresolved_conflicts"] = cmp.conflicts
    if cmp and cmp.informational:
        meta["informational_differences"] = cmp.informational
    merged["merge_metadata"] = meta
    return merged


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #

def render_markdown(results: list[dict], name_a: str, name_b: str,
                    metrics: dict, conflict_types: dict[str, int]) -> str:
    lines = ["# Annotation merge report", ""]
    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    lines.append(f"- Annotators: **{name_a}** vs **{name_b}**")
    lines.append(f"- Instances considered: **{len(results)}**")
    for k in ("agree", "minor_conflict", "conflict",
              "resolved", "skipped_by_resolution"):
        if k in counts:
            lines.append(f"- {k}: **{counts[k]}**")
    lines.append("")

    lines.append("## Per-location agreement")
    lines.append("")
    lines.append("Root-cause locations are set-valued, so instance-level "
                 "agree/conflict discards partial overlap. These score "
                 "agreement per location; statement level is line-shift "
                 "invariant and is the recommended headline number.")
    lines.append("")
    lines.append("| Granularity | Jaccard (macro) | Jaccard (micro) | "
                 "Dice / F1 (micro) | Krippendorff α (MASI) |")
    lines.append("|---|---|---|---|---|")
    for g in GRANULARITIES:
        m = metrics[g]
        lines.append(f"| {g} | {m['jaccard_macro']:.3f} | "
                     f"{m['jaccard_micro']:.3f} | {m['dice_micro']:.3f} | "
                     f"{m['alpha_masi']:.3f} |")
    lines.append("")
    if conflict_types:
        total = sum(conflict_types.values())
        lines.append(f"Disagreement composition ({total} conflicting "
                     "locations): "
                     + ", ".join(f"**{t}** {n} ({n / total:.0%})"
                                 for t, n in sorted(conflict_types.items(),
                                                    key=lambda kv: -kv[1])))
        lines.append("")

    def section(title, statuses):
        rows = [r for r in results if r["status"] in statuses]
        if not rows:
            return
        lines.append(f"## {title} ({len(rows)})")
        lines.append("")
        for r in rows:
            lines.append(f"### {r['instance_id']}")
            lines.append(f"- root causes: {name_a}={r['n_a']}, "
                         f"{name_b}={r['n_b']}, agreed={len(r['agreed'])}")
            for c in r["conflicts"]:
                lines.append(f"- **{c['type']}** ({c['severity']})")
                for k, v in c.items():
                    if k in ("type", "severity"):
                        continue
                    lines.append(f"    - {k}: {v}")
            for i in r["informational"]:
                lines.append(f"- _info_ {i['type']}: "
                             f"{ {k: v for k, v in i.items() if k != 'type'} }")
            lines.append("")

    section("Blocking conflicts — need manual resolution", {"conflict"})
    section("Minor conflicts — likely same location", {"minor_conflict"})
    section("Full agreement on root cause", {"agree"})

    return "\n".join(lines)


def write_id_lists(prefix: str, results: list[dict]) -> list[str]:
    """Write one plain-text file per bucket, instance ids newline-separated.

    The four core buckets are always written (empty if nothing landed in them)
    so downstream scripts can rely on the paths existing.  Resolution buckets
    are written only when a --resolutions map put something there, and are
    deleted otherwise so a re-run never leaves stale ids behind.
    """
    def ids(*statuses):
        return [r["instance_id"] for r in results if r["status"] in statuses]

    always = {
        # genuine root-cause agreement only - resolved conflicts are listed
        # separately so this file never overstates inter-annotator agreement
        "agreed": ids("agree"),
        "conflicts": ids("conflict", "minor_conflict"),
        # everything that ended up in the merged output directory
        "merged": [r["instance_id"] for r in results if r.get("mergeable")],
    }
    optional = {
        "conflicts_blocking": ids("conflict"),
        "conflicts_minor": ids("minor_conflict"),
        "resolved": ids("resolved"),
        "skipped_by_resolution": ids("skipped_by_resolution"),
    }

    written = []
    for bucket, values in list(always.items()) + list(optional.items()):
        path = f"{prefix}_{bucket}.txt"
        if bucket in optional and not values:
            if os.path.exists(path):
                os.remove(path)
            continue
        with open(path, "w", encoding="utf-8") as fh:
            for iid in sorted(values):
                fh.write(iid + "\n")
        written.append(path)
    return written


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def instance_ids(directory: str) -> set[str]:
    if not os.path.isdir(directory):
        return set()
    return {f[:-5] for f in os.listdir(directory) if f.endswith(".json")}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dir-a", default=DEFAULT_A)
    p.add_argument("--dir-b", default=DEFAULT_B)
    p.add_argument("--name-a", default=None, help="defaults to dir-a basename")
    p.add_argument("--name-b", default=None, help="defaults to dir-b basename")
    p.add_argument("--out", default=DEFAULT_OUT, help="merged output directory")
    p.add_argument("--report", default=DEFAULT_REPORT,
                   help="report path prefix (.json and .md are written)")
    p.add_argument("--primary", default=None,
                   help="annotator whose document is the merge base "
                        "(default: name-a)")
    p.add_argument("--resolutions", default=None,
                   help='JSON map {instance_id: "A"|"B"|"skip"} choosing a '
                        "winner for conflicting instances")
    p.add_argument("--write", action="store_true",
                   help="write merged files (default: report only)")
    p.add_argument("--include-minor", action="store_true",
                   help="also auto-merge instances whose only conflicts are minor")
    args = p.parse_args(argv)

    name_a = args.name_a or os.path.basename(args.dir_a.rstrip("/"))
    name_b = args.name_b or os.path.basename(args.dir_b.rstrip("/"))
    primary = args.primary or name_a
    if primary not in (name_a, name_b):
        p.error(f"--primary must be {name_a!r} or {name_b!r}")

    resolutions = {}
    if args.resolutions:
        raw = read_json(args.resolutions)
        for k, v in raw.items():
            v = str(v).strip()
            resolutions[k] = {"A": name_a, "B": name_b}.get(v.upper(), v)

    ids_a, ids_b = instance_ids(args.dir_a), instance_ids(args.dir_b)
    # only instances annotated by both annotators
    todo = sorted(ids_a & ids_b)

    results, written = [], 0
    loc_pairs = []
    for iid in todo:
        doc_a = read_json(os.path.join(args.dir_a, iid + ".json"))
        doc_b = read_json(os.path.join(args.dir_b, iid + ".json"))

        locs_a, locs_b = load_locs(doc_a), load_locs(doc_b)
        loc_pairs.append((loc_sets(locs_a), loc_sets(locs_b)))
        cmp = compare_root_causes(iid, locs_a, locs_b, name_a, name_b)
        cmp.informational = compare_metadata(doc_a, doc_b, name_a, name_b)
        rec = {
            "instance_id": iid,
            "status": cmp.status,
            "annotators": [name_a, name_b],
            "n_a": len(doc_a.get("root_cause") or []),
            "n_b": len(doc_b.get("root_cause") or []),
            "agreed": cmp.agreed,
            "conflicts": cmp.conflicts,
            "informational": cmp.informational,
        }
        winner = resolutions.get(iid)
        if winner == "skip":
            rec["resolution"] = "skip"
            rec["conflict_status_before_skip"] = rec["status"]
            rec["status"] = "skipped_by_resolution"
            merged = None
        elif winner in (name_a, name_b):
            rec["resolution"] = winner
            rec["status"] = "resolved"
            merged = merge_docs(doc_a, doc_b, name_a, name_b, cmp, winner)
            merged["merge_metadata"]["status"] = "resolved"
            merged["merge_metadata"]["resolved_in_favour_of"] = winner
            merged["merge_metadata"].pop("unresolved_conflicts", None)
            merged["merge_metadata"]["resolved_conflicts"] = cmp.conflicts
        else:
            merged = merge_docs(doc_a, doc_b, name_a, name_b, cmp, primary)

        results.append(rec)

        auto_ok = rec["status"] in ("agree", "resolved") or (
            args.include_minor and rec["status"] == "minor_conflict")
        rec["mergeable"] = bool(auto_ok and merged is not None)
        if args.write and merged is not None and auto_ok:
            os.makedirs(args.out, exist_ok=True)
            with open(os.path.join(args.out, iid + ".json"), "w",
                      encoding="utf-8") as fh:
                json.dump(merged, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            written += 1

    metrics = agreement_metrics(loc_pairs)
    conflict_types: dict[str, int] = {}
    for r in results:
        for c in r["conflicts"]:
            conflict_types[c["type"]] = conflict_types.get(c["type"], 0) + 1

    report = {
        "annotator_a": name_a,
        "annotator_b": name_b,
        "primary": primary,
        "line_shift_tolerance": LINE_SHIFT_TOLERANCE,
        "counts": {
            s: sum(1 for r in results if r["status"] == s)
            for s in sorted({r["status"] for r in results})
        },
        "agreement_metrics": metrics,
        "conflict_types": conflict_types,
        "instances": results,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
    with open(args.report + ".json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    with open(args.report + ".md", "w", encoding="utf-8") as fh:
        fh.write(render_markdown(results, name_a, name_b, metrics, conflict_types))
        fh.write("\n")

    id_files = write_id_lists(args.report, results)

    print(f"considered {len(results)} instances")
    for status, n in report["counts"].items():
        print(f"  {status}: {n}")
    print("per-location agreement (Jaccard macro / micro, Dice, alpha-MASI):")
    for g in GRANULARITIES:
        m = metrics[g]
        print(f"  {g:<9} J={m['jaccard_macro']:.3f}/{m['jaccard_micro']:.3f}  "
              f"Dice={m['dice_micro']:.3f}  alpha={m['alpha_masi']:.3f}")
    if conflict_types:
        total = sum(conflict_types.values())
        parts = ", ".join(f"{t}={n} ({n / total:.0%})"
                          for t, n in sorted(conflict_types.items(),
                                             key=lambda kv: -kv[1]))
        print(f"conflict types: {parts}")
    for r in results:
        if r["status"] in ("conflict", "minor_conflict"):
            kinds = ", ".join(sorted({c["type"] for c in r["conflicts"]}))
            print(f"  ! {r['instance_id']}  [{r['status']}]  {kinds}")
    print(f"report: {args.report}.json / {args.report}.md")
    for path in id_files:
        with open(path, encoding="utf-8") as fh:
            n = sum(1 for line in fh if line.strip())
        print(f"  ids: {os.path.basename(path)} ({n})")
    if args.write:
        print(f"merged files written: {written} -> {args.out}")
    else:
        print("dry run — pass --write to emit merged files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
