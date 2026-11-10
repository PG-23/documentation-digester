"""Dependency-free, unit-testable retrieval metrics.

The primary labels are the expected *source page* in questions.json.  A second,
stricter section metric checks for the exact expected heading when the search
result supplies a heading or contains a heading line. A page-level hit alone
must never be described as proof that the correct paragraph was retrieved.
"""

from __future__ import annotations

import math
import re
from statistics import mean
from typing import Any


def _flat(result: dict[str, Any]) -> dict[str, Any]:
    """Support both the team's flat API format and nested metadata results."""
    if not isinstance(result, dict):
        raise ValueError("Each search result must be a JSON object")
    metadata = result.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError("Result metadata must be an object")
    return {**metadata, **{k: v for k, v in result.items() if k != "metadata"}}


def _normalize_heading(text: str) -> str:
    """Normalize markup and a trailing colon without removing meaningful words."""
    text = text.strip().strip("#").strip().strip("*").strip()
    return re.sub(r"\s+", " ", text.rstrip(":").strip()).casefold()


def _has_heading_evidence(result: dict[str, Any], expected: str) -> bool:
    """A matching heading path or a standalone heading line is strong evidence.

    Do not match arbitrary mentions of the heading inside prose, and do not
    mistake 'section' (a broad manifest category) for a specific heading.
    """
    for field in ("heading", "section_heading", "heading_path"):
        path = result.get(field)
        if isinstance(path, str) and path.strip():
            if _normalize_heading(path.split(" > ")[-1]) == _normalize_heading(expected):
                return True

    text = result.get("text") or result.get("page_content") or ""
    if not isinstance(text, str):
        return False
    for line in text.splitlines():
        # The semantic chunker prepends "Page Title > Section Heading".
        # The length chunker retains original "**Section Heading:**" lines.
        candidate = line.strip()
        if candidate.startswith(("- ", "* ", "> ")):
            continue
        candidate = candidate.split(" > ")[-1]
        if _normalize_heading(candidate) == _normalize_heading(expected):
            return True
    return False


def score_question(question: dict[str, Any], results: list[dict[str, Any]], k: int = 5) -> dict[str, Any]:
    """Ranks start at 1; zero means not retrieved in the first k results."""
    if k < 1:
        raise ValueError("k must be at least 1")
    expected_source = question["expected_source_file"]
    expected_heading = question["expected_heading"]
    page_rank = section_rank = 0
    provenance_count = 0
    inspected = []

    for index, raw in enumerate(results[:k], start=1):
        r = _flat(raw)
        correct_page = r.get("source_file") == expected_source
        heading_matches = correct_page and _has_heading_evidence(r, expected_heading)
        if correct_page and not page_rank:
            page_rank = index
        if heading_matches and not section_rank:
            section_rank = index
        if all(isinstance(r.get(key), str) and r[key].strip() for key in ("source_file", "url", "title")):
            provenance_count += 1
        inspected.append({
            "rank": index,
            "source_file": r.get("source_file", ""),
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "heading": r.get("heading", r.get("section_heading", "")),
            "chunk_index": r.get("chunk_index", ""),
            "score": r.get("score"),
            "correct_page": bool(correct_page),
            "correct_section_evidenced": bool(heading_matches),
        })

    return {
        "id": question["id"],
        "question": question["question"],
        "style": question["style"],
        "expected_source_file": expected_source,
        "expected_heading": expected_heading,
        "page_rank": page_rank,
        "section_rank": section_rank,
        "reciprocal_rank": round(1 / page_rank, 6) if page_rank else 0.0,
        "section_reciprocal_rank": round(1 / section_rank, 6) if section_rank else 0.0,
        "returned_count": len(inspected),
        "provenance_count": provenance_count,
        "top_results": inspected,
    }


def _percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile, useful for describing a small benchmark."""
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(math.ceil(p * len(ordered))) - 1))
    return ordered[idx]


def summarize(details: list[dict[str, Any]], k: int = 5) -> dict[str, Any]:
    """Calculate page/section hit rates, MRR, latency, and provenance coverage."""
    if not details:
        raise ValueError("Cannot score an empty question set")
    n = len(details)
    latencies = [d["latency_ms"] for d in details]
    returned = sum(d["returned_count"] for d in details)
    provenance = sum(d["provenance_count"] for d in details)
    page_ranks = [d["page_rank"] for d in details]
    section_ranks = [d["section_rank"] for d in details]
    metrics = {
        "question_count": n,
        "k": k,
        "hit_at_1_pct": round(100 * sum(r == 1 for r in page_ranks) / n, 2),
        "hit_at_5_pct": round(100 * sum(0 < r <= k for r in page_ranks) / n, 2),
        "mrr_at_5": round(mean(1 / r if r else 0 for r in page_ranks), 4),
        "section_hit_at_5_pct": round(100 * sum(0 < r <= k for r in section_ranks) / n, 2),
        "section_mrr_at_5": round(mean(1 / r if r else 0 for r in section_ranks), 4),
        "avg_latency_ms": round(mean(latencies), 2),
        "p95_latency_ms": round(_percentile(latencies, 0.95), 2),
        "provenance_coverage_pct": round(100 * provenance / returned, 2) if returned else 0.0,
    }
    styles = sorted({d["style"] for d in details})
    metrics["by_style"] = {
        style: {
            "count": len(group),
            "hit_at_5_pct": round(100 * sum(0 < d["page_rank"] <= k for d in group) / len(group), 2),
            "mrr_at_5": round(mean(1 / d["page_rank"] if d["page_rank"] else 0 for d in group), 4),
        }
        for style in styles
        for group in [[d for d in details if d["style"] == style]]
    }
    return metrics
