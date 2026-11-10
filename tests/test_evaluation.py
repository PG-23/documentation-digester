"""Evaluation correctness tests. Works without LangChain/Chroma/model downloads."""
import json
import tempfile
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from eval.metrics import score_question, summarize
from eval.run_evaluation import (evaluate_api, load_questions, make_report, save_report,
                                 fetch_api_results)
from eval.plot_results import plot_reports


Q = {"id": "q00", "question": "How do signals work?", "style": "paraphrase",
     "expected_source_file": "key_concepts_overview.txt", "expected_heading": "4. Signals"}


def result(file="key_concepts_overview.txt", heading="", text="Some content", url="https://docs.example.org"):
    return {"source_file": file, "title": "Overview", "url": url,
            "heading": heading, "text": text, "chunk_index": 1, "score": 0.85}


class TestMetrics(unittest.TestCase):
    def test_page_ranks_are_one_based_and_reciprocal(self):
        s = score_question(Q, [result("wrong.txt"), result("key_concepts_overview.txt")])
        self.assertEqual(s["page_rank"], 2)
        self.assertEqual(s["reciprocal_rank"], 0.5)
        self.assertEqual(s["section_rank"], 0)

    def test_heading_and_file_must_both_match(self):
        s = score_question(Q, [result("wrong.txt", "Overview > 4. Signals"),
                               result("key_concepts_overview.txt", "Overview > 4. Signals")])
        self.assertEqual(s["page_rank"], 2)
        self.assertEqual(s["section_rank"], 2)

    def test_original_bold_heading_in_text_is_evidence(self):
        s = score_question(Q, [result(text="**4. Signals:**\n\nConnect nodes via signals.")])
        self.assertEqual(s["section_rank"], 1)

    def test_heading_mentioned_mid_sentence_is_not_evidence(self):
        s = score_question(Q, [result(text="Read 4. Signals to learn more.")])
        self.assertEqual(s["section_rank"], 0)

    def test_missing_results_do_not_get_credit(self):
        s = score_question(Q, [])
        self.assertEqual((s["page_rank"], s["section_rank"], s["provenance_count"]), (0, 0, 0))

    def test_nested_metadata_is_supported(self):
        s = score_question(Q, [{"text": "4. Signals\nEvent dispatch", "metadata": {
            "source_file": "key_concepts_overview.txt", "url": "https://x", "title": "X"}}])
        self.assertEqual(s["page_rank"], 1)
        self.assertEqual(s["section_rank"], 1)
        self.assertEqual(s["provenance_count"], 1)

    def test_mrr_hit_latency_and_provenance(self):
        a = score_question(Q, [result(heading="4. Signals")]); a["latency_ms"] = 10
        b = score_question({**Q, "id": "q01"}, [result("wrong.txt"), result(heading="4. Signals")]); b["latency_ms"] = 30
        c = score_question({**Q, "id": "q02"}, [result("wrong.txt", url="")]); c["latency_ms"] = 20
        s = summarize([a, b, c])
        self.assertAlmostEqual(s["hit_at_1_pct"], 33.33, places=2)
        self.assertAlmostEqual(s["hit_at_5_pct"], 66.67, places=2)
        self.assertAlmostEqual(s["mrr_at_5"], 0.5)
        self.assertEqual(s["avg_latency_ms"], 20)
        self.assertEqual(s["p95_latency_ms"], 30)
        self.assertEqual(s["provenance_coverage_pct"], 75)

    def test_topk_cutoff(self):
        s = score_question(Q, [result("wrong.txt"), result(heading="4. Signals")], k=1)
        self.assertEqual(s["page_rank"], 0)
        self.assertEqual(s["returned_count"], 1)

    def test_cannot_summarize_empty_dataset(self):
        with self.assertRaises(ValueError):
            summarize([])


class TestRunner(unittest.TestCase):
    def test_all_real_question_labels_exist(self):
        questions, digest = load_questions()
        self.assertEqual(len(questions), 25)
        self.assertEqual(len(digest), 64)
        self.assertTrue(any(q["expected_heading"] == "4. Signals" for q in questions[:10]))
        self.assertEqual(len({q["id"] for q in questions}), len(questions))

    def test_evaluate_api_measures_all_queries_but_skips_warmup(self):
        with patch("eval.run_evaluation.fetch_api_results", side_effect=[
            ([result(heading="4. Signals")], 999),
            ([result(heading="4. Signals")], 12.5),
        ]) as mocked:
            rows, conf = evaluate_api([Q], k=5, warmup=1)
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(rows[0]["latency_ms"], 12.5)
        self.assertEqual(conf["backend"], "api")

    def test_real_http_fetch_of_search_contract(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                route = urlparse(self.path)
                params = parse_qs(route.query)
                if route.path != "/search" or params.get("k") != ["5"]:
                    self.send_error(400)
                    return
                payload = json.dumps({"results": [result(heading="4. Signals")]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            rows, elapsed = fetch_api_results(f"http://127.0.0.1:{server.server_port}", "Do signals work?", 5, 5)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_file"], Q["expected_source_file"])
            self.assertGreaterEqual(elapsed, 0)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_report_can_be_serialized_and_charted(self):
        s = score_question(Q, [result(heading="4. Signals")]); s["latency_ms"] = 25
        report = make_report("a" * 64, [s], {"backend": "api"}, "baseline")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.json"
            chart = Path(folder) / "chart.png"
            save_report(report, path)
            self.assertEqual(json.loads(path.read_text())["metrics"]["hit_at_5_pct"], 100)
            self.assertEqual(report["metrics"]["canonical_url_match_pct"], 0.0)
            plot_reports([report], chart)
            self.assertGreater(chart.stat().st_size, 1000)

    def test_chart_can_show_multiple_local_experiments(self):
        one = score_question(Q, [result(heading="4. Signals")]); one["latency_ms"] = 12
        reports = []
        for i, (strategy, size) in enumerate((("length", 500), ("length", 800),
                                               ("semantic", 500), ("semantic", 800))):
            reports.append(make_report("a" * 64, [one],
                {"backend": "local", "strategy": strategy, "chunk_size": size},
                f"{strategy}-{size}"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "experiments.png"
            plot_reports(reports, path)
            self.assertGreater(path.stat().st_size, 1000)

    def test_cannot_compare_unmatched_question_sets(self):
        s = score_question(Q, [result(heading="4. Signals")]); s["latency_ms"] = 12
        a = make_report("a" * 64, [s], {"backend": "api"}, "baseline")
        b = make_report("b" * 64, [s], {"backend": "api"}, "improved")
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                plot_reports([a, b], Path(folder) / "chart.png")


if __name__ == "__main__":
    unittest.main()
