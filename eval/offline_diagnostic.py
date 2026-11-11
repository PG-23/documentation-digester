"""Offline, dependency-free BM25 *lexical diagnostic* for the fixed Godot questions.

This produces honest baseline numbers without a running API, embedding model, or
Chroma installation. It is NOT a measurement of the semantic search pipeline.
The two local chunking methods here are approximations for a diagnostic sweep,
NOT a claim to be the team's ingest.chunking implementation.

    python -m eval.offline_diagnostic

The production semantic benchmark is: python -m eval.run_evaluation --backend api
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import time
from typing import Any

from eval.metrics import score_question
from eval.run_evaluation import ROOT, DOCS_DIR, load_questions, make_report, save_report, print_summary

DEFAULT_OUTPUT = ROOT / "eval" / "deliverables" / "lexical_diagnostic"
HEADING_RE = re.compile(r"^\*\*(.+?)\*\*\s*$")
TOKEN_RE = re.compile(r"[a-z0-9]+(?:[+#][a-z0-9]+)*", re.I)


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.casefold())


def split_content(raw: str) -> str:
    """Strip the team's TITLE/SOURCE/CATEGORY header (no ingestion imports)."""
    return raw.split("CONTENT:", 1)[-1].strip() if "CONTENT:" in raw else raw.strip()


def windows(text: str, size: int, overlap: int) -> list[str]:
    """Bounded windows with an effort to stop on paragraph/sentence boundaries."""
    if not text.strip():
        return []
    if not 0 <= overlap < size:
        raise ValueError("overlap must be between zero and size - 1")
    out = []
    start = 0
    while start < len(text):
        limit = min(start + size, len(text))
        end = limit
        if limit < len(text):
            low = start + int(size * 0.60)
            # Keep meaningful words intact; separators mark natural split points.
            for sep in ("\n\n", ". ", "\n", " "):
                pos = text.rfind(sep, low, limit)
                if pos >= low:
                    end = pos + len(sep)
                    break
        piece = text[start:end].strip()
        if piece:
            out.append(piece)
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return out


def source_sections(text: str) -> list[tuple[str, str]]:
    """Split on explicit bold, standalone headings in the checked-in source."""
    sections = []
    heading = ""
    buf: list[str] = []
    for line in text.splitlines():
        match = HEADING_RE.match(line.strip())
        if match:
            if any(s.strip() for s in buf):
                sections.append((heading, "\n".join(buf).strip()))
            heading = match.group(1).strip().rstrip(":")
            buf = []
        else:
            buf.append(line)
    if any(s.strip() for s in buf):
        sections.append((heading, "\n".join(buf).strip()))
    return sections


def make_chunks(strategy: str, size: int, overlap: int) -> list[dict[str, Any]]:
    """Length or heading-aware approximation; never changes the shared DB."""
    if strategy not in ("length", "semantic"):
        raise ValueError("strategy must be 'length' or 'semantic'")
    if size < 250:
        raise ValueError("chunk size must be >= 250")
    manifest = json.loads((ROOT / "data" / "manifest.json").read_text(encoding="utf-8"))
    results = []
    for filename, metadata in sorted(manifest.items()):
        source = DOCS_DIR / filename
        text = split_content(source.read_text(encoding="utf-8"))
        page_meta = {**metadata, "source_file": filename}
        if strategy == "length":
            for i, body in enumerate(windows(text, size, overlap)):
                results.append({**page_meta, "text": body, "chunk_index": i})
        else:
            i = 0
            for heading, body in source_sections(text):
                prefix = f"{metadata['title']} > {heading}\n\n" if heading else f"{metadata['title']}\n\n"
                body_room = max(100, size - len(prefix))
                for part in windows(body, body_room, min(overlap, body_room - 1)):
                    results.append({**page_meta, "text": prefix + part, "heading": heading, "chunk_index": i})
                    i += 1
    if not results:
        raise ValueError("No source documents could be chunked")
    return results


class BM25:
    """Simple Okapi BM25, corpus-only indexed lexical retrieval."""

    def __init__(self, chunks: list[dict[str, Any]]):
        self.chunks = chunks
        self.counts = [Counter(tokenize(item["text"])) for item in chunks]
        self.lengths = [sum(counter.values()) for counter in self.counts]
        self.avgdl = sum(self.lengths) / max(len(self.lengths), 1)
        df = Counter(token for counts in self.counts for token in counts)
        n = len(chunks)
        self.idf = {term: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()}

    def search(self, question: str, k: int = 5) -> list[dict[str, Any]]:
        query_terms = set(tokenize(question))
        scores = []
        for i, (counts, dl) in enumerate(zip(self.counts, self.lengths)):
            score = 0.0
            for token in query_terms:
                count = counts.get(token, 0)
                if count:
                    denom = count + 1.5 * (0.25 + 0.75 * dl / self.avgdl)
                    score += self.idf[token] * count * 2.5 / denom
            scores.append(score)
        # Avoid awarding zero-score chunks as valid hits: no query-term overlap.
        ordered = sorted((i for i in range(len(scores)) if scores[i] > 0),
                         key=lambda i: (-scores[i], i))[:k]
        return [{**self.chunks[i], "score": round(scores[i], 5)} for i in ordered]


def evaluate(questions: list[dict[str, Any]], strategy: str, size: int,
             overlap: int, k: int = 5) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    t0 = time.perf_counter()
    chunks = make_chunks(strategy, size, overlap)
    index = BM25(chunks)
    build_seconds = time.perf_counter() - t0
    details = []
    # Timing is measured around retrieval only, excluding index construction.
    for q in questions:
        q0 = time.perf_counter()
        hits = index.search(q["question"], k=k)
        latency = (time.perf_counter() - q0) * 1000
        row = score_question(q, hits, k=k)
        row["latency_ms"] = round(latency, 4)
        details.append(row)
    return details, {
        "backend": "bm25",
        "retriever": "Okapi BM25 (lexical, NOT sentence-transformer semantic search)",
        "strategy": strategy,
        "chunk_size": size,
        "chunk_overlap": overlap,
        "chunker_note": "Independent heading-aware/length diagnostic approximation; not ingest.chunking",
        "chunk_count": len(chunks),
        "source_file_count": 7,
        "index_build_seconds": round(build_seconds, 4),
        "latency_scope": "local Python BM25 query ranking only; excludes index construction, HTTP, embeddings and Chroma",
        "not_semantic_model_baseline": True,
    }


def run(output_dir: Path = DEFAULT_OUTPUT, sizes: list[int] | None = None,
        strategies: list[str] | None = None) -> list[dict[str, Any]]:
    questions, digest = load_questions()
    sizes = sizes or [300, 500, 800, 1000, 1200]
    strategies = strategies or ["length", "semantic"]
    reports = []
    for strategy in strategies:
        for size in sizes:
            label = f"bm25-{strategy}-{size}"
            detail, config = evaluate(questions, strategy, size, min(100, size // 8))
            report = make_report(digest, detail, config, label)
            save_report(report, output_dir / f"{label}.json")
            reports.append(report)
            print_summary(report)
    from eval.plot_results import plot_reports
    plot_reports(reports, output_dir / "lexical_chunking_comparison.png",
                 title="Lexical BM25 Diagnostic | NOT Semantic Search")
    baseline = next((r for r in reports if r["label"] == "bm25-length-800"), reports[0])
    plot_reports([baseline], output_dir / "lexical_baseline.png",
                 title="Lexical BM25 Baseline | NOT Semantic Search")
    best = max(reports, key=lambda r: (r["metrics"]["mrr_at_5"],
                                           r["metrics"]["hit_at_5_pct"]))
    b = baseline["metrics"]
    n = best["metrics"]
    report = f"""# Offline evaluation results: lexical diagnostic, not semantic search

These values are **real measurements** of the seven checked-in Godot documents and
teammate-owned `eval/questions.json` (25 questions), made using local BM25 token
matching and independent approximation chunkers. **They are NOT model/Chroma/API
results and MUST NOT be presented as the semantic-search baseline or as proof
that the team's production chunker was tested.** BM25 does not understand synonyms.

Dataset SHA256: `{digest}`.

## Baseline: BM25 + length chunks (800 characters)

- Hit@1: **{b['hit_at_1_pct']:.2f}%**
- Hit@5: **{b['hit_at_5_pct']:.2f}%**
- MRR@5: **{b['mrr_at_5']:.4f}**
- Strict section evidence@5: **{b['section_hit_at_5_pct']:.2f}%**
- Average BM25 query ranking latency: **{b['avg_latency_ms']:.2f} ms**
- P95 BM25 query ranking latency: **{b['p95_latency_ms']:.2f} ms**

## Best diagnostic configuration by page-level MRR@5

- **{best['label']}**: Hit@5 **{n['hit_at_5_pct']:.2f}%**,
  MRR@5 **{n['mrr_at_5']:.4f}**, avg BM25 query latency **{n['avg_latency_ms']:.2f} ms**.

The measured BM25 latency only includes in-process token matching and scoring.
It excludes the embedding model, HTTP request, vector database and index loading.

## To get the actual team's semantic-search baseline

1. With the team's dependencies and index configured, run `python -m eval.run_evaluation --backend api --label semantic-baseline --output eval/results/semantic-baseline.json`.
2. Run `python -m eval.plot_results eval/results/semantic-baseline.json --output eval/results/semantic-baseline.png`.
3. Compare real embedding-based chunking via `python -m eval.compare_chunkers`.
4. Share **those** scores in the demo; this BM25 diagnostic can be a separate reference baseline.
"""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "RESULTS.md").write_text(report, encoding="utf-8")
    print(f"\nSaved measured BM25 diagnostic charts and reports to {output_dir}")
    return reports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=[300, 500, 800, 1000, 1200])
    parser.add_argument("--strategies", nargs="+", choices=["length", "semantic"],
                        default=["length", "semantic"])
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        run(args.output_dir, args.sizes, args.strategies)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Offline diagnostic failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
