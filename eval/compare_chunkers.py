"""Re-score the fixed 25-question benchmark under multiple chunking settings.

Uses the actual sentence-transformer embeddings and the team's chunking code,
not a simulated index. Each trial is saved separately and a comparison chart
is generated. The application's Chroma collection is never modified.

    python -m eval.compare_chunkers
    python -m eval.compare_chunkers --sizes 500 800 --strategies length semantic
"""

from __future__ import annotations

import argparse
from pathlib import Path

from eval.run_evaluation import (
    DEFAULT_MODEL, ROOT, evaluate_local, load_questions, make_report,
    print_summary, save_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sizes", nargs="+", type=int, default=[300, 500, 800, 1000, 1200])
    parser.add_argument("--strategies", nargs="+", choices=("length", "semantic"), default=["length", "semantic"])
    parser.add_argument("-k", type=int, default=5)
    parser.add_argument("--overlap", type=int, default=None, help="fixed overlap; default is min(100, size // 8)")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "eval" / "results" / "experiments")
    parser.add_argument("--chart", type=Path, default=ROOT / "eval" / "results" / "chunking_comparison.png")
    args = parser.parse_args(argv)

    if args.k != 5 or any(size < 250 for size in args.sizes):
        parser.error("The frozen benchmark uses top-5 only; use -k 5 and chunk sizes >= 250")

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        parser.exit(1, f"Missing dependencies. Run pip install -r requirements.txt first ({exc})\n")
    from eval.plot_results import plot_reports

    questions, digest = load_questions()
    print(f"Loading {DEFAULT_MODEL} once for {len(args.sizes) * len(args.strategies)} trials ...")
    model = SentenceTransformer(DEFAULT_MODEL, device="cpu")
    reports = []
    for strategy in args.strategies:
        for size in args.sizes:
            label = f"{strategy}-{size}"
            print(f"\nRunning {label} ...", flush=True)
            try:
                details, config = evaluate_local(questions, strategy, size, args.overlap, args.k, model=model)
            except (ValueError, RuntimeError) as exc:
                parser.exit(1, f"Unable to evaluate {label}: {exc}\n")
            report = make_report(digest, details, config, label, args.k)
            output = args.output_dir / f"{label}.json"
            save_report(report, output)
            print_summary(report, output)
            reports.append(report)

    ranked = sorted(reports, key=lambda r: (r["metrics"]["mrr_at_5"],
                                            r["metrics"]["hit_at_5_pct"],
                                            -r["metrics"]["avg_latency_ms"]), reverse=True)
    print(f"\nBest tested setup (page MRR): {ranked[0]['label']}")
    plot_reports(reports, args.chart, title="Godot Docs | Chunking Experiment")
    print(f"Demo chart: {args.chart}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
