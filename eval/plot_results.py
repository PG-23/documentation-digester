"""Create a presentation-ready chart from actual evaluation result JSON files.

    python -m eval.plot_results eval/results/baseline.json
    python -m eval.plot_results eval/results/baseline.json eval/results/semantic-800.json \
        --output eval/results/baseline_vs_semantic.png
    python -m eval.plot_results eval/results/experiments/*.json \
        --output eval/results/chunking_comparison.png

Never hardcodes or fabricates performance figures: all plotted measurements
must come from completed evaluation runs (API, embedding model, or BM25 diagnostic).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def plot_reports(reports: list[dict], output: Path, title: str = "Godot Docs | Retrieval Evaluation") -> None:
    if not reports:
        raise ValueError("No evaluation reports to chart")
    hashes = {r.get("questions_sha256") for r in reports}
    if len(hashes) != 1 or None in hashes:
        raise ValueError("Reports must use the identical frozen question dataset (SHA256 mismatch)")
    k_values = {r["metrics"]["k"] for r in reports}
    if len(k_values) != 1:
        raise ValueError("Cannot compare reports with different top-k settings")
    sources = {r["config"].get("backend", "unknown") for r in reports}
    if len(sources) != 1:
        raise ValueError("Cannot compare latency from different backends; plot them separately")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    labels = [r["label"] for r in reports]
    if len(set(labels)) != len(labels):
        raise ValueError("Report labels must be unique")
    metrics = [r["metrics"] for r in reports]

    bg, fg, muted, grid = "#111a27", "#f0f6ff", "#a2b1c5", "#364358"
    colors = {"hit_at_1_pct": "#62b6ff", "hit_at_5_pct": "#36d3b1",
              "mrr_at_5": "#f8bb68", "section_hit_at_5_pct": "#d6a4ff"}
    plt.rcParams.update({
        "figure.facecolor": bg, "axes.facecolor": bg, "axes.edgecolor": grid,
        "axes.labelcolor": fg, "text.color": fg, "xtick.color": muted,
        "ytick.color": muted, "grid.color": grid, "font.size": 10,
    })

    experiment = len(reports) > 2 and all(r["config"].get("backend") in ("local", "bm25")
                                           and "chunk_size" in r["config"] for r in reports)
    if experiment:
        fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))
        panels = [
            ("hit_at_1_pct", "Hit@1", "%", 100),
            ("hit_at_5_pct", "Hit@5", "%", 100),
            ("mrr_at_5", "MRR@5", "score", 1),
            ("avg_latency_ms", "Average query latency", "ms", None),
        ]
        strategy_colors = {"length": "#62b6ff", "semantic": "#36d3b1"}
        for ax, (key, heading, unit, ymax) in zip(axes.flat, panels):
            for strategy in sorted({r["config"]["strategy"] for r in reports}):
                group = sorted([r for r in reports if r["config"]["strategy"] == strategy],
                               key=lambda r: r["config"]["chunk_size"])
                sizes = [r["config"]["chunk_size"] for r in group]
                values = [r["metrics"][key] for r in group]
                ax.plot(sizes, values, marker="o", markersize=6, linewidth=2.5,
                        color=strategy_colors.get(strategy, "#d6a4ff"), label=strategy)
            ax.set_title(heading, loc="left", fontweight="bold", pad=10)
            ax.set_xlabel("Chunk size (characters)")
            ax.set_ylabel(unit)
            if ymax is not None:
                ax.set_ylim(0, ymax * 1.05)
            else:
                ax.set_ylim(bottom=0)
            ax.grid(alpha=0.55, axis="y")
            ax.spines[["top", "right"]].set_visible(False)
        axes[0, 0].legend(loc="best", frameon=False, labelcolor=fg)
        fig.suptitle(title, x=0.07, y=0.98, ha="left", fontsize=20, fontweight="bold")
        fig.text(0.07, 0.935, f"{metrics[0]['question_count']} labeled Godot questions  |  page-level relevance  |  {next(iter(sources))} benchmark",
                 color=muted, fontsize=11)
        fig.tight_layout(rect=(0.03, 0.04, 0.98, 0.89), h_pad=2.3)
    else:
        fig, (left, right) = plt.subplots(1, 2, figsize=(12.5, 5.8), gridspec_kw={"width_ratios": [1.9, 1]})
        x = np.arange(len(labels))
        width = 0.25
        for offset, (key, title_part) in enumerate([
            ("hit_at_1_pct", "Hit@1"), ("hit_at_5_pct", "Hit@5"), ("mrr_at_5", "MRR@5 (×100)")
        ]):
            vals = [m[key] * (100 if key == "mrr_at_5" else 1) for m in metrics]
            shift = (offset - 1) * width
            bars = left.bar(x + shift, vals, width, color=colors[key], label=title_part)
            for bar in bars:
                left.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                          f"{bar.get_height():.0f}", ha="center", va="bottom", fontsize=9)
        left.set_title("Retrieval accuracy", loc="left", fontweight="bold", pad=14)
        left.set_xticks(x, labels, rotation=15 if len(labels) > 3 else 0, ha="center")
        left.set_ylim(0, 112)
        left.set_ylabel("Score / percent")
        left.legend(ncol=3, frameon=False, loc="upper center", fontsize=9)
        left.grid(axis="y", alpha=0.5)
        vals = [m["avg_latency_ms"] for m in metrics]
        bars = right.bar(labels, vals, color="#d6a4ff", width=0.55)
        for bar in bars:
            right.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(vals) * 0.03,
                       f"{bar.get_height():.1f} ms", ha="center", va="bottom", fontsize=9)
        right.set_ylim(0, max(max(vals) * 1.25, 1))
        right.set_title("Average query latency", loc="left", fontweight="bold", pad=14)
        right.set_ylabel("Milliseconds")
        right.tick_params(axis="x", labelrotation=15 if len(labels) > 3 else 0)
        right.grid(axis="y", alpha=0.5)
        for ax in (left, right):
            ax.spines[["top", "right"]].set_visible(False)
            ax.set_axisbelow(True)
        fig.suptitle(title, x=0.06, y=0.99, ha="left", fontsize=20, fontweight="bold")
        fig.text(0.06, 0.92, f"{metrics[0]['question_count']} labeled questions  |  top-{metrics[0]['k']}  |  {next(iter(sources))} benchmark",
                 color=muted, fontsize=11)
        fig.tight_layout(rect=(0.02, 0.02, 0.99, 0.85))

    footer = ("LEXICAL BM25 ONLY: not a semantic/Chroma/API benchmark. " if "bm25" in sources else "") + ("Page-level metrics check source_file; strict section evidence in JSON.")
    fig.text(0.5, 0.013, footer,
             ha="center", fontsize=9, color=muted)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=190, bbox_inches="tight", facecolor=bg)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("reports", nargs="+", type=Path, help="evaluation report JSON files")
    parser.add_argument("--output", type=Path, default=Path("eval/results/evaluation_chart.png"))
    parser.add_argument("--title", default="Godot Docs | Retrieval Evaluation")
    args = parser.parse_args(argv)
    try:
        reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.reports]
        plot_reports(reports, args.output, args.title)
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(1, f"Chart failed: {exc}\n")
    print(f"Saved chart: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
