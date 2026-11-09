"""
benchmark/visualizer.py
-----------------------
STORY-014: Results Analysis, Visualization & Research Report Generator.

Loads benchmark_results.json and produces:
  1. data/results/comparison_table.md   - Markdown comparison table
  2. data/results/charts/gir.png        - GIR bar chart
  3. data/results/charts/cr.png         - CR bar chart
  4. data/results/charts/cra.png        - CRA bar chart
  5. data/results/charts/ptc.png        - PTC bar chart
  6. data/results/charts/latency.png    - Mean latency bar chart

Usage (run from project root):
    PYTHONPATH=. ./venv/bin/python benchmark/visualizer.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt

RESULTS_PATH = Path("data/results/benchmark_results.json")
CHARTS_DIR   = Path("data/results/charts")
TABLE_PATH   = Path("data/results/comparison_table.md")

PROTOCOL_LABELS = {
    "adhoc":              "Ad-Hoc\n(Baseline)",
    "mpac":               "Full MPAC",
    "ablation_no_a2a":    "Ablation\nNo A2A",
    "ablation_no_locks":  "Ablation\nNo Locks",
    "ablation_timestamp": "Ablation\nTimestamp",
}

PROTOCOL_COLORS = {
    "adhoc":              "#e74c3c",   # Red
    "mpac":               "#2ecc71",   # Green
    "ablation_no_a2a":    "#3498db",   # Blue
    "ablation_no_locks":  "#f39c12",   # Orange
    "ablation_timestamp": "#9b59b6",   # Purple
}


def load_results() -> list[dict]:
    if not RESULTS_PATH.exists():
        raise FileNotFoundError(
            f"{RESULTS_PATH} not found. "
            "Run `PYTHONPATH=. ./venv/bin/python benchmark/runner.py` first."
        )
    with open(RESULTS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _bar_chart(
    results: list[dict],
    metric_key: str,
    title: str,
    ylabel: str,
    output_path: Path,
    lower_is_better: bool = False,
) -> None:
    protocols = [r["protocol"] for r in results]
    values    = [r.get(metric_key, 0.0) for r in results]
    colors    = [PROTOCOL_COLORS.get(p, "#95a5a6") for p in protocols]
    labels    = [PROTOCOL_LABELS.get(p, p) for p in protocols]

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(labels, values, color=colors, edgecolor="black", linewidth=0.8)

    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            bar.get_height() + 0.5,
            f"{val:.1f}",
            ha="center", va="bottom", fontsize=11, fontweight="bold",
        )

    direction = "lower is better" if lower_is_better else "higher is better"
    ax.set_title(f"{title}  ({direction})", fontsize=14, fontweight="bold", pad=15)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_xlabel("Protocol", fontsize=12)
    ax.set_ylim(0, max(values) * 1.25 if max(values) > 0 else 10)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"Chart saved: {output_path}")


def generate_charts(results: list[dict]) -> None:
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)

    _bar_chart(results, "GIR",             "Graph Inconsistency Rate (GIR)",
               "GIR (%)", CHARTS_DIR / "gir.png", lower_is_better=True)

    _bar_chart(results, "CR",              "Conflict Resolution Rate (CR)",
               "CR (%)", CHARTS_DIR / "cr.png", lower_is_better=False)

    _bar_chart(results, "CRA",             "Conflict Resolution Accuracy (CRA)",
               "CRA (%)", CHARTS_DIR / "cra.png", lower_is_better=False)

    _bar_chart(results, "PTC",             "Provenance Trail Completeness (PTC)",
               "PTC (%)", CHARTS_DIR / "ptc.png", lower_is_better=False)

    _bar_chart(results, "mean_latency_ms", "Mean Commit Latency",
               "Latency (ms)", CHARTS_DIR / "latency.png", lower_is_better=True)


def generate_comparison_table(results: list[dict]) -> None:
    lines = [
        "# ProGRESS Benchmark: Protocol Comparison Table\n",
        "| Protocol | GIR (%) ↓ | CR (%) ↑ | CRA (%) ↑ | PTC (%) ↑ | Mean Latency (ms) ↓ | p95 Latency (ms) ↓ |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        label = PROTOCOL_LABELS.get(r["protocol"], r["protocol"]).replace("\n", " ")
        lines.append(
            f"| {label} "
            f"| {r.get('GIR', 0):.1f} "
            f"| {r.get('CR', 0):.1f} "
            f"| {r.get('CRA', 0):.1f} "
            f"| {r.get('PTC', 0):.1f} "
            f"| {r.get('mean_latency_ms', 0):.1f} "
            f"| {r.get('p95_latency_ms', 0):.1f} |"
        )

    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TABLE_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"Comparison table saved: {TABLE_PATH}")


def find_worst_ablation(results: list[dict]) -> str:
    ablation_protocols = [r for r in results if r["protocol"].startswith("ablation")]
    if not ablation_protocols:
        return "N/A"
    worst = max(ablation_protocols, key=lambda r: r.get("GIR", 0))
    return worst["protocol"]


if __name__ == "__main__":
    results = load_results()
    generate_charts(results)
    generate_comparison_table(results)
    worst = find_worst_ablation(results)
    print(f"\nWorst degrading ablation mode (highest GIR): {worst}")
    print("All visualizations complete.")
