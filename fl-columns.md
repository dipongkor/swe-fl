# `fl-summary.csv` column definitions

Produced by `fl_eval.py`. One block of rows per model: three per-run rows
(`run1`/`run2`/`run3`) followed by four aggregate rows (`mean`, `any@3`,
`majority@3`, `all@3`).

All `*_rate` columns and `precision`/`recall`/`f1` are **fractions in [0, 1]**
(3 decimals). Hit columns (`file_hit`, `line_hit`, …) are **instance counts**.

## What "a hit" means (matching rules)

A prediction's `root_cause` locations are matched against the ground-truth
`root_cause` locations. An instance counts as a hit at a granularity if **any**
predicted location matches **any** GT location:

- **file** — predicted file path == GT file path.
- **line** — same file **and** the predicted line lies inside the GT statement's
  logical span, **or** the GT line lies inside the predicted statement's span,
  **or** the two line numbers are equal. This encodes the annotation unit "the
  statement containing the line," so a model citing a different physical line of
  the same multi-line statement still counts.
- **exact line** — same file and predicted line **==** GT line (no span
  tolerance). Strict subset of a line hit.
- **statement** — predicted statement text equals a GT statement text after
  normalizing whitespace, quotes, and commas.

## Row types

| Row | Meaning |
| --- | --- |
| `run1`/`run2`/`run3` | a single agent run |
| `mean` | arithmetic mean of the three per-run values |
| `any@3` | consensus with threshold **k = 1** (hit in ≥1 run) |
| `majority@3` | consensus with threshold **k = 2** (hit in ≥2 runs) |
| `all@3` | consensus with threshold **k = 3** (hit in all runs) |

## Columns

| Column | Type | Definition |
| --- | --- | --- |
| `model` | str | Model name. |
| `run` | str | Row type (see above). |
| `total` | int | Instances scored against ground truth (**130**). The denominator for every `*_rate` except `line_rate_eval`. |
| `evaluated` | int | Per-run: instances where the model emitted a parseable localization. Aggregate rows: "answered" = instances localized in ≥1 run. `mean`: `-`. |
| `file_hit` | int | Instances with a file-level hit. Per-run: this run. Aggregate: hit in ≥k runs. |
| `line_hit` | int | Instances with a line-level hit (span rule). **Primary FL metric.** Per-run vs ≥k-run consensus as above. |
| `exact_line_hit` | int | Instances with an exact-line hit. **Per-run only**; aggregate rows show `-`. |
| `stmt_hit` | int | Instances with a statement-text hit. |
| `file_rate` | frac | `file_hit / total`. |
| `line_rate` | frac | `line_hit / total`. Missing/unparseable localization counts as a miss. |
| `line_rate_eval` | frac | `line_hit / evaluated`. Per-run: over localization-present instances. Aggregate: over "answered". `mean`: mean of the three per-run eval-rates. Isolates quality-when-answered from coverage. |
| `stmt_rate` | frac | `stmt_hit / total`. |
| `precision` | frac | Micro-averaged, line granularity. Per-run: `matched predicted locations / all predicted locations`. Aggregate: `correct consensus locations / (correct + spurious) consensus locations`, where a location survives if predicted in ≥k runs. |
| `recall` | frac | Micro-averaged, line granularity. Per-run: `matched GT locations / all GT locations`. Aggregate: `GT locations matched in ≥k runs / all GT locations`. |
| `f1` | frac | Harmonic mean of `precision` and `recall`. |
| `resolved` | int | Instances whose generated patch passed the SWE-bench evaluation (`report.json` `resolved == true`). Per-run vs ≥k-run consensus as above. |
| `resolved_rate` | frac | `resolved / total`. SWE-bench patch-fix success rate (independent of localization). |

## Notes

- **Two denominators.** `line_rate` (of 130) is the fair cross-model number;
  `line_rate_eval` (of answered) is the diagnostic. A model that stays silent on
  many instances shows a low `line_rate` but can show a high `line_rate_eval`.
- **P/R/F1 are micro-averaged** (pooled counts, not per-instance means) — the
  FL/IR standard. It gives the expected consensus tradeoff: `any@3` → high
  recall / low precision; `all@3` → low recall / high precision.
- `precision`/`recall`/`f1` are computed at **line** granularity only.
- `hit` metrics answer "did the model find the fault"; `precision`/`recall`
  additionally penalize naming **extra** wrong locations. `resolved*` is a
  separate, patch-level signal and does not depend on the localization fields.
