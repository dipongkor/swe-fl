#!/usr/bin/env python3
"""LLM-as-jury for inter-annotator *reasoning* alignment on agreed instances.

Location agreement is already established by merge_annotations.py.  This asks a
different question about the ``agree`` instances: when both annotators point at
the same root-cause location, do they describe the *same causal mechanism*?

Design (aligned with the LLM-as-a-judge survey [Gu2026], section by section):
  * Multi-model jury  - the survey's endorsed recipe for a labelling/pairwise
    judge is "strong models + position swap + majority vote"
    [Gu2026, "Experiment summary", p.18], and it warns against trusting a
    single model ["Model selection", p.5; Box 6, p.8].  Integrating verdicts
    from multiple *different* LLMs is the survey's "vote by multiple LLMs"
    strategy ["Integrating multi-source evaluation results", p.13].  Jurors are
    drawn from different model *families* so their errors are decorrelated - a
    genuine jury, not one model sampled repeatedly.  (This replaces the earlier
    single-model 3-lens panel, whose only purpose was to fake diversity because
    Opus 4.8 rejects the temperature parameter.)
  * Order-swap  - each juror judges every instance twice with Annotator 1/2
    swapped, to cancel position bias ["Judgment-specific biases: Position
    bias", pp.14-15; swap-and-vote mitigation, "Prompt design strategy", p.12].
  * Few-shot rubric anchoring  - one worked example per label in the rubric
    ["Improving LLMs' task understanding": few-shot prompting, p.9].
  * Structured output  - every verdict is a forced JSON object
    ["Standardizing LLMs' output format", p.12; "Constrained decoding", p.7].
  * Majority vote across all (juror x ordering) verdicts is the final label;
    the survey found majority voting (majority@5) the only multi-run
    aggregation that helps, over mean/best ["Experiment summary", p.18].
  * Validation  - judge-human agreement on a labelled subset (judge_validation.py)
    is what licenses trusting the full-set verdicts.  The survey names Cohen's
    kappa / percentage agreement as the agreement metrics ["Agreement with
    human judgments", p.13] and explicitly endorses adapting Cohen's kappa or
    Krippendorff's alpha for judge reliability ["Theoretically grounded
    evaluation", p.23].

Self-enhancement bias ["Task-agnostic biases: Self-enhancement bias", p.15]
does NOT apply here: the annotations are human-written, so no juror can favour
its own output.  Reported as out-of-scope, not unaddressed.

The jury runs synchronously with bounded concurrency; each provider uses its
own official SDK and structured-output mode.

Usage:
    python reasoning_judge.py --dry-run                 # build requests + cost
    python reasoning_judge.py --run                     # run jury, write reports
    python reasoning_judge.py --limit 5 --run           # smoke test
    python reasoning_judge.py --jurors anthropic --run  # subset of jurors

References:
    [Gu2026] Gu, J., Jiang, X., Shi, Z., et al. (2026). A survey on
        LLM-as-a-judge. The Innovation 7(6):101253.
        https://doi.org/10.1016/j.xinn.2025.101253
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO = os.path.dirname(os.path.abspath(__file__))
REPORT_JSON = os.path.join(REPO, "annotation", "merge_report.json")
DIR_A = os.path.join(REPO, "annotation", "Atish_Annotation")
DIR_B = os.path.join(REPO, "annotation", "Eshgin_Annotation")
NAME_A, NAME_B = "Atish", "Eshgin"

OUT_DIR = os.path.join(REPO, "annotation", "reasoning_alignment")
MANIFEST_FILE = os.path.join(OUT_DIR, "manifest.json")
RAW_FILE = os.path.join(OUT_DIR, "raw_results.json")
REPORT_OUT = os.path.join(OUT_DIR, "reasoning_alignment_report")

MAX_TOKENS = 4096
EFFORT = "high"           # Anthropic reasoning effort
MAX_WORKERS = 8           # concurrent in-flight requests across all providers
RETRIES = 3

# The jury: one strong model per family, so their errors are decorrelated
# [Gu2026, "Integrating multi-source evaluation results", p.13 - "vote by
# multiple LLMs"; use different families to avoid self-enhancement bias, p.15].
# Anthropic is known-good in this environment.  Set the OpenAI/Google model IDs
# to models you can actually call before running with those jurors - the script
# errors clearly (missing SDK / missing API key) rather than guessing.
JURORS = [
    {"provider": "anthropic", "model": "claude-opus-4-8"},
    {"provider": "openai",    "model": "gpt-5.3-codex"},          # <- set to your model
    {"provider": "google",    "model": "gemini-3.6-flash"},  # <- set to your model
]

# alignment scale, ordered least -> most divergent (used for tie-breaks)
LABELS = ["aligned", "partial", "divergent", "contradictory"]
LABEL_RANK = {lab: i for i, lab in enumerate(LABELS)}

# Forced JSON verdict [Gu2026, "Standardizing LLMs' output format", p.12].
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "alignment": {"type": "string", "enum": LABELS},
        "shared_mechanism": {"type": "string"},
        "differences": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "rationale": {"type": "string"},
    },
    "required": ["alignment", "shared_mechanism", "differences",
                 "confidence", "rationale"],
    "additionalProperties": False,
}

# --------------------------------------------------------------------------- #
# rubric (shared verbatim across every juror x ordering; prompt-cached on
# Anthropic via cache_control).  One worked example per label = few-shot
# anchoring [Gu2026, "Improving LLMs' task understanding", p.9].
# --------------------------------------------------------------------------- #

RUBRIC = """\
You are an expert software-fault-localization researcher grading inter-annotator \
agreement for a study. Two annotators independently identified the same faulty \
line in a program and each wrote a short explanation of the *mechanism* of the \
fault - why that line causes the failure. Their explanations describe mechanism \
only (they never mention the fix).

Your job: judge how well the two mechanisms ALIGN. They point at the same code, \
so the question is never *where* the fault is - it is whether they explain the \
*same causal story*. Wording, length, and level of detail do not matter; the \
underlying mechanism does.

Assign exactly one label:

- "aligned": Same causal mechanism. Both describe the same faulty behavior \
producing the same failure. They may differ only in wording or in how much \
detail they give.
    Example - A: "returns None when the cache misses, and the caller dereferences \
it." B: "on a cache miss the function yields a null that the caller then uses \
without a guard." -> aligned.

- "partial": Overlapping but incomplete. One annotator identifies a mechanistic \
step, condition, or cause that the other omits, though what they do say is \
consistent.
    Example - A: "the index is off by one so it reads past the array." B: "it \
reads the wrong element because the loop bound is wrong, and when the input is \
empty it also reads out of bounds." -> partial (B adds the empty-input path).

- "divergent": Different mechanisms for the same line. Both are plausible, not \
mutually exclusive, but they are not the same causal story.
    Example - A: "the value is wrong because it is computed before the config is \
loaded." B: "the value is wrong because the wrong unit conversion is applied." \
-> divergent.

- "contradictory": Mechanisms that cannot both be the true cause - they make \
incompatible claims about what goes wrong.
    Example - A: "the branch is taken when the flag is true, which is the bug." \
B: "the bug is that the branch is skipped when the flag is true." \
-> contradictory.

Set "confidence" to how sure you are of the label. Put what BOTH annotators \
convey in "shared_mechanism", and what one says that the other does not (or where \
they conflict) in "differences" (empty string if none). Keep "rationale" to one \
or two sentences. Return the single best-fitting label from the four above."""


def build_user_content(reasoning_1: str, reasoning_2: str) -> str:
    return (
        f"Annotator 1 reasoning:\n\"\"\"\n{reasoning_1.strip()}\n\"\"\"\n\n"
        f"Annotator 2 reasoning:\n\"\"\"\n{reasoning_2.strip()}\n\"\"\""
    )


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #

def read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def agreed_instance_ids() -> list[str]:
    """Instances the merge marked ``agree`` - derived from the report, not the
    possibly-stale id-list text file."""
    report = read_json(REPORT_JSON)
    return sorted(i["instance_id"] for i in report["instances"]
                  if i["status"] == "agree")


def reasoning_of(directory: str, iid: str) -> str:
    return str(read_json(os.path.join(directory, iid + ".json")).get("reasoning") or "")


def build_requests(iids: list[str], jurors: list[dict]) -> tuple[list[dict], dict]:
    """Return (request specs, manifest).

    One request per (instance, ordering, juror).  ``cid`` is a short opaque
    index; the manifest maps it back to (instance, ordering, provider, model).
    Each spec also carries the blinded ``user`` text (not stored in the
    manifest).
    """
    specs, manifest = [], {}
    idx = 0
    for iid in iids:
        ra, rb = reasoning_of(DIR_A, iid), reasoning_of(DIR_B, iid)
        # Order-swap to cancel position bias [Gu2026, "Position bias", pp.14-15].
        # ordering 0: A is Annotator 1.  ordering 1: swapped.
        for ordering, (r1, r2) in enumerate([(ra, rb), (rb, ra)]):
            user = build_user_content(r1, r2)
            for juror in jurors:
                cid = f"c{idx}"
                meta = {"instance_id": iid, "ordering": ordering,
                        "provider": juror["provider"], "model": juror["model"]}
                manifest[cid] = meta
                specs.append({"cid": cid, "user": user, **meta})
                idx += 1
    return specs, manifest


# --------------------------------------------------------------------------- #
# provider backends (each uses its own official SDK + structured-output mode)
# --------------------------------------------------------------------------- #

_CLIENTS: dict[str, object] = {}


def _client(provider: str):
    if provider not in _CLIENTS:
        if provider == "anthropic":
            import anthropic
            _CLIENTS[provider] = anthropic.Anthropic()
        elif provider == "openai":
            from openai import OpenAI
            _CLIENTS[provider] = OpenAI()
        elif provider == "google":
            from google import genai
            _CLIENTS[provider] = genai.Client()
        else:
            raise ValueError(f"unknown provider {provider!r}")
    return _CLIENTS[provider]


def _anthropic_call(model: str, system_text: str, user_text: str) -> dict:
    msg = _client("anthropic").messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={
            "effort": EFFORT,
            "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
        },
        system=[{"type": "text", "text": system_text,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_text}],
    )
    text = next((b.text for b in msg.content if b.type == "text"), None)
    return json.loads(text)


def _openai_call(model: str, system_text: str, user_text: str) -> dict:
    # Responses API (v1/responses): reasoning/codex-family models reject
    # chat/completions, and Responses also serves older models.  Structured
    # output via text.format json_schema (strict).  OUTPUT_SCHEMA already sets
    # additionalProperties:false and lists every field as required.
    resp = _client("openai").responses.create(
        model=model,
        instructions=system_text,
        input=user_text,
        text={"format": {"type": "json_schema",
                         "name": "alignment_verdict",
                         "schema": OUTPUT_SCHEMA,
                         "strict": True}},
    )
    return json.loads(resp.output_text)


def _google_call(model: str, system_text: str, user_text: str) -> dict:
    from google.genai import types
    resp = _client("google").models.generate_content(
        model=model,
        contents=user_text,
        config=types.GenerateContentConfig(
            system_instruction=system_text,
            response_mime_type="application/json",
            # Gemini's response_schema is an OpenAPI-subset and rejects
            # `additionalProperties`; send the schema without it.
            response_schema={k: v for k, v in OUTPUT_SCHEMA.items()
                             if k != "additionalProperties"},
        ),
    )
    return json.loads(resp.text)


_CALLERS = {"anthropic": _anthropic_call,
            "openai": _openai_call,
            "google": _google_call}


def run_request(spec: dict) -> dict:
    """Execute one juror verdict with retries; returns meta + verdict or error."""
    meta = {k: spec[k] for k in ("cid", "instance_id", "ordering",
                                 "provider", "model")}
    caller = _CALLERS[spec["provider"]]
    last: dict = {"error": "unknown"}
    for attempt in range(RETRIES):
        try:
            verdict = caller(spec["model"], RUBRIC, spec["user"])
            if isinstance(verdict, dict) and verdict.get("alignment") in LABEL_RANK:
                return {**meta, **verdict}
            last = {"error": "bad_output", "raw": verdict}
        except Exception as e:                       # noqa: BLE001 - record any failure
            last = {"error": type(e).__name__, "detail": str(e)[:300]}
            time.sleep(2 ** attempt)
    return {**meta, **last}


def preflight(providers: list[str]) -> None:
    """Fail fast with a clear message if a selected juror's SDK/key is missing."""
    problems = []
    for p in sorted(set(providers)):
        try:
            _client(p)
        except ModuleNotFoundError as e:
            pkg = {"anthropic": "anthropic", "openai": "openai",
                   "google": "google-genai"}.get(p, p)
            problems.append(f"  {p}: SDK not installed - run: pip install {pkg}")
        except Exception as e:                        # missing key, bad config, ...
            problems.append(f"  {p}: {type(e).__name__}: {str(e)[:160]}")
    if problems:
        sys.exit("cannot start jury; fix these jurors (or drop them with "
                 "--jurors):\n" + "\n".join(problems))


def run_jury(specs: list[dict]) -> dict:
    raw: dict = {}
    total = len(specs)
    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(run_request, s): s["cid"] for s in specs}
        for fut in as_completed(futs):
            res = fut.result()
            raw[res["cid"]] = res
            done += 1
            if done % 25 == 0 or done == total:
                errs = sum(1 for r in raw.values() if "alignment" not in r)
                print(f"  {done}/{total} verdicts ({errs} failed so far)")
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(RAW_FILE, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, indent=2, ensure_ascii=False)
    return raw


# --------------------------------------------------------------------------- #
# aggregation
# --------------------------------------------------------------------------- #

def majority(labels: list[str]) -> str:
    """Most common label; ties broken toward the more-divergent (conservative).

    Majority voting is the only multi-run aggregation the survey found reliably
    helpful (over mean/best) [Gu2026, "Experiment summary", p.18].
    """
    counts = Counter(labels)
    top = max(counts.values())
    tied = [lab for lab, n in counts.items() if n == top]
    return max(tied, key=lambda lab: LABEL_RANK[lab])


def aggregate(raw: dict, manifest: dict) -> dict:
    per_instance: dict[str, list[dict]] = {}
    for cid, meta in manifest.items():
        verdict = raw.get(cid, {"error": "missing"})
        per_instance.setdefault(meta["instance_id"], []).append({**meta, **verdict})

    results = {}
    for iid, votes in per_instance.items():
        good = [v for v in votes if v.get("alignment") in LABEL_RANK]
        if not good:
            results[iid] = {"final_alignment": None, "flagged": True,
                            "flag_reason": "no valid verdicts", "votes": votes}
            continue

        final = majority([v["alignment"] for v in good])

        # per-ordering majority (position-bias signal)
        order_labels = {}
        for o in (0, 1):
            labs = [v["alignment"] for v in good if v["ordering"] == o]
            order_labels[o] = majority(labs) if labs else None
        order_disagreement = (order_labels.get(0) != order_labels.get(1)
                              and None not in order_labels.values())

        # per-model majority (cross-family robustness signal)
        model_labels = {}
        for prov in sorted({v["provider"] for v in good}):
            labs = [v["alignment"] for v in good if v["provider"] == prov]
            model_labels[prov] = majority(labs) if labs else None
        model_disagreement = len(set(model_labels.values())) > 1

        confidences = [v.get("confidence") for v in good]
        low_conf = Counter(confidences).get("low", 0) >= len(good) / 2

        reasons = []
        if model_disagreement:
            reasons.append("cross-model disagreement")
        if order_disagreement:
            reasons.append("order-swap disagreement")
        if final in ("divergent", "contradictory"):
            reasons.append(f"final={final}")
        if low_conf:
            reasons.append("low confidence")
        if len(good) < len(votes):
            reasons.append(f"{len(votes) - len(good)} verdict(s) failed")

        results[iid] = {
            "final_alignment": final,
            "order0_label": order_labels.get(0),
            "order1_label": order_labels.get(1),
            "order_disagreement": order_disagreement,
            "model_labels": model_labels,
            "model_disagreement": model_disagreement,
            "label_counts": dict(Counter(v["alignment"] for v in good)),
            "flagged": bool(reasons),
            "flag_reason": "; ".join(reasons),
            "votes": votes,
        }
    return results


def write_reports(results: dict, jurors: list[dict]) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(REPORT_OUT + ".json", "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)

    dist = Counter(r["final_alignment"] for r in results.values())
    flagged = {iid: r for iid, r in results.items() if r["flagged"]}
    model_split = sum(1 for r in results.values() if r.get("model_disagreement"))
    order_split = sum(1 for r in results.values() if r.get("order_disagreement"))
    jury_str = ", ".join(f"{j['provider']}:{j['model']}" for j in jurors)

    lines = ["# Reasoning-alignment report", "",
             f"- Instances judged: **{len(results)}**",
             f"- Jury: {jury_str}",
             "- Each juror judges every instance twice (2 orderings); the final "
             "label is the majority across all juror x ordering verdicts.", "",
             "## Final alignment distribution", ""]
    for lab in LABELS + [None]:
        if dist.get(lab):
            lines.append(f"- {lab}: **{dist[lab]}**")
    lines += ["",
              "## Reliability signals", "",
              f"- Cross-model disagreements: **{model_split}** / {len(results)}",
              f"- Order-swap disagreements: **{order_split}** / {len(results)}", "",
              f"## Flagged for manual adjudication ({len(flagged)})", "",
              "Cross-model or order-swap disagreements, divergent/contradictory "
              "finals, low-confidence, or failed verdicts.", ""]
    for iid, r in sorted(flagged.items()):
        lines.append(f"### {iid}")
        lines.append(f"- final: **{r['final_alignment']}** ({r.get('flag_reason')})")
        lines.append(f"- per-model: {r.get('model_labels')}")
        lines.append(f"- label counts: {r.get('label_counts')}, "
                     f"order0={r.get('order0_label')}, order1={r.get('order1_label')}")
        lines.append("")
    with open(REPORT_OUT + ".md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print(f"instances judged: {len(results)}")
    for lab in LABELS + [None]:
        if dist.get(lab):
            print(f"  {lab}: {dist[lab]}")
    print(f"cross-model disagreements: {model_split}; "
          f"order-swap disagreements: {order_split}; flagged: {len(flagged)}")
    print(f"report: {REPORT_OUT}.json / {REPORT_OUT}.md")


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def cost_estimate(n_instances: int, jurors: list[dict]) -> None:
    per_call_in, per_call_out = 900, 500          # rubric + reasonings; thinking + JSON
    calls_per_juror = n_instances * 2             # 2 orderings
    print(f"  {len(jurors)} juror(s) x {calls_per_juror} calls each "
          f"= {len(jurors) * calls_per_juror} synchronous requests")
    # very rough, Opus-tier pricing as a stand-in; real cost depends on each
    # juror's per-token price and whether prompt caching applies.
    approx = len(jurors) * calls_per_juror * (per_call_in / 1e6 * 5.0
                                              + per_call_out / 1e6 * 25.0)
    print(f"  rough order-of-magnitude cost: ${approx:.2f} "
          "(no batch discount; caching lowers input cost)")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true",
                   help="build requests, print count/cost, write manifest; no API")
    p.add_argument("--run", action="store_true",
                   help="run the jury synchronously, then write reports")
    p.add_argument("--limit", type=int, default=None,
                   help="only the first N agreed instances (smoke test)")
    p.add_argument("--jurors", default=None,
                   help="comma-separated provider subset (default: all in JURORS)")
    args = p.parse_args(argv)

    jurors = JURORS
    if args.jurors:
        want = {s.strip() for s in args.jurors.split(",") if s.strip()}
        jurors = [j for j in JURORS if j["provider"] in want]
        if not jurors:
            sys.exit(f"no jurors match {sorted(want)}; "
                     f"available: {[j['provider'] for j in JURORS]}")

    iids = agreed_instance_ids()
    if args.limit:
        iids = iids[:args.limit]

    specs, manifest = build_requests(iids, jurors)
    print(f"agreed instances: {len(iids)}  ->  {len(specs)} jury requests "
          f"({len(jurors)} jurors x 2 orderings)")
    cost_estimate(len(iids), jurors)

    if args.dry_run:
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(MANIFEST_FILE, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)
        print(f"dry run - manifest written to {MANIFEST_FILE}, nothing submitted")
        return 0

    if not args.run:
        p.error("choose --dry-run or --run")

    preflight([j["provider"] for j in jurors])
    with open(MANIFEST_FILE, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    raw = run_jury(specs)
    write_reports(aggregate(raw, manifest), jurors)
    return 0


if __name__ == "__main__":
    sys.exit(main())
