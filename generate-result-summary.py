import csv
import glob
import json
import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def discover_runs():
    """Find swebench-fl-<model>-run<N> dirs -> [(model, run, dirname)] sorted."""
    pairs = []
    for path in glob.glob(os.path.join(BASE_DIR, "swebench-fl-*-run*")):
        if not os.path.isdir(path):
            continue
        name = os.path.basename(path)
        m = re.match(r"swebench-fl-(.+)-run(\d+)$", name)
        if not m:
            continue
        pairs.append((m.group(1), int(m.group(2)), name))
    return sorted(pairs, key=lambda p: (p[0], p[1]))


def load_instances():
    """Read verified-buggy-instances.txt (one full_id per line) as short dir names."""
    path = os.path.join(BASE_DIR, "verified-buggy-instances.txt")
    instances = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            full_id = line.split()[-1]
            instances.append(full_id.split("__")[-1])
    return sorted(set(instances))


def collect_results(run_dir, instances):
    """Return {instance: resolved_bool_or_None} for one run directory.

    None means no report.json was found (evaluation missing/failed, or the
    instance directory itself is absent).
    """
    results = {}
    root = os.path.join(BASE_DIR, run_dir)
    for instance in instances:
        instance_dir = os.path.join(root, instance)
        if not os.path.isdir(instance_dir):
            results[instance] = None
            continue
        reports = glob.glob(
            os.path.join(instance_dir, "logs", "run_evaluation", "**", "report.json"),
            recursive=True,
        )
        if not reports:
            results[instance] = None
            continue
        with open(reports[0]) as f:
            report = json.load(f)
        # report.json is keyed by the full instance id, e.g. astropy__astropy-7606
        entry = next(iter(report.values()))
        results[instance] = bool(entry.get("resolved", False))
    return results


def get_exit_status(run_dir, instance):
    """Read the agent's exit status from the instance's .traj.json, if present."""
    if not os.path.isdir(os.path.join(BASE_DIR, run_dir, instance)):
        return "no_instance_dir"
    trajs = glob.glob(
        os.path.join(BASE_DIR, run_dir, instance, "**", "*.traj.json"),
        recursive=True,
    )
    if not trajs:
        return "no_trajectory"
    with open(trajs[0]) as f:
        traj = json.load(f)
    for message in reversed(traj.get("messages", [])):
        if message.get("role") == "exit":
            return message.get("extra", {}).get("exit_status", "unknown")
    return "no_exit_message"


def main():
    instances = load_instances()
    pairs = discover_runs()
    if not pairs:
        print("No swebench-fl-<model>-run<N> directories found.")
        return

    # ordered unique models and the runs available for each
    models = sorted({m for m, _, _ in pairs})
    runs_of = {m: sorted(r for mm, r, _ in pairs if mm == m) for m in models}
    dir_of = {(m, r): d for m, r, d in pairs}

    # results[(model, run)] = {instance: bool|None}
    results = {(m, r): collect_results(dir_of[(m, r)], instances)
               for m, r, _ in pairs}
    print(f"Processing {len(instances)} instances across {len(pairs)} runs "
          f"({len(models)} models)\n")

    def resolved_runs(model, instance):
        """How many of a model's runs resolved this instance (None -> no)."""
        return sum(1 for r in runs_of[model]
                   if results[(model, r)].get(instance) is True)

    # ---- wide per-instance matrix: instance x (model/run) ----
    wide_path = os.path.join(BASE_DIR, "result-summary.csv")
    col_pairs = [(m, r) for m in models for r in runs_of[m]]
    with open(wide_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["instance"] + [f"{m}/run{r}" for m, r in col_pairs])
        for instance in instances:
            row = [instance]
            for m, r in col_pairs:
                v = results[(m, r)].get(instance)
                row.append("missing" if v is None else str(v))
            w.writerow(row)

    # ---- compact per-instance counts: instance x model = k/N ----
    counts_path = os.path.join(BASE_DIR, "result-summary-counts.csv")
    with open(counts_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["instance"] + models)
        for instance in instances:
            row = [instance]
            for m in models:
                row.append(f"{resolved_runs(m, instance)}/{len(runs_of[m])}")
            w.writerow(row)

    # ---- per-run + aggregate model summary ----
    summary_path = os.path.join(BASE_DIR, "model-summary.csv")
    header = ["model", "run", "total", "evaluated", "resolved", "rate"]
    print(f"{'model':28} {'run':>10} {'total':>6} {'eval':>6} {'resolved':>9} {'rate':>8}")
    rows = []
    for m in models:
        R = len(runs_of[m])
        run_rates = []
        for r in runs_of[m]:
            res = results[(m, r)]
            total = len(res)
            evaluated = sum(1 for v in res.values() if v is not None)
            resolved = sum(1 for v in res.values() if v)
            rate = resolved / total * 100 if total else 0.0
            run_rates.append(rate)
            rows.append([m, f"run{r}", total, evaluated, resolved, f"{rate:.2f}%"])
            print(f"{m:28} {('run'+str(r)):>10} {total:>6} {evaluated:>6} "
                  f"{resolved:>9} {rate:>7.2f}%")

        # cross-run aggregates over the instance set
        total = len(instances)
        any_res = sum(1 for i in instances if resolved_runs(m, i) >= 1)
        maj_res = sum(1 for i in instances if resolved_runs(m, i) >= R // 2 + 1)
        all_res = sum(1 for i in instances if resolved_runs(m, i) == R)
        mean_rate = sum(run_rates) / len(run_rates) if run_rates else 0.0
        for label, val in [("mean", None), (f"any@{R}", any_res),
                           (f"majority@{R}", maj_res), (f"all@{R}", all_res)]:
            if label == "mean":
                rows.append([m, "mean", total, "-", "-", f"{mean_rate:.2f}%"])
                print(f"{m:28} {'mean':>10} {total:>6} {'-':>6} {'-':>9} "
                      f"{mean_rate:>7.2f}%")
            else:
                rate = val / total * 100 if total else 0.0
                rows.append([m, label, total, "-", val, f"{rate:.2f}%"])
                print(f"{m:28} {label:>10} {total:>6} {'-':>6} {val:>9} "
                      f"{rate:>7.2f}%")
        print()

    with open(summary_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)

    # ---- missing report.json per (model, run) ----
    missing = {
        f"{m}/run{r}": {
            i: get_exit_status(dir_of[(m, r)], i)
            for i, v in sorted(results[(m, r)].items()) if v is None
        }
        for m, r, _ in pairs
    }
    missing_path = os.path.join(BASE_DIR, "missing-reports.json")
    with open(missing_path, "w") as f:
        json.dump(missing, f, indent=2)

    # missing counts pivoted as (model/run) x exit_status
    statuses = sorted(
        {s for insts in missing.values() for s in insts.values()},
        key=lambda s: -sum(list(insts.values()).count(s) for insts in missing.values()),
    )
    missing_csv_path = os.path.join(BASE_DIR, "missing-reports.csv")
    with open(missing_csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model/run"] + statuses)
        for m, r, _ in pairs:
            label = f"{m}/run{r}"
            if not missing[label]:
                continue
            counts = list(missing[label].values())
            w.writerow([label] + [counts.count(s) or "-" for s in statuses])

    print(f"Per-instance matrix (wide)   -> {wide_path}")
    print(f"Per-instance counts (k/N)    -> {counts_path}")
    print(f"Model summary (per-run+agg)  -> {summary_path}")
    print(f"Missing reports              -> {missing_path} and {missing_csv_path}")


if __name__ == "__main__":
    main()
