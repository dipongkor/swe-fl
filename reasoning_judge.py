#!/usr/bin/env python3
"""LLM-as-annotator jury for inter-annotator *reasoning* alignment.

Location agreement is already established by merge_annotations.py.  This asks a
different question about the ``agree`` instances: when both annotators point at
the same root-cause location, do they describe the *same causal mechanism*?

In the study-type taxonomy of Baltes et al. this is the LLM-as-ANNOTATOR role
(closed coding against a predefined coding guide), not the judge role (rating
artifacts on quality criteria).  The mechanics below are borrowed from the
LLM-as-a-judge literature because the pairwise, rubric-driven, structured-verdict
setup is the same.

Design, with the primary source for each decision:

  * Panel of jurors from disjoint model families [Verga2024].  A panel of
    diverse models beats a single large judge and shows less intra-model bias.
    Not assumed superior here - judge_validation.py tests it against the best
    single juror with a paired bootstrap, because correlated jurors can dilute
    the strongest member's signal.
  * Order-swap: every juror codes every instance twice with Annotator 1/2
    swapped, to expose position bias [Wang2024].  The codebook is symmetric, so
    any flip is attributable to position, not to the rubric.
  * Self-consistency: each (juror, ordering) is sampled REPEATS times and the
    distribution is retained [Wang2023].  This separates stochastic noise from
    genuine inter-juror disagreement - impossible when each cell is sampled once.
  * Rubric with one worked example per label, and form-filling structured
    output [Liu2023].  Every verdict is a forced JSON object.
  * Response-set elicitation: alongside the forced choice, each juror returns
    every label it considers defensible [Guerdan2025].  Forced-choice-only
    validation selects substantially worse judge systems when the rating task
    admits multiple valid readings, which the partial/divergent boundary does.
  * Aggregation ABSTAINS rather than tie-breaking.  Any fixed tie-break rule
    imposes a directional prior on the distribution the study reports.
    Abstentions are routed to human adjudication [Jung2025].
  * Uncertainty is measured by vote entropy, not by the jurors' verbalized
    confidence, which is poorly calibrated.  Model-model agreement is reported
    as Krippendorff's alpha and read against Krippendorff's thresholds
    (< 0.667 discard, >= 0.8 reliable), not the lower screening threshold used
    in earlier SE work [Ahmed2025, Baltes2026].

Self-enhancement bias does not apply: the annotations are human-written, so no
juror can favour its own output.  Out of scope, not unaddressed.

Every call is cached on disk, so a crashed or interrupted run resumes for free
and a re-run costs nothing.  The cache key includes the rubric text, so editing
the rubric correctly invalidates it.

Usage:
    python reasoning_judge.py --dry-run                  # requests + cost, no API
    python reasoning_judge.py --run                      # run jury, write reports
    python reasoning_judge.py --limit 5 --run            # smoke test
    python reasoning_judge.py --jurors anthropic --run   # subset of jurors
    python reasoning_judge.py --repeats 3 --run          # self-consistency
    python reasoning_judge.py --run --no-cache           # ignore cached verdicts

References:
    [Verga2024]  Verga et al. Replacing Judges with Juries. arXiv:2404.18796.
    [Wang2024]   Wang et al. Large Language Models are not Fair Evaluators.
                 ACL 2024, 9440-9450.
    [Wang2023]   Wang et al. Self-Consistency Improves Chain of Thought
                 Reasoning in Language Models. ICLR 2023.
    [Liu2023]    Liu et al. G-Eval. EMNLP 2023.
    [Guerdan2025] Guerdan et al. Validating LLM-as-a-Judge Systems under Rating
                 Indeterminacy. NeurIPS 2025.
    [Jung2025]   Jung, Brahman, Choi. Trust or Escalate. ICLR 2025.
    [Ahmed2025]  Ahmed et al. Can LLMs Replace Manual Annotation of Software
                 Engineering Artifacts? MSR 2025, 526-538.
    [Baltes2026] Baltes et al. Guidelines for Empirical Studies in Software
                 Engineering Involving LLMs. EMSE (accepted).
                 https://llm-guidelines.org
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import os
import random
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO = os.path.dirname(os.path.abspath(__file__))
REPORT_JSON = os.path.join(REPO, "annotation", "merge_report.json")
DIR_A = os.path.join(REPO, "annotation", "Atish_Annotation")
DIR_B = os.path.join(REPO, "annotation", "Eshgin_Annotation")
NAME_A, NAME_B = "Atish", "Eshgin"

OUT_DIR = os.path.join(REPO, "annotation", "reasoning_alignment")
MANIFEST_FILE = os.path.join(OUT_DIR, "manifest.json")
RAW_FILE = os.path.join(OUT_DIR, "raw_results.json")
CACHE_FILE = os.path.join(OUT_DIR, "verdict_cache.jsonl")
CONFIG_FILE = os.path.join(OUT_DIR, "run_config.json")
REPORT_OUT = os.path.join(OUT_DIR, "reasoning_alignment_report")

MAX_TOKENS = 4096
EFFORT = "high"              # Anthropic reasoning effort
RETRIES = 3
MIN_REASONING_CHARS = 15     # below this, treat the annotation as unusable

# Per-provider concurrency. A single global pool lets one provider's rate limit
# throttle the others; separate semaphores keep each within its own budget.
PROVIDER_CONCURRENCY = {"anthropic": 4, "openai": 4, "google": 4, "mock": 8}

# The jury: one strong general-purpose model per family, so errors are less
# correlated [Verga2024]. NOTE: do not use a code-specialized model (e.g. a
# *-codex variant) as a juror - the task is rubric-following on natural-language
# rationales, and a reviewer can reasonably ask why a coding model was chosen.
#
# `temperature`: set explicitly for reproducibility [Baltes2026]. Use None for
# jurors whose reasoning/thinking mode rejects the parameter; those jurors are
# still sampled REPEATS times, which measures backend nondeterminism rather
# than sampling variance. VERIFY each model ID and parameter shape against the
# provider's current API docs before running.
JURORS = [
    {"provider": "anthropic", "model": "claude-opus-4-8",   "temperature": None},
    {"provider": "openai",    "model": "gpt-5.3-codex",           "temperature": None},
    {"provider": "google",    "model": "gemini-3.6-flash",  "temperature": 0.0},
]

# Nominal codes. LABELS is an ordering for display only - it is NOT an ordinal
# scale, and nothing in this file breaks ties or weights distances by it.
LABELS = ["aligned", "partial", "divergent", "contradictory"]
LABEL_SET = set(LABELS)

LABEL_DESC = {
    "aligned": "Mutually recoverable mechanisms; neither adds causal content "
               "the other lacks (may differ in wording or detail).",
    "partial": "One-way subsumption; one annotator's mechanism strictly "
               "elaborates the other's, with no conflict between them.",
    "divergent": "Incomparable mechanisms; each has causal content the other "
                 "lacks, but both could hold at once.",
    "contradictory": "Incompatible mechanisms that cannot both be true; the "
                     "annotators make opposing claims about what the code does.",
}

# PRIMARY code = the binary conflict question.  The aligned<->partial boundary is
# a directional "one-way subsumption" test, so it is position-sensitive and
# order-swap flips it ~30% of the time (Krippendorff alpha < floor).  Collapsing
# to consistent (aligned+partial) vs conflicting (divergent+contradictory) is
# order-invariant and is what the study actually asks ("do the annotators
# conflict?").  The 4-way split is retained as an ORDER-SENSITIVE DIAGNOSTIC only.
BINARY_OF = {"aligned": "consistent", "partial": "consistent",
             "divergent": "conflicting", "contradictory": "conflicting"}
BINARY_LABELS = ["consistent", "conflicting"]

# Forced JSON verdict [Liu2023], plus the response set [Guerdan2025].
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "alignment": {"type": "string", "enum": LABELS},
        "plausible_alignments": {
            "type": "array",
            "items": {"type": "string", "enum": LABELS},
            "minItems": 1,
        },
        "shared_mechanism": {"type": "string"},
        "differences": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "rationale": {"type": "string"},
    },
    "required": ["alignment", "plausible_alignments", "shared_mechanism",
                 "differences", "confidence", "rationale"],
    "additionalProperties": False,
}

# --------------------------------------------------------------------------- #
# rubric
#
# The four codes partition the space by the direction of subsumption between the
# two mechanisms, which makes the boundaries checkable rather than intuitive:
#   aligned       mutual  (each recoverable from the other)
#   partial       one-way (B strictly elaborates A, or vice versa)
#   divergent     neither (incomparable but compatible)
#   contradictory conflict
# --------------------------------------------------------------------------- #

RUBRIC = """\
You are an expert software-fault-localization researcher coding inter-annotator \
agreement for a study. Two annotators independently identified the same faulty \
line in a program and each wrote a short explanation of the *mechanism* of the \
fault - why that line causes the failure. Their explanations describe mechanism \
only (they never mention the fix).

Your job: code the relation between the two mechanisms. They point at the same \
code, so the question is never *where* the fault is - it is how the two causal \
stories relate. Wording, length, and level of detail do not matter on their own; \
what matters is whether one explanation carries causal content the other lacks.

Decide by asking, in order:
  1. Do they make claims about the code's behavior that cannot both be true?
     -> "contradictory"
  2. Otherwise, can each mechanism be recovered from the other - would rewriting
     one in the other's words lose nothing?  -> "aligned"
  3. Otherwise, does one strictly elaborate the other - same causal chain, but
     one names a step, condition, or cause the other omits?  -> "partial"
  4. Otherwise, each has causal content the other lacks, yet both could hold at
     once.  -> "divergent"

Worked examples:

- "aligned": A: "returns None when the cache misses, and the caller dereferences \
it." B: "on a cache miss the function yields a null that the caller then uses \
without a guard." -> Same chain, different words; nothing is lost either way.

- "partial": A: "the value is stale because the cache is never invalidated." \
B: "the cache is never invalidated when the config reloads, so the value is \
stale." -> B names the triggering condition (config reload) that A omits; A adds \
nothing B lacks. One-way subsumption.

- "divergent": A: "the value is wrong because it is computed before the config \
is loaded." B: "the value is wrong because the wrong unit conversion is \
applied." -> Two independent causes. Neither subsumes the other, but both could \
be true of the same line.

- "contradictory": A: "the branch is taken when the flag is true, which is the \
bug." B: "the bug is that the branch is skipped when the flag is true." \
-> Opposing claims about what the code does.

Output fields:
- "alignment": the single best-fitting code.
- "plausible_alignments": every code you consider defensible for this pair, \
including the one you chose. Give more than one ONLY when the pair genuinely \
admits more than one reading - do not hedge by listing all four.
- "shared_mechanism": what BOTH annotators convey.
- "differences": what one says that the other does not, or where they conflict \
(empty string if none).
- "confidence": how sure you are of the chosen code.
- "rationale": one or two sentences."""

RUBRIC_HASH = hashlib.sha256(RUBRIC.encode()).hexdigest()[:12]


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
    """Instances the merge marked ``agree``, from the report (not a stale list)."""
    report = read_json(REPORT_JSON)
    return sorted(i["instance_id"] for i in report["instances"]
                  if i["status"] == "agree")


def reasoning_of(directory: str, iid: str) -> str:
    return str(read_json(os.path.join(directory, iid + ".json")).get("reasoning") or "")


def partition_instances(iids: list[str]) -> tuple[list[str], dict]:
    """Split into codeable instances and malformed ones.

    An empty or near-empty rationale is a DATA problem, not a `partial` code.
    Judging it silently would conflate "the annotator wrote nothing" with "the
    annotator described less mechanism", which is exactly the distinction the
    partial code is supposed to carry.
    """
    ok, malformed = [], {}
    for iid in iids:
        ra, rb = reasoning_of(DIR_A, iid), reasoning_of(DIR_B, iid)
        short = []
        if len(ra.strip()) < MIN_REASONING_CHARS:
            short.append(f"{NAME_A} ({len(ra.strip())} chars)")
        if len(rb.strip()) < MIN_REASONING_CHARS:
            short.append(f"{NAME_B} ({len(rb.strip())} chars)")
        if short:
            malformed[iid] = "missing/near-empty reasoning: " + ", ".join(short)
        else:
            ok.append(iid)
    return ok, malformed


def build_requests(iids: list[str], jurors: list[dict],
                   repeats: int) -> tuple[list[dict], dict]:
    """One request per (instance, ordering, juror, repeat)."""
    specs, manifest = [], {}
    idx = 0
    for iid in iids:
        ra, rb = reasoning_of(DIR_A, iid), reasoning_of(DIR_B, iid)
        # ordering 0: A is Annotator 1. ordering 1: swapped [Wang2024].
        for ordering, (r1, r2) in enumerate([(ra, rb), (rb, ra)]):
            user = build_user_content(r1, r2)
            for juror in jurors:
                for rep in range(repeats):
                    cid = f"c{idx}"
                    meta = {"instance_id": iid, "ordering": ordering,
                            "provider": juror["provider"],
                            "model": juror["model"],
                            "temperature": juror.get("temperature"),
                            "repeat": rep}
                    manifest[cid] = meta
                    specs.append({"cid": cid, "user": user, **meta})
                    idx += 1
    return specs, manifest


# --------------------------------------------------------------------------- #
# on-disk cache (append-only JSONL; makes any run resumable)
# --------------------------------------------------------------------------- #

_cache_lock = threading.Lock()


def cache_key(spec: dict) -> str:
    payload = "|".join([spec["provider"], spec["model"], RUBRIC_HASH,
                        str(spec.get("temperature")), str(spec["repeat"]),
                        spec["user"]])
    return hashlib.sha256(payload.encode()).hexdigest()


def load_cache() -> dict:
    if not os.path.exists(CACHE_FILE):
        return {}
    out = {}
    with open(CACHE_FILE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue          # tolerate a truncated final line after a kill
            if rec.get("key"):
                out[rec["key"]] = rec["value"]
    return out


def cache_put(key: str, value: dict) -> None:
    with _cache_lock:
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(CACHE_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"key": key, "value": value},
                                ensure_ascii=False) + "\n")
            fh.flush()


# --------------------------------------------------------------------------- #
# provider backends
# --------------------------------------------------------------------------- #

_CLIENTS: dict[str, object] = {}
_client_lock = threading.Lock()


def _client(provider: str):
    with _client_lock:
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
            elif provider == "mock":
                _CLIENTS[provider] = object()
            else:
                raise ValueError(f"unknown provider {provider!r}")
    return _CLIENTS[provider]


def _anthropic_call(model, system_text, user_text, temperature):
    kwargs = dict(
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
    if temperature is not None:
        kwargs["temperature"] = temperature
    msg = _client("anthropic").messages.create(**kwargs)
    text = next((b.text for b in msg.content if b.type == "text"), None)
    if text is None:
        raise SchemaError("no text block in response")
    return _parse_json(text)


def _openai_call(model, system_text, user_text, temperature):
    kwargs = dict(
        model=model,
        instructions=system_text,
        input=user_text,
        text={"format": {"type": "json_schema",
                         "name": "alignment_verdict",
                         "schema": OUTPUT_SCHEMA,
                         "strict": True}},
    )
    if temperature is not None:
        kwargs["temperature"] = temperature
    resp = _client("openai").responses.create(**kwargs)
    return _parse_json(resp.output_text)


def _google_call(model, system_text, user_text, temperature):
    from google.genai import types
    cfg = dict(
        system_instruction=system_text,
        response_mime_type="application/json",
        # Gemini's response_schema is an OpenAPI subset and rejects
        # `additionalProperties`; send the schema without it.
        response_schema={k: v for k, v in OUTPUT_SCHEMA.items()
                         if k != "additionalProperties"},
    )
    if temperature is not None:
        cfg["temperature"] = temperature
    resp = _client("google").models.generate_content(
        model=model, contents=user_text,
        config=types.GenerateContentConfig(**cfg))
    return _parse_json(resp.text)


def _mock_call(model, system_text, user_text, temperature):
    """Offline juror for testing the pipeline without spending money.

    The label is driven by the instance (order-invariant, so orderings mostly
    agree) with per-call noise, which mimics a real juror well enough to
    exercise abstention, flips, and entropy. Never used unless --mock is passed.
    """
    blocks = tuple(sorted(user_text.split('"""')))     # order-invariant identity
    base = random.Random(hashlib.sha256(
        ("".join(blocks) + model).encode()).hexdigest())
    lab = base.choices(LABELS, weights=[60, 22, 12, 6])[0]
    noise = random.Random()                            # per-call, non-reproducible
    if noise.random() < 0.15:
        lab = noise.choice(LABELS)
    alt = [lab] if noise.random() < 0.8 else sorted({lab, noise.choice(LABELS)},
                                                    key=LABELS.index)
    return {"alignment": lab, "plausible_alignments": alt,
            "shared_mechanism": "mock", "differences": "",
            "confidence": noise.choice(["high", "medium", "low"]),
            "rationale": "mock verdict"}


_CALLERS = {"anthropic": _anthropic_call, "openai": _openai_call,
            "google": _google_call, "mock": _mock_call}


class SchemaError(Exception):
    """The call succeeded but the payload is unusable. Retrying will not help."""


def _parse_json(text):
    if text is None:
        raise SchemaError("empty response body")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise SchemaError(f"non-JSON response: {str(e)[:80]} :: {text[:200]!r}")


def _validate(verdict) -> dict:
    if not isinstance(verdict, dict):
        raise SchemaError(f"not an object: {type(verdict).__name__}")
    if verdict.get("alignment") not in LABEL_SET:
        raise SchemaError(f"bad alignment {verdict.get('alignment')!r}")
    plaus = verdict.get("plausible_alignments") or [verdict["alignment"]]
    plaus = [p for p in plaus if p in LABEL_SET]
    if verdict["alignment"] not in plaus:
        plaus.append(verdict["alignment"])       # forced choice must be in the set
    verdict["plausible_alignments"] = sorted(set(plaus), key=LABELS.index)
    return verdict


_TRANSIENT = ("ratelimit", "timeout", "connection", "apiconnection",
              "internalserver", "serviceunavailable", "overloaded",
              "apistatus", "remoteprotocol", "readtimeout")


def _is_transient(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    if any(t in name for t in _TRANSIENT):
        return True
    msg = str(exc).lower()
    return any(s in msg for s in ("rate limit", "429", "500", "502", "503",
                                  "504", "overloaded", "timed out"))


def run_request(spec: dict, sems: dict, cache: dict, use_cache: bool) -> dict:
    """One juror verdict, cached, with retries only on transient failures."""
    meta = {k: spec[k] for k in ("cid", "instance_id", "ordering", "provider",
                                 "model", "temperature", "repeat")}
    key = cache_key(spec)
    if use_cache and key in cache:
        return {**meta, **cache[key], "cached": True}

    caller = _CALLERS[spec["provider"]]
    sem = sems[spec["provider"]]
    last = {"error": "unknown"}
    for attempt in range(RETRIES):
        try:
            with sem:
                raw = caller(spec["model"], RUBRIC, spec["user"],
                             spec.get("temperature"))
            verdict = _validate(raw)
            cache_put(key, verdict)
            return {**meta, **verdict, "cached": False}
        except SchemaError as e:
            # Deterministic failure: the same prompt will fail the same way.
            # Record the payload so it can be diagnosed instead of retrying.
            last = {"error": "SchemaError", "detail": str(e)[:400]}
            break
        except Exception as e:                       # noqa: BLE001
            last = {"error": type(e).__name__, "detail": str(e)[:300]}
            if not _is_transient(e) or attempt == RETRIES - 1:
                break
            time.sleep((2 ** attempt) + random.uniform(0, 0.5))
    return {**meta, **last, "cached": False}


def preflight(providers: list[str]) -> None:
    problems = []
    for p in sorted(set(providers)):
        try:
            _client(p)
        except ModuleNotFoundError:
            pkg = {"anthropic": "anthropic", "openai": "openai",
                   "google": "google-genai"}.get(p, p)
            problems.append(f"  {p}: SDK not installed - run: pip install {pkg}")
        except Exception as e:
            problems.append(f"  {p}: {type(e).__name__}: {str(e)[:160]}")
    if problems:
        sys.exit("cannot start jury; fix these jurors (or drop them with "
                 "--jurors):\n" + "\n".join(problems))


def run_jury(specs: list[dict], use_cache: bool) -> dict:
    cache = load_cache() if use_cache else {}
    if cache:
        print(f"  cache: {len(cache)} verdict(s) on disk")
    sems = {p: threading.Semaphore(n) for p, n in PROVIDER_CONCURRENCY.items()}
    workers = sum(PROVIDER_CONCURRENCY.get(p, 4)
                  for p in {s["provider"] for s in specs})
    raw, done, hits = {}, 0, 0
    total = len(specs)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = [ex.submit(run_request, s, sems, cache, use_cache) for s in specs]
        for fut in as_completed(futs):
            res = fut.result()
            raw[res["cid"]] = res
            done += 1
            hits += bool(res.get("cached"))
            if done % 25 == 0 or done == total:
                errs = sum(1 for r in raw.values() if "alignment" not in r)
                print(f"  {done}/{total} verdicts ({hits} cached, {errs} failed)")
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(RAW_FILE, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, indent=2, ensure_ascii=False)
    return raw


# --------------------------------------------------------------------------- #
# aggregation
# --------------------------------------------------------------------------- #

def strict_majority(labels: list[str]):
    """Label held by MORE THAN HALF of the votes, else None.

    Deliberately no tie-break. Breaking ties toward any label puts a directional
    prior on the study's dependent variable; abstaining routes the instance to a
    human instead [Jung2025].
    """
    if not labels:
        return None
    counts = Counter(labels)
    lab, n = counts.most_common(1)[0]
    return lab if n * 2 > len(labels) else None


def vote_entropy(counts: dict) -> float:
    """Normalized Shannon entropy of the vote distribution (0 = unanimous)."""
    total = sum(counts.values())
    if total <= 0:
        return 1.0
    h = -sum((c / total) * math.log(c / total) for c in counts.values() if c)
    return h / math.log(len(LABELS))


def aggregate(raw: dict, manifest: dict, malformed: dict) -> dict:
    per_instance = defaultdict(list)
    for cid, meta in manifest.items():
        verdict = raw.get(cid, {"error": "missing"})
        per_instance[meta["instance_id"]].append({**meta, **verdict})

    results = {}
    for iid, reason in malformed.items():
        results[iid] = {"final_binary": None, "final_alignment": None,
                        "status": "malformed", "flagged": True,
                        "flag_reason": reason, "label_counts": {},
                        "binary_label_counts": {}, "votes": []}

    for iid, votes in per_instance.items():
        good = [v for v in votes if v.get("alignment") in LABEL_SET]
        if not good:
            results[iid] = {"final_binary": None, "final_alignment": None,
                            "status": "no_verdicts", "flagged": True,
                            "flag_reason": "no valid verdicts", "label_counts": {},
                            "binary_label_counts": {}, "votes": votes}
            continue

        # ---- level 1: each juror's own label, over its orderings x repeats ----
        # Aggregating per juror first means a juror whose calls failed abstains
        # cleanly instead of silently reweighting the panel toward the survivors.
        by_juror = defaultdict(list)
        for v in good:
            by_juror[f"{v['provider']}:{v['model']}"].append(v)

        juror_labels, juror_flip, juror_selfcons = {}, {}, {}
        juror_binary, juror_binary_flip = {}, {}
        for jk, vs in by_juror.items():
            juror_labels[jk] = strict_majority([v["alignment"] for v in vs])
            juror_binary[jk] = strict_majority([BINARY_OF[v["alignment"]] for v in vs])
            per_order, per_order_bin = {}, {}
            for o in (0, 1):
                labs = [v["alignment"] for v in vs if v["ordering"] == o]
                per_order[o] = strict_majority(labs) if labs else None
                blabs = [BINARY_OF[v["alignment"]] for v in vs if v["ordering"] == o]
                per_order_bin[o] = strict_majority(blabs) if blabs else None
            juror_flip[jk] = (per_order[0] is not None and per_order[1] is not None
                              and per_order[0] != per_order[1])
            juror_binary_flip[jk] = (per_order_bin[0] is not None
                                     and per_order_bin[1] is not None
                                     and per_order_bin[0] != per_order_bin[1])
            # agreement of this juror with itself across repeats within an ordering
            reps = [len(set(v["alignment"] for v in vs if v["ordering"] == o)) == 1
                    for o in (0, 1)
                    if sum(1 for v in vs if v["ordering"] == o) > 1]
            juror_selfcons[jk] = (all(reps) if reps else None)

        # ---- level 2: panel labels ------------------------------------------
        # PRIMARY: binary consistent/conflicting (order-invariant).
        voting_bin = [l for l in juror_binary.values() if l is not None]
        final_binary = strict_majority(voting_bin)
        abstained_bin = [k for k, v in juror_binary.items() if v is None]
        # DIAGNOSTIC: 4-way (order-sensitive).
        voting = [l for l in juror_labels.values() if l is not None]
        final = strict_majority(voting)
        abstained_jurors = [k for k, v in juror_labels.items() if v is None]

        # ---- diagnostics -------------------------------------------------------
        # binary (PRIMARY) order/model disagreement
        bin_order = {}
        for o in (0, 1):
            blabs = [BINARY_OF[v["alignment"]] for v in good if v["ordering"] == o]
            bin_order[o] = strict_majority(blabs) if blabs else None
        binary_order_disagreement = (bin_order[0] is not None and bin_order[1] is not None
                                     and bin_order[0] != bin_order[1])
        binary_model_labels = {v["provider"]: juror_binary.get(f"{v['provider']}:{v['model']}")
                               for v in good}
        binary_model_disagreement = len({l for l in binary_model_labels.values()
                                         if l is not None}) > 1
        binary_counts = dict(Counter(BINARY_OF[v["alignment"]] for v in good))

        # 4-way (DIAGNOSTIC) order/model disagreement
        order_labels = {}
        for o in (0, 1):
            labs = [v["alignment"] for v in good if v["ordering"] == o]
            order_labels[o] = strict_majority(labs) if labs else None
        order_disagreement = (order_labels[0] is not None
                              and order_labels[1] is not None
                              and order_labels[0] != order_labels[1])

        model_labels = {v["provider"]: juror_labels.get(f"{v['provider']}:{v['model']}")
                        for v in good}
        model_disagreement = len({l for l in model_labels.values()
                                  if l is not None}) > 1

        counts = dict(Counter(v["alignment"] for v in good))
        entropy = vote_entropy(counts)

        # Response sets [Guerdan2025]. A plain union over every verdict flags
        # almost everything once there are many verdicts, so the operative
        # measure is the MAJORITY set: labels that more than half of the jurors'
        # verdicts called defensible. The union is retained for reference.
        sets = [set(v.get("plausible_alignments") or []) & LABEL_SET
                for v in good]
        sets = [s for s in sets if s]
        set_counts = Counter(l for s in sets for l in s)
        rs_majority = sorted(
            [l for l, c in set_counts.items() if c * 2 > len(sets)],
            key=LABELS.index) if sets else []
        rs_union = sorted(set_counts, key=LABELS.index)
        mean_set_size = (sum(len(s) for s in sets) / len(sets)) if sets else 0.0
        # keep the historical key name for downstream consumers
        response_set = rs_majority or ([final] if final else rs_union)

        # Flags are driven by the PRIMARY (binary) code: aligned<->partial flips
        # no longer flag an instance, since they don't change consistent/conflicting.
        reasons = []
        if final_binary is None:
            reasons.append("no panel majority on consistent/conflicting (abstained)")
        if binary_model_disagreement:
            reasons.append("cross-model disagreement (binary)")
        if binary_order_disagreement:
            reasons.append("order-swap disagreement (binary)")
        if abstained_bin:
            reasons.append(f"{len(abstained_bin)} juror(s) abstained (binary)")
        if len(good) < len(votes):
            reasons.append(f"{len(votes) - len(good)} verdict(s) failed")
        # 4-way diagnostics recorded but not primary flags
        diag = []
        if final is None:
            diag.append("4-way abstained")
        if order_disagreement:
            diag.append("4-way order-swap flip")
        if model_disagreement:
            diag.append("4-way cross-model")
        if len(rs_majority) > 1:
            diag.append(f"indeterminate ({'/'.join(rs_majority)})")

        results[iid] = {
            # ---- PRIMARY: binary consistent/conflicting ----
            "final_binary": final_binary,
            "status": "coded" if final_binary else "abstained",
            "binary_label_counts": binary_counts,
            "juror_binary": juror_binary,
            "juror_binary_flip": juror_binary_flip,
            "binary_order_disagreement": binary_order_disagreement,
            "binary_model_disagreement": binary_model_disagreement,
            "abstained_jurors_binary": abstained_bin,
            # ---- DIAGNOSTIC: 4-way (order-sensitive) ----
            "final_alignment": final,
            "status_4way": "coded" if final else "abstained",
            "diag_4way": "; ".join(diag),
            "juror_labels": juror_labels,
            "juror_order_flip": juror_flip,
            "juror_self_consistent": juror_selfcons,
            "abstained_jurors": abstained_jurors,
            "order0_label": order_labels[0],
            "order1_label": order_labels[1],
            "order_disagreement": order_disagreement,
            "model_labels": model_labels,
            "model_disagreement": model_disagreement,
            "label_counts": counts,
            "vote_entropy": entropy,
            "response_set": response_set,
            "response_set_majority": rs_majority,
            "response_set_union": rs_union,
            "mean_response_set_size": mean_set_size,
            "confidence_counts": dict(Counter(v.get("confidence") for v in good)),
            "flagged": bool(reasons),
            "flag_reason": "; ".join(reasons),
            "votes": votes,
        }
    return results


# --------------------------------------------------------------------------- #
# reliability: Krippendorff's alpha (nominal), pure stdlib
# --------------------------------------------------------------------------- #

def krippendorff_alpha(units: list[dict], labels: list[str] = None) -> float:
    """Nominal alpha over {coder: label} dicts, one per unit.

    `labels` is the category set (defaults to the 4-way LABELS; pass
    BINARY_LABELS for the primary consistent/conflicting alpha).  Units with
    fewer than two labels contribute nothing.  Read against Krippendorff's
    thresholds: < 0.667 discard, 0.667-0.8 tentative, >= 0.8 reliable [Baltes2026].
    """
    labels = labels or LABELS
    label_set = set(labels)
    coincid = defaultdict(float)
    for u in units:
        vals = [v for v in u.values() if v in label_set]
        m = len(vals)
        if m < 2:
            continue
        c = Counter(vals)
        for a in c:
            for b in c:
                pairs = c[a] * (c[a] - 1) if a == b else c[a] * c[b]
                coincid[(a, b)] += pairs / (m - 1)
    n_c = {lab: sum(coincid[(lab, k)] for k in labels) for lab in labels}
    n = sum(n_c.values())
    if n < 2:
        return float("nan")
    d_o = sum(coincid[(a, b)] for a in labels for b in labels if a != b)
    d_e = sum(n_c[a] * n_c[b] for a in labels for b in labels if a != b) / (n - 1)
    if d_e == 0:
        return float("nan")
    return 1.0 - d_o / d_e


def reliability(results: dict) -> dict:
    units = [r["juror_labels"] for r in results.values() if r.get("juror_labels")]
    units_bin = [r["juror_binary"] for r in results.values() if r.get("juror_binary")]
    alpha = krippendorff_alpha(units)                          # 4-way (diagnostic)
    alpha_bin = krippendorff_alpha(units_bin, BINARY_LABELS)   # binary (PRIMARY)
    jurors = sorted({k for u in units for k in u})

    pairwise = {}
    for i, a in enumerate(jurors):
        for b in jurors[i + 1:]:
            both = [(u[a], u[b]) for u in units
                    if u.get(a) in LABEL_SET and u.get(b) in LABEL_SET]
            if both:
                pairwise[f"{a} vs {b}"] = {
                    "n": len(both),
                    "raw_agreement": sum(x == y for x, y in both) / len(both),
                    "alpha": krippendorff_alpha([{"a": x, "b": y} for x, y in both]),
                }

    # primary flip/coverage use the BINARY per-juror labels; 4-way flip kept too
    flips, flips_4way, coverage, selfcons = {}, {}, {}, {}
    for jk in jurors:
        fb = [r["juror_binary_flip"].get(jk) for r in results.values()
              if r.get("juror_binary_flip") and jk in r["juror_binary_flip"]]
        flips[jk] = (sum(1 for f in fb if f) / len(fb)) if fb else None
        f4 = [r["juror_order_flip"].get(jk) for r in results.values()
              if r.get("juror_order_flip") and jk in r["juror_order_flip"]]
        flips_4way[jk] = (sum(1 for f in f4 if f) / len(f4)) if f4 else None
        cov = [r["juror_binary"].get(jk) for r in results.values()
               if r.get("juror_binary")]
        coverage[jk] = (sum(1 for c in cov if c in set(BINARY_LABELS)) / len(cov)
                        if cov else 0.0)
        sc = [r["juror_self_consistent"].get(jk) for r in results.values()
              if r.get("juror_self_consistent")
              and r["juror_self_consistent"].get(jk) is not None]
        selfcons[jk] = (sum(1 for s in sc if s) / len(sc)) if sc else None

    return {"krippendorff_alpha_binary": alpha_bin,
            "krippendorff_alpha_nominal": alpha, "n_units": len(units),
            "jurors": jurors, "pairwise": pairwise,
            "order_flip_rate": flips, "order_flip_rate_4way": flips_4way,
            "juror_coverage": coverage, "juror_self_consistency": selfcons}


def alpha_band(a: float) -> str:
    if a != a:
        return "undefined"
    if a >= 0.8:
        return "reliable (Krippendorff >= 0.8)"
    if a >= 0.667:
        return "tentative only (0.667 <= alpha < 0.8)"
    return "below Krippendorff's floor (< 0.667)"


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #

def write_reports(results: dict, jurors: list[dict], repeats: int) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(REPORT_OUT + ".json", "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)

    rel = reliability(results)
    dist_bin = Counter(r.get("final_binary") for r in results.values())   # PRIMARY
    dist4 = Counter(r["final_alignment"] for r in results.values())       # diagnostic
    status = Counter(r.get("status") for r in results.values())
    flagged = {i: r for i, r in results.items() if r["flagged"]}
    coded = sum(1 for r in results.values() if r.get("final_binary") in set(BINARY_LABELS))
    coded4 = sum(1 for r in results.values() if r["final_alignment"] in LABEL_SET)
    n = len(results)
    jury_str = ", ".join(f"{j['provider']}:{j['model']}"
                         f"(T={j.get('temperature')})" for j in jurors)
    ab, a4 = rel["krippendorff_alpha_binary"], rel["krippendorff_alpha_nominal"]

    L = ["# Reasoning-alignment report", "",
         f"- Instances: **{n}**  |  coded (binary): **{coded}**  |  "
         f"coverage: **{coded / n:.1%}**" if n else "- Instances: 0", "",
         f"- Jury: {jury_str}",
         f"- Repeats per (juror x ordering): {repeats}",
         f"- Rubric hash: `{RUBRIC_HASH}`",
         f"- Generated: {datetime.datetime.now().isoformat(timespec='seconds')}",
         "",
         "PRIMARY code = binary **consistent** (aligned+partial) vs **conflicting**",
         "(divergent+contradictory). The 4-way split is an order-sensitive",
         "diagnostic (see below). Panel label = strict majority over jurors; each",
         "juror = strict majority over its orderings x repeats; ties ABSTAIN.",
         "", "## Primary: consistent vs conflicting", ""]
    for lab in BINARY_LABELS:
        if dist_bin.get(lab):
            L.append(f"- {lab}: **{dist_bin[lab]}** ({dist_bin[lab] / n:.1%})")
    for st, c in sorted(status.items()):
        if st != "coded":
            L.append(f"- _{st}_: **{c}**")
    L += ["",
          f"- Model-model Krippendorff's alpha (binary): "
          f"**{ab:.3f}** — {alpha_band(ab)}" if ab == ab else
          "- Model-model Krippendorff's alpha (binary): undefined",
          "- consistent = aligned+partial; conflicting = divergent+contradictory."]

    L += ["", "## Diagnostic: 4-way split (ORDER-SENSITIVE, do not report alone)", "",
          f"coded (4-way): **{coded4}** ({coded4 / n:.1%})   "
          f"Krippendorff alpha (4-way): "
          + (f"**{a4:.3f}** — {alpha_band(a4)}" if a4 == a4 else "undefined"), ""]
    for lab in LABELS:
        if dist4.get(lab):
            L.append(f"- {lab}: **{dist4[lab]}** ({dist4[lab] / n:.1%})")
    L += ["",
          "The aligned<->partial boundary is directional and position-sensitive;",
          "its flips do not change the binary code and are excluded from the",
          "primary result.", "", "### Label legend", ""]
    L += [f"- **{lab}** — {LABEL_DESC[lab]}" for lab in LABELS]

    L += ["", "## Per juror", "",
          "| juror | coverage | order-flip (binary) | order-flip (4-way) | self-consistency |",
          "|---|---|---|---|---|"]
    for jk in rel["jurors"]:
        fb = rel["order_flip_rate"].get(jk)
        f4 = rel["order_flip_rate_4way"].get(jk)
        s = rel["juror_self_consistency"].get(jk)
        L.append(f"| {jk} | {rel['juror_coverage'].get(jk, 0):.1%} | "
                 f"{f'{fb:.1%}' if fb is not None else '-'} | "
                 f"{f'{f4:.1%}' if f4 is not None else '-'} | "
                 f"{f'{s:.1%}' if s is not None else 'n/a (repeats=1)'} |")
    if rel["pairwise"]:
        L += ["", "### Pairwise juror agreement (4-way)", "",
              "| pair | n | raw | alpha |", "|---|---|---|---|"]
        for k, v in rel["pairwise"].items():
            av = v["alpha"]
            L.append(f"| {k} | {v['n']} | {v['raw_agreement']:.1%} | "
                     f"{av:.3f} |" if av == av else
                     f"| {k} | {v['n']} | {v['raw_agreement']:.1%} | undef |")
        L += ["", "High pairwise agreement across families is necessary but not",
              "sufficient: it can reflect shared bias rather than validity. Run",
              "judge_validation.py against the human gold codes [Ahmed2025]."]

    L += ["", f"## Flagged for manual adjudication ({len(flagged)})", "",
          "Binary panel abstentions, binary cross-model/order-swap disagreement,",
          "or failed calls. (4-way-only disagreements are noted, not flagged.)", ""]
    for iid, r in sorted(flagged.items(),
                         key=lambda kv: -kv[1].get("vote_entropy", 0)):
        L.append(f"### {iid}")
        L.append(f"- binary: **{r.get('final_binary')}** ({r.get('flag_reason')})")
        if r.get("juror_binary"):
            L.append(f"- per juror (binary): {r['juror_binary']}")
            L.append(f"- 4-way: final={r.get('final_alignment')} "
                     f"per juror={r.get('juror_labels')}  {r.get('diag_4way', '')}")
            L.append(f"- counts: {r.get('label_counts')}  "
                     f"entropy={r.get('vote_entropy', 0):.2f}")
        L.append("")
    with open(REPORT_OUT + ".md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")

    print(f"\ninstances: {n}  coded (binary): {coded} ({coded / n:.1%} coverage)"
          if n else "no instances")
    for lab in BINARY_LABELS:
        if dist_bin.get(lab):
            print(f"  {lab}: {dist_bin[lab]}")
    for st, c in sorted(status.items()):
        if st != "coded":
            print(f"  [{st}]: {c}")
    print(f"binary alpha: {ab:.3f} ({alpha_band(ab)})" if ab == ab
          else "binary alpha: undefined")
    print(f"  [diagnostic] 4-way coded {coded4}, 4-way alpha "
          + (f"{a4:.3f}" if a4 == a4 else "undefined"))
    print(f"flagged: {len(flagged)}")
    print(f"report: {REPORT_OUT}.json / {REPORT_OUT}.md")
    print("next: python judge_validation.py")


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def cost_estimate(n_instances: int, jurors: list[dict], repeats: int) -> None:
    per_in, per_out = 900, 500
    calls = n_instances * 2 * repeats
    print(f"  {len(jurors)} juror(s) x {calls} calls each "
          f"= {len(jurors) * calls} requests "
          f"({n_instances} instances x 2 orderings x {repeats} repeat(s))")
    approx = len(jurors) * calls * (per_in / 1e6 * 5.0 + per_out / 1e6 * 25.0)
    print(f"  rough order-of-magnitude cost: ${approx:.2f} "
          "(Opus-tier stand-in pricing; caching and cheaper jurors lower it)")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true",
                   help="build requests, print count/cost, write manifest; no API")
    p.add_argument("--run", action="store_true", help="run the jury, write reports")
    p.add_argument("--limit", type=int, default=None,
                   help="only the first N agreed instances (smoke test)")
    p.add_argument("--jurors", default=None,
                   help="comma-separated provider subset (default: all)")
    p.add_argument("--repeats", type=int, default=1,
                   help="samples per (juror x ordering) for self-consistency")
    p.add_argument("--temperature", type=float, default=None,
                   help="override every juror's temperature")
    p.add_argument("--no-cache", action="store_true",
                   help="ignore cached verdicts and re-call the API")
    p.add_argument("--mock", type=int, default=0, metavar="N",
                   help="replace the jury with N offline mock jurors "
                        "(for testing the pipeline without API calls)")
    args = p.parse_args(argv)

    jurors = [dict(j) for j in JURORS]
    if args.mock:
        jurors = [{"provider": "mock", "model": f"mock-{i}", "temperature": 0.0}
                  for i in range(args.mock)]
    elif args.jurors:
        want = {s.strip() for s in args.jurors.split(",") if s.strip()}
        jurors = [j for j in jurors if j["provider"] in want]
        if not jurors:
            sys.exit(f"no jurors match {sorted(want)}; "
                     f"available: {[j['provider'] for j in JURORS]}")
    if args.temperature is not None:
        for j in jurors:
            j["temperature"] = args.temperature

    all_ids = agreed_instance_ids()
    if args.limit:
        all_ids = all_ids[:args.limit]
    iids, malformed = partition_instances(all_ids)

    if malformed:
        print(f"note: {len(malformed)} instance(s) excluded as malformed "
              "(missing/near-empty reasoning); they appear in the report with "
              "status=malformed, not as a code")
        for i, why in sorted(malformed.items())[:5]:
            print(f"    {i}: {why}")

    specs, manifest = build_requests(iids, jurors, args.repeats)
    print(f"agreed: {len(all_ids)}  codeable: {len(iids)}  ->  "
          f"{len(specs)} jury requests")
    cost_estimate(len(iids), jurors, args.repeats)

    config = {"jurors": jurors, "repeats": args.repeats,
              "rubric_hash": RUBRIC_HASH, "labels": LABELS,
              "max_tokens": MAX_TOKENS, "effort": EFFORT,
              "n_agreed": len(all_ids), "n_codeable": len(iids),
              "malformed": malformed,
              "run_started": datetime.datetime.now().isoformat(timespec="seconds")}

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(MANIFEST_FILE, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)

    if args.dry_run:
        print(f"dry run - manifest -> {MANIFEST_FILE}, config -> {CONFIG_FILE}")
        return 0
    if not args.run:
        p.error("choose --dry-run or --run")

    preflight([j["provider"] for j in jurors])
    raw = run_jury(specs, use_cache=not args.no_cache)
    write_reports(aggregate(raw, manifest, malformed), jurors, args.repeats)
    return 0


if __name__ == "__main__":
    sys.exit(main())