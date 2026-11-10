"""Plot the actual *test-set coverage*, not search performance.

Useful for presenting the 25-question golden set while the first embedding
index is being built. The retrieval charts are generated separately by
`python -m eval.plot_results ...` after real evaluation results exist.

    python -m eval.plot_question_coverage --output eval/question_set_coverage.png
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from eval.run_evaluation import ROOT, load_questions

LABELS = {
    "introduction_to_godot.txt": "Introduction",
    "key_concepts_overview.txt": "Key Concepts",
    "scripting_languages.txt": "Scripting Languages",
    "first_2d_game_project_setup.txt": "2D Project Setup",
    "your_first_2d_game.txt": "First 2D Game",
    "first_3d_game_setup.txt": "3D Project Setup",
    "your_first_3d_game.txt": "First 3D Game",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=ROOT / "eval" / "question_set_coverage.png")
    args = parser.parse_args(argv)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    qs, _ = load_questions()
    counts = Counter((q["expected_source_file"], q["style"]) for q in qs)
    files = list(LABELS)
    bg, fg, muted = "#101722", "#f0f6ff", "#a8b4c6"
    fig, ax = plt.subplots(figsize=(11, 6.7), facecolor=bg)
    ax.set_facecolor(bg)
    yy = range(len(files))
    keyword = [counts[(f, "keyword")] for f in files]
    paraphrase = [counts[(f, "paraphrase")] for f in files]
    ax.barh(yy, keyword, label="Keyword", color="#66b8ff", height=0.57)
    ax.barh(yy, paraphrase, left=keyword, label="Paraphrase", color="#33d2b2", height=0.57)
    for y, total in enumerate([keyword[i] + paraphrase[i] for i in range(len(files))]):
        ax.text(total + 0.13, y, str(total), color=fg, va="center", fontweight="bold")
    ax.invert_yaxis()
    ax.set_yticks(list(yy), [LABELS[f] for f in files])
    ax.tick_params(colors=fg, length=0, pad=12)
    ax.set_xlim(0, max(keyword[i] + paraphrase[i] for i in range(len(files))) + 1)
    ax.set_xticks(range(0, 6))
    ax.set_xlabel("Number of labeled questions", color=muted, labelpad=13)
    ax.spines[:].set_visible(False)
    ax.grid(axis="x", alpha=0.18, color="white")
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0.0, 1.02),
              labelcolor=fg, ncol=2)
    fig.suptitle("Godot Docs | Evaluation Dataset", x=0.07, ha="left", y=0.97,
                 color=fg, fontsize=22, fontweight="bold")
    fig.text(0.07, 0.907, f"{len(qs)} verified questions · {len(files)} documentation pages · "
             f"{sum(q['style']=='paraphrase' for q in qs)} paraphrases",
             color=muted, fontsize=12)
    fig.text(0.07, 0.06, "Dataset coverage only. Retrieval accuracy and latency require a running embedding index.",
             color=muted, fontsize=10)
    fig.subplots_adjust(left=0.24, right=0.92, top=0.76, bottom=0.18)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=180, facecolor=bg)
    plt.close(fig)
    print(f"Saved dataset coverage chart: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
