# SWE-FL — Trustworthiness Benchmark Pipeline

Evaluates LLM trustworthiness on buggy SWE-bench-Verified instances across four
axes:

1. **FL** — fault localization: does the model point at the faulty statement?
2. **APR** — automated program repair: does its patch pass the tests (`resolved`)?
3. **Reasoning** — does the model's explanation match the ground-truth mechanism?
4. **Robustness** — do FL/APR/reasoning survive semantics-preserving code
   transformations (SPTs)?

Ground truth is a two-annotator fault-localization study (Atish = annotator1,
Eshgin = annotator2) merged into `ground-truth-fl/`, with each root-cause
`statement` stored **verbatim** from the source at the instance's base commit.
The developer-written reference fixes (gold patches) are fetched separately into
`ground-truth-patches/`.

---

## 0. Prerequisites

```bash
pip install datasets anthropic openai google-genai      # jury + dataset access
export ANTHROPIC_API_KEY=...        # jury juror 1
export OPENAI_API_KEY=...           # jury juror 2
export GOOGLE_API_KEY=...           # jury juror 3
bash clone_repos.sh                 # clone the 11 repos into repos/ (needed for
                                    # statement extraction and FL line matching)
```

Repos, the HuggingFace `SWE-bench/SWE-bench_Verified` dataset (base commits +
human difficulty), and agent-run outputs under `agent-fl/swebench-fl-<model>-run<N>/`
are all expected to be present. Everything is pure Python + the three SDKs; the
statistics scripts need no numpy/scipy.

---

## Directory layout

| Path | What |
|---|---|
| `annotation/Atish_Annotation/`, `Eshgin_Annotation/` | raw per-annotator JSON |
| `annotation/merge_report.json` | which instances `agree` vs `conflict` |
| `ground-truth-fl/` | merged ground truth (one JSON per instance) |
| `ground-truth-fl.csv` | flattened GT (instance, base_commit, file, line, statement) |
| `ground-truth-patches/` | developer-written gold patch per instance (`<inst>.patch`), from SWE-bench Verified |
| `repos/` | cloned source repos (for statement/line matching) |
| `agent-fl/swebench-fl-<model>-run<N>/<inst>/` | agent outputs: `preds.json` (patch + `localization`) and eval `report.json` |
| `reasoning_eval/` | reasoning-jury working dir (cache/raw/manifest) |
| `annotation/reasoning_alignment/` | inter-annotator jury report + validation |
| `archive/` | superseded script versions |

---

## Stage A — Build the ground truth

```bash
# 1. Merge the two annotators + decision CSVs into ground-truth-fl/
python3 merge_from_csv.py            # reads agreed.csv, conflicts.csv

# 2. Rewrite each root_cause.statement to the VERBATIM source statement
#    containing its line (backs up changed files to <file>.bak)
python3 extract_statements.py --apply
python3 extract_statements.py        # verify-only: prints "N/N extracted", 0 flagged

# 3. Flatten to CSV (adds base_commit from SWE-bench Verified)
python3 ground_truth_to_csv.py       # -> ground-truth-fl.csv

# 4. Fetch developer-written gold patches (reference fixes) from SWE-bench Verified.
#    Independent of steps 1-3, but the default instance list is read from
#    ground-truth-fl/*.json, so run it after step 1.
python3 get_ground_truth_patches.py  # -> ground-truth-patches/<inst>.patch (130)
#   --instances FILE   explicit id list      --all   every Verified instance (500)
```

Helpers: `classify_statements.py` buckets statements good / safe-to-apply /
unsafe-to-apply; `merge.html` / `index.html` are browser UIs (served with
`python3 -m http.server`) for merging and viewing annotations.

---

## Stage B — Reasoning jury + validation (inter-annotator)

Judges, on **agreed** instances, whether the two annotators describe the same
fault *mechanism*, using a 3-model LLM jury (Anthropic + OpenAI + Google), each
juror judging both A/B orderings, majority vote, abstaining on ties.

```bash
# 1. Cost/plan preview (no API calls)
python3 reasoning_judge.py --dry-run

# 2. Smoke-test one juror before spending (verify model IDs / keys)
python3 reasoning_judge.py --jurors anthropic --limit 1 --run

# 3. Run the jury  (resumable: cached on disk, re-runs cost nothing)
python3 reasoning_judge.py --run                 # add --repeats 3 for self-consistency
#   -> annotation/reasoning_alignment/reasoning_alignment_report.json (+ .md)

# 4. Validate the jury against human gold labels
python3 make_validation_sheet.py                 # builds sheet from reasoning_alignment.csv
python3 judge_validation.py                       # Cohen's kappa + Gwet AC1 + PABAK,
                                                  # per-juror vs gold, coverage curve
```

Jurors are configured in `reasoning_judge.py` (`JURORS`). Temperature policy:
pin `0.0` where the API honours it (Gemini); use `None` where it's rejected
(Anthropic with thinking on; OpenAI reasoning models) — determinism comes from
`--repeats` + the panel, not temperature.

---

## Stage C — Evaluate models (FL + APR + reasoning)

Assumes agent runs exist under `agent-fl/` (4 models × 3 runs). Each
`preds.json` carries a `localization` field with the GT schema
(`root_cause:[{file,line,statement}]`, `reasoning`).

```bash
# FL accuracy (file / line / statement), micro P/R/F1, + resolved rate.
python3 fl_eval.py                    # -> fl-summary.csv, fl-matrix.csv,
                                      #    fl-counts.csv, fl-details.csv
python3 fl_eval.py --columns          # column definitions (see also fl-columns.md)

# FL x APR alignment, per (model,run,instance) cell.
python3 fl_apr_align.py               # -> fl-apr-align.csv (contingency + phi),
                                      #    fl-apr-cells.csv (per-cell)

# Reasoning vs ground-truth reasoning (LLM jury, reuses reasoning_judge).
python3 reasoning_eval.py --dry-run                    # prints cell count + cost
python3 reasoning_eval.py --condition line --limit 20 --run   # cheap pilot
python3 reasoning_eval.py --run                        # full -> reasoning-summary.csv,
                                                       #         reasoning-cells.csv
#   --condition {all,line,file}     which localized cells to judge (default all)
#   --gt-reference {single,both}    single annotator (default) vs best-of-both

# Join all three axes into one per-cell table + cross-axis stats.
python3 trust_axes.py                 # -> trust-cells.csv
```

`generate-result-summary.py` produces the standalone SWE-bench `resolved`
summary (per-run + any@3/majority@3/all@3) if you want APR alone.

---

## Stage D — Robustness (SPTs)

The 13 semantics-preserving transformation rules are in `spt-rules.md`
(comment removal, identifier renaming, branch/loop rewrites, dead-code removal,
function extraction, …). Because running all instances × 13 transforms × models
is too costly, sample a stratified panel first.

```bash
# 1. Draw a reproducible stratified panel from FL-correct behavioural groups
python3 select_robustness_sample.py   # -> robustness-sample.txt (instance list),
                                       #    robustness-sample.csv (with strata)
#   groups: 'both' (FL+ & resolved) and 'fl_only' (FL+ & unresolved), >=2 models;
#   stratified by repo x SWE-bench difficulty. Tune with --n-both/--n-fl-only.
```

2. **Transform** each panel instance with each of the 13 SPT rules, and run the
   agents on the transformed instances. Land each transform's outputs in its own
   dir, e.g. `agent-fl-<rule>/swebench-fl-<model>-run<N>/…`.

3. **Score each transform** (same tools, with `--tag` and `--agent-fl`):

```bash
# base (once):
python3 fl_apr_align.py   --tag base
python3 reasoning_eval.py --tag base --run
python3 trust_axes.py     --tag base           # -> trust-cells-base.csv

# per transform T:
python3 fl_apr_align.py   --agent-fl agent-fl-T --tag T
python3 reasoning_eval.py --agent-fl agent-fl-T --tag T --run
python3 trust_axes.py     --tag T              # -> trust-cells-T.csv
```

4. **Diff** base vs every transform, all axes at once:

```bash
python3 robustness_diff.py --base trust-cells-base.csv trust-cells-*.csv
#   -> robustness-diff.csv : per (transform, axis) break rate + exact McNemar p.
```

`break_rate = b/(a+b)` — of what the model got right on the base, how much the
transform broke. Watch **`full_trust` break_rate** and whether the
**fix-without-understanding** pattern (resolved but FL wrong / reasoning not
aligned) grows under transformation.

---

## End-to-end cheat sheet

```bash
# --- ground truth ---
python3 merge_from_csv.py && python3 extract_statements.py --apply && python3 ground_truth_to_csv.py
python3 get_ground_truth_patches.py   # gold patches -> ground-truth-patches/

# --- reasoning jury + validation ---
python3 reasoning_judge.py --run
python3 make_validation_sheet.py && python3 judge_validation.py

# --- model eval (FL / APR / reasoning / join) ---
python3 fl_eval.py
python3 fl_apr_align.py
python3 reasoning_eval.py --run
python3 trust_axes.py

# --- robustness ---
python3 select_robustness_sample.py
#   ... transform panel with the 13 SPT rules, run agents into agent-fl-<rule>/ ...
python3 trust_axes.py --tag base
# per transform: fl_apr_align.py / reasoning_eval.py / trust_axes.py with --tag
python3 robustness_diff.py --base trust-cells-base.csv trust-cells-*.csv
```

---

## Notes

- **Caching / resume.** Both jury scripts (`reasoning_judge.py`,
  `reasoning_eval.py`) cache every verdict on disk keyed by
  `(provider, model, rubric-hash, temperature, repeat, prompt)`. A killed run
  resumes for free; re-runs cost nothing. Use `--no-cache` to force re-calls.
- **Offline testing.** Both jury scripts accept `--mock N` to run N fake jurors
  with no API calls — validates the full pipeline (aggregation, entropy,
  reports) for free.
- **FL line matching** uses "the statement containing the line": a predicted
  line matches if it falls in the GT statement's logical span (or vice-versa),
  computed from `repos/` at the base commit. See `fl-columns.md`.
- **Reproducibility.** Sampling (`select_robustness_sample.py`) and validation
  (`judge_validation.py`) take `--seed`. Every metric script writes CSVs so
  numbers are traceable in the replication package.
- **Cost.** `reasoning_judge.py --dry-run` and `reasoning_eval.py --dry-run`
  print request counts and an order-of-magnitude cost before any spend.
