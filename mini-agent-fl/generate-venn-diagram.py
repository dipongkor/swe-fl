"""Draw a 4-set Venn diagram of resolved instances per model.

Reads result-summary.csv (produced by generate-result-summary.py) and writes
venn-resolved.png. The 4-ellipse layout is the classic construction used by
pyvenn, so no venn library is needed.
"""

import csv
import os

import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MODEL_DIRS = [
    "swebench-fl-claude-opus",
    "swebench-fl-gemini-3.1-flash-lite",
    "swebench-fl-gpt-5-3-codex-v3",
    "swebench-fl-minimax-m3",
]

COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]

# (cx, cy, width, height, angle) in axes fractions
ELLIPSES = [
    (0.350, 0.400, 0.72, 0.45, 140.0),
    (0.450, 0.500, 0.72, 0.45, 140.0),
    (0.544, 0.500, 0.72, 0.45, 40.0),
    (0.644, 0.400, 0.72, 0.45, 40.0),
]

# region label positions keyed by membership mask, e.g. "1010" means the
# region inside sets 1 and 3 only (set order = MODEL_DIRS order)
REGION_POS = {
    "1000": (0.14, 0.42),
    "0100": (0.32, 0.72),
    "0010": (0.68, 0.72),
    "0001": (0.85, 0.42),
    "1100": (0.23, 0.59),
    "1010": (0.29, 0.30),
    "1001": (0.50, 0.17),
    "0110": (0.50, 0.66),
    "0101": (0.71, 0.30),
    "0011": (0.77, 0.59),
    "1110": (0.35, 0.50),
    "1101": (0.61, 0.24),
    "1011": (0.39, 0.24),
    "0111": (0.65, 0.50),
    "1111": (0.50, 0.38),
}

NAME_POS = [(0.13, 0.18), (0.18, 0.83), (0.82, 0.83), (0.87, 0.18)]
NAME_ALIGN = ["right", "right", "left", "left"]


def load_resolved_sets():
    """Return {model: set(resolved instances)} from result-summary.csv."""
    sets = {model: set() for model in MODEL_DIRS}
    with open(os.path.join(BASE_DIR, "result-summary.csv")) as f:
        for row in csv.DictReader(f):
            for model in MODEL_DIRS:
                if row[model] == "True":
                    sets[model].add(row["instance"])
    return sets


def main():
    sets = load_resolved_sets()
    members = [sets[model] for model in MODEL_DIRS]
    universe = set().union(*members)

    regions = {}
    for instance in universe:
        mask = "".join("1" if instance in s else "0" for s in members)
        regions[mask] = regions.get(mask, 0) + 1

    fig, ax = plt.subplots(figsize=(9, 8))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.axis("off")

    for (cx, cy, w, h, angle), color in zip(ELLIPSES, COLORS):
        ax.add_patch(
            Ellipse((cx, cy), w, h, angle=angle, facecolor=color, alpha=0.35,
                    edgecolor=color, linewidth=2)
        )

    for mask, (x, y) in REGION_POS.items():
        ax.text(x, y, str(regions.get(mask, 0)), ha="center", va="center",
                fontsize=13, color="#1a1a19")

    for model, (x, y), align, color in zip(MODEL_DIRS, NAME_POS, NAME_ALIGN, COLORS):
        name = model.removeprefix("swebench-fl-")
        ax.text(x, y, f"{name} ({len(sets[model])})", ha=align, va="center",
                fontsize=12, color=color, fontweight="bold")

    ax.set_title(f"Resolved instances per model (union: {len(universe)})",
                 fontsize=14, color="#1a1a19", pad=16)

    out_path = os.path.join(BASE_DIR, "venn-resolved.pdf")
    fig.savefig(out_path, dpi=300, bbox_inches="tight", facecolor="white")
    print(f"Venn diagram written to {out_path}")

    only = {model: regions.get("".join("1" if m == model else "0" for m in MODEL_DIRS), 0)
            for model in MODEL_DIRS}
    print(f"Resolved by all 4 models: {regions.get('1111', 0)}")
    for model, count in only.items():
        print(f"Resolved only by {model.removeprefix('swebench-fl-')}: {count}")


if __name__ == "__main__":
    main()
