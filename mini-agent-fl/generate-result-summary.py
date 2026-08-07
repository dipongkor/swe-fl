import csv
import glob
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MODEL_DIRS = [
    "swebench-fl-claude-opus",
    "swebench-fl-gemini-3.1-flash-lite",
    "swebench-fl-gpt-5-3-codex-v3",
    "swebench-fl-minimax-m3",
]


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


def collect_results(model_dir, instances):
    """Return {instance: resolved_bool_or_None} for one model directory.

    None means no report.json was found (evaluation missing/failed, or the
    instance directory itself is absent).
    """
    results = {}
    root = os.path.join(BASE_DIR, model_dir)
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


def get_exit_status(model_dir, instance):
    """Read the agent's exit status from the instance's .traj.json, if present."""
    if not os.path.isdir(os.path.join(BASE_DIR, model_dir, instance)):
        return "no_instance_dir"
    trajs = glob.glob(
        os.path.join(BASE_DIR, model_dir, instance, "**", "*.traj.json"),
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
    all_results = {model: collect_results(model, instances) for model in MODEL_DIRS}
    print(f"Processing {len(instances)} instances from verified-buggy-instances.txt\n")

    # per-instance matrix
    matrix_path = os.path.join(BASE_DIR, "result-summary.csv")
    with open(matrix_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["instance"] + MODEL_DIRS)
        for instance in instances:
            row = [instance]
            for model in MODEL_DIRS:
                resolved = all_results[model].get(instance)
                row.append("missing" if resolved is None else str(resolved))
            writer.writerow(row)

    # missing report.json per model
    missing = {
        model: {
            i: get_exit_status(model, i)
            for i, v in sorted(results.items())
            if v is None
        }
        for model, results in all_results.items()
    }
    missing_path = os.path.join(BASE_DIR, "missing-reports.json")
    with open(missing_path, "w") as f:
        json.dump(missing, f, indent=2)

    # missing counts pivoted as model x exit_status
    statuses = sorted(
        {s for insts in missing.values() for s in insts.values()},
        key=lambda s: -sum(list(insts.values()).count(s) for insts in missing.values()),
    )
    missing_csv_path = os.path.join(BASE_DIR, "missing-reports.csv")
    with open(missing_csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["model"] + statuses)
        for model in MODEL_DIRS:
            if not missing[model]:
                continue
            counts = list(missing[model].values())
            row = [model.removeprefix("swebench-fl-")]
            row += [counts.count(s) or "-" for s in statuses]
            writer.writerow(row)

    # per-model summary
    summary_path = os.path.join(BASE_DIR, "model-summary.csv")
    print(f"{'model':40} {'total':>6} {'evaluated':>10} {'resolved':>9} {'rate':>8}")
    with open(summary_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["model", "total", "evaluated", "resolved", "rate"])
        for model in MODEL_DIRS:
            results = all_results[model]
            total = len(results)
            evaluated = sum(1 for v in results.values() if v is not None)
            resolved = sum(1 for v in results.values() if v)
            rate = resolved / total * 100 if total else 0.0
            print(f"{model:40} {total:>6} {evaluated:>10} {resolved:>9} {rate:>7.2f}%")
            writer.writerow([model, total, evaluated, resolved, f"{rate:.2f}%"])

    print(f"\nPer-instance matrix written to {matrix_path}")
    print(f"Model summary written to {summary_path}")
    print(f"Missing reports written to {missing_path} and {missing_csv_path}")


if __name__ == "__main__":
    main()
