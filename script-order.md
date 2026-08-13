# Merge
merge_from_csv.py
extract_statements.py

# Reasoning-judge pipeline — script run order

Three scripts, two independent inputs that both feed the validator last.

```
reasoning_alignment.csv          merge_report.json
   (human labels)                 (agreed set)
        │                          │        │
        ▼                          ▼        ▼
make_validation_sheet.py     reasoning_judge.py --run
        │                          │
        ▼                          ▼
  validation_sheet.csv    reasoning_alignment_report.json
        │                          │
        └──────────┬───────────────┘
                   ▼
          judge_validation.py   →  Cohen's κ, confusion matrix, per-class P/R
```

## Order

1. **`reasoning_judge.py --dry-run`** *(optional)* — builds requests, prints count +
   cost estimate, writes `manifest.json`. No API calls. Run this to sanity-check
   before spending tokens.
2. **`reasoning_judge.py --run`** — runs the jury (3 jurors × 2 orderings) over the
   agreed instances, writes `reasoning_alignment_report.json` (+ `.md`,
   `raw_results.json`).
3. **`make_validation_sheet.py`** — joins `reasoning_alignment.csv` (human labels)
   with each annotator's reasoning → `validation_sheet.csv`. **Independent of the
   judge** — can run before, after, or in parallel with steps 1–2.
4. **`judge_validation.py`** — needs *both* the report (step 2) and the sheet
   (step 3); compares them → κ + confusion matrix + per-class precision/recall.

## The only hard constraint

`judge_validation.py` runs **last** — it reads both
`reasoning_alignment_report.json` and `validation_sheet.csv`. Steps 2 and 3 have no
dependency on each other, so their order is free; everything else just has to
precede step 4.

## Inputs and outputs

| Script | Reads | Writes |
| --- | --- | --- |
| `reasoning_judge.py` | agreed set (`merge_report.json`), annotator reasoning | `reasoning_alignment_report.json`, `.md`, `raw_results.json`, `manifest.json` |
| `make_validation_sheet.py` | `reasoning_alignment.csv`, `merge_report.json`, annotator reasoning | `validation/validation_sheet.csv`, `validation/validation_key.json` |
| `judge_validation.py` | `validation_sheet.csv`, `reasoning_alignment_report.json` | stdout (κ, matrix, per-class P/R) |

## When to re-run

- Re-run **`reasoning_judge.py --run`** only when jurors, prompts, or the agreed set
  change — then re-run **`judge_validation.py`** to refresh κ against the same human
  labels.
- Re-run **`make_validation_sheet.py`** when `reasoning_alignment.csv` (human labels)
  changes — then re-run **`judge_validation.py`**.
