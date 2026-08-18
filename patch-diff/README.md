# patch-diff — differential / strengthened testing of the 23 conflicting cells

Purpose: check whether the 23 resolved-but-mislocalized, conflicting-rationale patches are
genuinely correct (survive strengthened testing) or overfit to a weak SWE-bench suite, and
demonstrate the sphinx-9658 specimen concretely. Answers the reviewer objection
*"fix-without-localizing is just the known overfitting problem."*

## Inputs
- `preds/agent__<model>-<run>.jsonl` — agent patches, grouped per model-run (unique instance
  ids per file); `preds/gold.jsonl` — the 10 gold patches. SWE-bench harness format.
- `images.txt` — the 10 x86_64 eval-image names.

## Host note (Apple Silicon)
SWE-bench prebuilt images are x86_64-only; run under emulation. The docker-py SDK's `pull()`
ignores `DOCKER_DEFAULT_PLATFORM`, so images must be pre-pulled with
`docker pull --platform linux/amd64` (done by `run_baseline.sh`).

## Steps
1. `bash run_baseline.sh` — pre-pull images, run all 23 agent + 10 gold through the STANDARD
   harness. Confirms every cell resolves (validates our accuracy labels) and caches images.
   Reports land in `reports/`.
2. `python strengthen_diff.py` — for each instance, run the WHOLE test file(s) touched by
   gold's `test_patch` on the gold-patched vs agent-patched repo and diff pass/fail. A test
   passing under gold but not agent = a strengthened-test divergence. -> `strengthen-results.json`.
3. `python ingest_results.py` — fold resolved + strengthened verdicts into
   `../fix-without-understanding-audit.csv` (adds `resolved_recheck`, `strengthen_verdict`).

## Results so far
- `specimen_sphinx-9658.md` — the specimen differential (executed). Both patches resolve;
  on Python 3.9 the agent patch is behaviourally equivalent to gold on every reachable render,
  but leaves the mock's identity corrupted (`__qualname__ == ''` vs gold's `'Class'`): it masks
  one renderer instead of repairing the source.
- UTBoost cross-check: all 10 instances are in `Bertsekas/SWE-Bench_Verified_UTBoost`, but
  NONE was strengthened by UTBoost (identical FAIL_TO_PASS / PASS_TO_PASS / test_patch to base)
  -> our conflicting cells are not among the weak-test instances UTBoost targets.
