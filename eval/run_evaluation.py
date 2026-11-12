"""Measure Documentation Digester retrieval quality against frozen labels.

From the project root:
    python -m eval.run_evaluation --backend api --label baseline --output eval/results/baseline.json
    python -m eval.run_evaluation --backend local --strategy semantic --chunk-size 800 \
        --label semantic-800 --output eval/results/semantic-800.json

The API benchmark measures HTTP round-trip latency and tests the actual indexed
collection. The local benchmark uses the team's chunk() implementation and
SentenceTransformer on the seven checked-in source files, without changing the DB.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eval.metrics import score_question, summarize

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS_PATH = ROOT / "eval" / "questions.json"
DEFAULT_OUTPUT = ROOT / "eval" / "results" / "baseline.json"
DOCS_DIR = ROOT / "data" / "docs"
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def load_questions(path: Path = QUESTIONS_PATH, validate_sources: bool = True) -> tuple[list[dict[str, Any]], str]:
    """Verify unique IDs, labels, source existence and section names.

    This deliberately fails loudly when the dataset and docs get out of sync.
    Never silently change evaluation labels based on the model's output.
    """
    data = path.read_bytes()
    questions = json.loads(data)
    if not isinstance(questions, list) or not questions:
        raise ValueError("Question file must contain a nonempty list")
    seen = set()
    for q in questions:
        required = ("id", "question", "expected_source_file", "expected_heading", "style")
        for key in required:
            if not isinstance(q.get(key), str) or not q[key].strip():
                raise ValueError(f"Invalid question {q!r}: missing {key}")
        if q["id"] in seen:
            raise ValueError(f"Duplicate question ID: {q['id']}")
        seen.add(q["id"])
        if q["style"] not in ("keyword", "paraphrase"):
            raise ValueError(f"Unexpected question style for {q['id']}: {q['style']}")
        file_name = q["expected_source_file"]
        if Path(file_name).name != file_name:
            raise ValueError(f"Question {q['id']} has unsafe source filename: {file_name}")
        if validate_sources:
            source = DOCS_DIR / file_name
            if not source.is_file():
                raise ValueError(f"Question {q['id']} refers to missing source: {source}")
            # Exact heading is present in the source's Markdown-style bold line.
            import re
            text = source.read_text(encoding="utf-8")
            headings = re.findall(r"^\*\*(.+?)\*\*\s*$", text, re.MULTILINE)
            norm = lambda s: s.strip().rstrip(":").casefold()
            if norm(q["expected_heading"]) not in {norm(h) for h in headings}:
                raise ValueError(f"Question {q['id']} refers to missing heading: {q['expected_heading']!r}")
    return questions, hashlib.sha256(data).hexdigest()


def fetch_api_results(base_url: str, question: str, k: int, timeout: int) -> tuple[list[dict], float]:
    params = urllib.parse.urlencode({"query": question, "k": k})
    url = f"{base_url.rstrip('/')}/search?{params}"
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Search failed for {question!r}: {exc}") from exc
    elapsed_ms = (time.perf_counter() - t0) * 1000
    results = payload.get("results") if isinstance(payload, dict) else payload
    if not isinstance(results, list):
        raise ValueError(f"Unexpected /search response (expected list or object with results): {str(payload)[:160]}")
    return results, elapsed_ms


def evaluate_api(questions: list[dict], k: int = 5, url: str = "http://127.0.0.1:8000",
                 warmup: int = 2, timeout: int = 60) -> tuple[list[dict], dict]:
    if not 1 <= k <= 20:
        raise ValueError("API k must be between 1 and 20")
    for _ in range(warmup):
        # Warm the endpoint/model so we're measuring steady-state response time.
        fetch_api_results(url, questions[0]["question"], k, timeout)
    details = []
    for q in questions:
        results, elapsed = fetch_api_results(url, q["question"], k, timeout)
        one = score_question(q, results, k)
        one["latency_ms"] = round(elapsed, 2)
        details.append(one)
    return details, {"backend": "api", "url": url, "warmup_requests": warmup, "timeout_seconds": timeout,
                     "latency_scope": "client-measured HTTP round trip; warmup excluded"}


def evaluate_local(questions: list[dict], strategy: str = "length", chunk_size: int = 800,
                   overlap: int | None = None, k: int = 5, model=None) -> tuple[list[dict], dict]:
    """Evaluate chunker changes in memory using the real local embedding model.

    Important: the team's current ingestion uses its own 800/100 default. For
    comparisons this function applies the requested size/overlap to the team
    chunking module; changing this experiment does NOT update the Chroma index.
    """
    try:
        import numpy as np
        from sentence_transformers import SentenceTransformer
        from ingest.chunking import chunk
        from ingest.ingest import MODEL_NAME, load_documents
    except ImportError as exc:
        raise RuntimeError("Install project dependencies first: pip install -r requirements.txt") from exc

    if strategy not in ("length", "semantic","hybrid"):
        raise ValueError("strategy must be length or semantic or hybrid")
    if chunk_size < 250:
        raise ValueError("chunk size must be at least 250 characters")
    if overlap is None:
        overlap = min(100, chunk_size // 8)
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("Overlap must be >= 0 and smaller than chunk size")
    model = model or SentenceTransformer(MODEL_NAME, device="cpu")
    docs = load_documents()
    t0 = time.perf_counter()
    chunks = []
    for doc in docs:
        metadata = {field: doc[field] for field in ("title", "section", "url", "source_file")}
        chunks.extend(chunk(doc["text"], metadata, strategy, chunk_size=chunk_size, chunk_overlap=overlap))
    if not chunks:
        raise RuntimeError("No chunks produced from data/docs")
    chunk_vectors = np.asarray(
        model.encode([d.page_content for d in chunks], batch_size=32, normalize_embeddings=True),
        dtype=np.float32,
    )
    build_seconds = time.perf_counter() - t0
    # Avoid model cold-start overhead in the timing measurements.
    model.encode([questions[0]["question"]], normalize_embeddings=True)

    details = []
    for q in questions:
        q0 = time.perf_counter()
        q_vector = np.asarray(model.encode([q["question"]], normalize_embeddings=True)[0], dtype=np.float32)
        similarities = chunk_vectors @ q_vector
        indexes = np.argsort(-similarities, kind="stable")[:k]
        elapsed_ms = (time.perf_counter() - q0) * 1000
        results = [
            {"text": chunks[int(i)].page_content, **chunks[int(i)].metadata,
             "score": float(similarities[i])}
            for i in indexes
        ]
        one = score_question(q, results, k)
        one["latency_ms"] = round(elapsed_ms, 2)
        details.append(one)
    return details, {
        "backend": "local", "strategy": strategy, "chunk_size": chunk_size,
        "chunk_overlap": overlap, "model": MODEL_NAME, "chunk_count": len(chunks),
        "source_file_count": len(docs), "index_build_seconds": round(build_seconds, 2),
        "latency_scope": "warm model: per-query embedding + NumPy similarity; no HTTP or Chroma overhead",
        "note": "In-memory experiment; does not update the application's Chroma index",
    }


def make_report(questions_hash: str, details: list[dict], config: dict, label: str, k: int = 5) -> dict:
    metrics = summarize(details, k=k)
    # Verify that each retrieved source points to the documented canonical URL,
    # not merely that a URL field exists. Uploaded/unknown sources are excluded.
    manifest = json.loads((ROOT / "data" / "manifest.json").read_text(encoding="utf-8"))
    eligible = correct = 0
    for detail in details:
        for found in detail["top_results"]:
            expected = manifest.get(found["source_file"], {}).get("url")
            if expected:
                eligible += 1
                correct += found["url"].strip().rstrip("/") == expected.strip().rstrip("/")
    metrics["canonical_url_match_pct"] = round(100 * correct / eligible, 2) if eligible else None
    metrics["canonical_url_checked_results"] = eligible
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "label": label,
        "questions_sha256": questions_hash,
        "config": config,
        "metrics": metrics,
        "questions": details,
    }


def save_report(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_team_summary(report: dict, path: Path) -> None:
    """Generate a ready-to-share update containing measured results, not placeholders."""
    m = report["metrics"]
    conf = report["config"]
    backend = conf.get("backend", "unknown")
    label = report["label"]
    script = (
        f"Documentation Digester evaluation ({label}): I ran {m['question_count']} fixed "
        f"Godot documentation questions at top-{m['k']} using {backend} retrieval. "
        f"Hit@1 was {m['hit_at_1_pct']:.2f}%, Hit@5 was {m['hit_at_5_pct']:.2f}%, "
        f"MRR@5 was {m['mrr_at_5']:.4f}, strict section evidence@5 was "
        f"{m['section_hit_at_5_pct']:.2f}%, and average query latency was "
        f"{m['avg_latency_ms']:.2f} ms (p95 {m['p95_latency_ms']:.2f} ms). "
        f"Provenance completeness was {m['provenance_coverage_pct']:.2f}%. "
        f"The report records each question's top five results and expected source."
    )
    note = (
        "This is the team's API/Chroma search performance; latency includes HTTP."
        if backend == "api" else
        "This is an in-memory SentenceTransformer retrieval experiment, not API latency."
        if backend == "local" else
        "This is a lexical diagnostic only, NOT the semantic-search model."
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Team evaluation update\n\n" + script + "\n\n**Measurement scope:** " + note + "\n\n" +
        f"**Dataset SHA256:** `{report['questions_sha256']}`\n\n" +
        f"**Configuration:** `{json.dumps(conf, sort_keys=True)}`\n",
        encoding="utf-8",
    )


def print_summary(report: dict, path: Path | None = None) -> None:
    m = report["metrics"]
    print(f"\nEvaluation: {report['label']}  ({m['question_count']} questions, top-{m['k']})")
    print(f"Hit@1: {m['hit_at_1_pct']:.1f}% | Hit@5: {m['hit_at_5_pct']:.1f}% | MRR@5: {m['mrr_at_5']:.3f}")
    print(f"Section evidence@5: {m['section_hit_at_5_pct']:.1f}% | Provenance fields: {m['provenance_coverage_pct']:.1f}%")
    if m["canonical_url_match_pct"] is not None:
        print(f"Canonical source URLs: {m['canonical_url_match_pct']:.1f}% across {m['canonical_url_checked_results']} indexed hits")
    print(f"Avg latency: {m['avg_latency_ms']:.1f} ms | P95 latency: {m['p95_latency_ms']:.1f} ms")
    misses = [d["id"] for d in report["questions"] if not d["page_rank"]]
    print(f"Missed pages in top-{m['k']}: {', '.join(misses) if misses else 'none'}")
    if path:
        print(f"Saved: {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backend", choices=("api", "local"), default="api")
    parser.add_argument("--questions", type=Path, default=QUESTIONS_PATH)
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("-k", type=int, default=5)
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--warmup", type=int, default=2, help="excluded API warmup requests")
    parser.add_argument("--timeout", type=int, default=60, help="per-request timeout (seconds)")
    parser.add_argument("--strategy", choices=("length", "semantic"), default="length")
    parser.add_argument("--chunk-size", type=int, default=800)
    parser.add_argument("--overlap", type=int, default=None)
    parser.add_argument("--no-chart", action="store_true", help="skip auto-generated baseline PNG")
    args = parser.parse_args(argv)
    if args.k != 5 or args.warmup < 0:
        parser.error("The frozen evaluation reports Hit@5 and MRR@5; use -k 5 and warmup >= 0")
    try:
        questions, digest = load_questions(args.questions)
        if args.backend == "api":
            details, config = evaluate_api(questions, args.k, args.url, args.warmup, args.timeout)
        else:
            details, config = evaluate_local(questions, args.strategy, args.chunk_size, args.overlap, args.k)
        report = make_report(digest, details, config, args.label, args.k)
        save_report(report, args.output)
        print_summary(report, args.output)
        summary_path = args.output.with_name(args.output.stem + "_team_update.md")
        write_team_summary(report, summary_path)
        print(f"Team update: {summary_path}")
        if not args.no_chart:
            from eval.plot_results import plot_reports
            chart_path = args.output.with_suffix(".png")
            plot_reports([report], chart_path)
            print(f"Baseline chart: {chart_path}")
    except (RuntimeError, ValueError, OSError) as exc:
        parser.exit(1, f"Evaluation failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
