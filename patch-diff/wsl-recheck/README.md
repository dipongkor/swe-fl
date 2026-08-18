# wsl-recheck — re-verify all 214 fl_wrong_resolved patches (Windows + WSL2)

Self-contained. Confirms every one of the 214 `fl_wrong_resolved` agent patches (and the 64
gold patches) resolves under the standard SWE-bench Verified harness on a native x86_64 host.
No emulation: the prebuilt `swebench/sweb.eval.x86_64.*` images pull directly.

Scope: 214 agent cells across 64 instances / 8 repos (astropy, django, matplotlib, pydata,
pytest-dev, scikit-learn, sphinx-doc, sympy). 12 agent prediction files + 1 gold file.

## Prerequisites (inside WSL2 Ubuntu)
- Docker Desktop for Windows with **WSL2 integration enabled** (Settings → Resources → WSL
  integration → enable your distro). Verify: `docker run --rm hello-world`.
- Python 3.10+ and: `pip install swebench datasets`
- Internet (pulls images + the HF dataset metadata).

## Disk footprint (optimized)
`--cache_level env` makes the harness **delete each ~2-4 GB instance image the moment that
instance finishes** (per-instance, in `run_instance`'s `finally`). Images do **not**
accumulate, so peak disk is bounded by concurrent workers, not by the 64 instances:

| workers | approx peak disk |
|--------:|------------------|
|   2     | ~10 GB           |
|   4     | ~15-20 GB        |
|   8     | ~30 GB           |

So **~20 GB free is plenty** at the default 4 workers. Workers control both speed and peak disk.

Repo-wise (64 instances): django 24 · scikit-learn 9 · pytest-dev 8 · sphinx-doc 8 · sympy 7
· matplotlib 4 · astropy 2 · pydata 2.

## Run — pick one
```bash
cd wsl-recheck

# A) straight through (recommended). Prunes dangling layers + prints disk between files.
bash run_all.sh                 # run_id=recheck, 4 workers
bash run_all.sh recheck 3       # fewer workers -> lower peak disk

# B) repo-at-a-time with a HARD cleanup (removes all sweb.* images) between repos.
#    Use if disk is tight or you want per-repo checkpoints. Smallest repo first.
bash run_by_repo.sh             # calls summarize.py at the end

python3 summarize.py            # -> recheck-summary.csv + tally  (A only; B runs it for you)
```
Both modes are resumable: re-running skips already-completed instances.

## Share back
- The tally printed by `summarize.py`, and
- `recheck-summary.csv` (one row per cell: model_name, instance_id, resolved).
If anything is non-resolved, `summarize.py` lists those cells explicitly — send those.

## Notes
- Files run sequentially, so an instance shared across model-runs never collides on a
  container name. Instances are unique within a file, so `--max_workers` is safe.
- If a run is interrupted, just re-run `bash run_all.sh` — completed instances are skipped.
- To also keep the fast instance images (more disk, faster re-runs): edit `run_all.sh`,
  set `--cache_level instance`.
- Expected outcome: agent 214/214 resolved, gold 64/64 resolved. Any deviation is the
  interesting signal — that would be a patch our original eval marked resolved but this
  re-run does not.
