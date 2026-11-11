"""Offline lexical evaluation regression tests; only Python stdlib is needed."""
import unittest
from eval.offline_diagnostic import BM25, make_chunks, tokenize, windows, source_sections, evaluate
from eval.run_evaluation import load_questions


class TestOfflineDiagnostic(unittest.TestCase):
    def test_windows_boundaries_and_overlap(self):
        text = "alpha beta gamma. " * 50
        chunks = windows(text, 300, 40)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 300 for c in chunks))

    def test_section_headings_are_found_in_actual_docs(self):
        from pathlib import Path
        from eval.run_evaluation import DOCS_DIR
        raw = (DOCS_DIR / "key_concepts_overview.txt").read_text()
        headings = [h for h, body in source_sections(raw.split("CONTENT:", 1)[-1])]
        self.assertIn("4. Signals", headings)

    def test_no_zero_overlap_false_hits(self):
        chunks = [
            {"source_file": "wrong.txt", "text": "green kettle bird"},
            {"source_file": "right.txt", "text": "plasma mountain octopus"},
        ]
        self.assertEqual(BM25(chunks).search("unicorn", k=5), [])
        self.assertEqual(BM25(chunks).search("plasma", k=5)[0]["source_file"], "right.txt")

    def test_all_data_sources_indexed_with_urls(self):
        for strategy in ("length", "semantic"):
            chunks = make_chunks(strategy, 500, 50)
            self.assertEqual(len({c["source_file"] for c in chunks}), 7)
            self.assertTrue(all(c["url"].startswith("https://") for c in chunks))
            self.assertTrue(any("4. Signals" in c.get("heading", "") for c in chunks)
                            if strategy == "semantic" else True)

    def test_real_question_set_is_scored_without_fake_results(self):
        questions, _ = load_questions()
        data, config = evaluate(questions, "semantic", 500, 50)
        self.assertEqual(len(data), 25)
        self.assertEqual(config["backend"], "bm25")
        self.assertTrue(config["not_semantic_model_baseline"])
        self.assertTrue(all(d["returned_count"] <= 5 for d in data))
        self.assertEqual(data[4]["id"], "q05")


if __name__ == "__main__":
    unittest.main()
