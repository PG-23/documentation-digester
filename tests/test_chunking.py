"""Tests for ingest/chunking.py.  Run:  python -m unittest tests.test_chunking -v"""
import json
import unittest
from pathlib import Path

from ingest.chunking import (
    CHUNK_SIZE,
    _is_plain_heading,
    _is_underline_heading,
    _split_sections,
    _strip_header,
    _clean_heading,
    chunk,
    semantic_chunker,
)

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "data" / "docs"
MANIFEST = json.loads((ROOT / "data" / "manifest.json").read_text())

# A long section (well over CHUNK_SIZE) to force the length fallback.
PARA = "Signals let nodes talk to each other without tight coupling. " * 6
LONG_PAGE = "Big page\n\nLong part\n\n" + "\n\n".join([PARA] * 6)


def headings_in(lines, check):
    return [l for i, l in enumerate(lines) if check(lines, i)]


class TestHeadingDetector(unittest.TestCase):
    def test_plain_headings_in_real_page(self):
        lines = (DOCS / "signals.txt").read_text().splitlines()
        self.assertEqual(
            headings_in(lines, _is_plain_heading),
            ["Using signals", "Connecting a signal in the editor",
             "Connecting a signal in code", "Defining custom signals",
             "Why use signals"],
        )

    def test_sentence_and_bullet_and_code_are_not_headings(self):
        lines = ["", "This is a sentence.", "", "- a bullet item", "",
                 "button.pressed.connect(f)", "", "Real heading", ""]
        self.assertEqual(headings_in(lines, _is_plain_heading), ["Real heading"])

    def test_underline_headings(self):
        lines = ["Using signals", "*************", "", "Some text.", "",
                 "=====  =====", "    code line", "    ---------",
                 "In code", "======="]
        self.assertEqual(headings_in(lines, _is_underline_heading),
                         ["Using signals", "In code"])


class TestSplitSections(unittest.TestCase):
    def test_plain_heading_paths(self):
        sections = _split_sections((DOCS / "signals.txt").read_text())
        self.assertEqual(len(sections), 5)
        self.assertEqual(sections[0][0], "Using signals")
        self.assertEqual(sections[2][0], "Using signals > Connecting a signal in code")

    def test_underline_levels_go_back_up(self):
        rst = ("Signals\n=======\n\nIntro.\n\nIn code\n-------\n\nCode.\n\n"
               "Advanced\n~~~~~~~~\n\nDeep.\n\nCustom\n------\n\nCustom text.\n")
        self.assertEqual(
            [h for h, _ in _split_sections(rst)],
            ["Signals", "Signals > In code", "Signals > In code > Advanced",
             "Signals > Custom"],
        )

    def test_heading_with_no_body_is_skipped(self):
        page = "Page\n\nEmpty part\n\nFilled part\n\nBody text."
        self.assertEqual(_split_sections(page), [("Page > Filled part", "Body text.")])

HEADER_PAGE = """TITLE: Overview of Godot's Key Concepts

SOURCE: https://docs.godotengine.org/en/stable/key_concepts_overview.html

CATEGORY: Getting started / Introduction

CONTENT:

Godot uses four core concepts.

**1. Nodes:**

Nodes are the basic building blocks.
"""


class TestHeaderFormat(unittest.TestCase):
    def test_strip_header(self):
        title, content = _strip_header(HEADER_PAGE)
        self.assertEqual(title, "Overview of Godot's Key Concepts")
        self.assertNotIn("SOURCE:", content)
        self.assertNotIn("CONTENT:", content)
        self.assertTrue(content.strip().startswith("Godot uses four core concepts."))

    def test_page_without_header_is_unchanged(self):
        text = (DOCS / "signals.txt").read_text()
        self.assertEqual(_strip_header(text), ("", text))

    def test_clean_heading(self):
        self.assertEqual(_clean_heading("**1. Nodes:**"), "1. Nodes")
        self.assertEqual(_clean_heading("**What Is a Game Engine?**"), "What Is a Game Engine?")
        self.assertEqual(_clean_heading("## Signals"), "Signals")
        self.assertEqual(_clean_heading("Using signals"), "Using signals")

    def test_header_page_sections(self):
        self.assertEqual(_split_sections(HEADER_PAGE), [
            ("Overview of Godot's Key Concepts", "Godot uses four core concepts."),
            ("Overview of Godot's Key Concepts > 1. Nodes", "Nodes are the basic building blocks."),
        ])

    def test_no_header_or_markdown_leaks_into_real_chunks(self):
        for f in DOCS.glob("*.txt"):
            with self.subTest(file=f.name):
                for c in semantic_chunker(f.read_text()):
                    for junk in ("TITLE:", "SOURCE:", "CATEGORY:", "CONTENT:"):
                        self.assertNotIn(junk, c)
                    self.assertNotIn("**", c.split("\n\n", 1)[0])




class TestSemanticChunker(unittest.TestCase):
    def test_real_pages_chunks_fit_and_start_with_heading(self):
        for f in DOCS.glob("*.txt"):
            with self.subTest(file=f.name):
                text = f.read_text()
                headings = {h for h, _ in _split_sections(text)}
                for c in semantic_chunker(text):
                    self.assertLessEqual(len(c), CHUNK_SIZE)
                    self.assertIn(c.split("\n\n", 1)[0], headings)

    

    def test_long_section_is_split_and_keeps_heading(self):
        chunks = semantic_chunker(LONG_PAGE)
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(len(c), CHUNK_SIZE)
            self.assertTrue(c.startswith("Big page > Long part\n\n"))

    def test_page_without_headings_still_chunks(self):
        self.assertEqual(semantic_chunker("Just one sentence of plain text."),
                         ["Just one sentence of plain text."])


class TestChunkEntryPoint(unittest.TestCase):
    def setUp(self):
        self.text = (DOCS / "signals.txt").read_text()
        self.meta = {**MANIFEST["signals.txt"], "source_file": "signals.txt"}

    def test_both_strategies_keep_metadata_and_number_chunks(self):
        for strategy in ["length", "semantic"]:
            with self.subTest(strategy=strategy):
                docs = chunk(self.text, self.meta, strategy)
                self.assertEqual([d.metadata["chunk_index"] for d in docs],
                                 list(range(len(docs))))
                for d in docs:
                    self.assertEqual(d.metadata["url"], self.meta["url"])
                    self.assertEqual(d.metadata["source_file"], "signals.txt")
                    self.assertEqual(d.metadata["chunker"], strategy)
                    self.assertLessEqual(len(d.page_content), CHUNK_SIZE)

    def test_semantic_has_heading_metadata(self):
        docs = chunk(self.text, self.meta, "semantic")
        self.assertEqual(docs[2].metadata["heading"],
                         "Using signals > Connecting a signal in code")
        self.assertTrue(docs[2].page_content.startswith(docs[2].metadata["heading"]))

    def test_does_not_change_callers_metadata(self):
        before = dict(self.meta)
        chunk(self.text, self.meta, "semantic")
        self.assertEqual(self.meta, before)

    def test_chunk_size_is_passed_through(self):
        small = chunk(self.text, self.meta, "length", chunk_size=300, chunk_overlap=50)
        self.assertGreater(len(small), len(chunk(self.text, self.meta, "length")))

    def test_unknown_strategy_raises(self):
        with self.assertRaises(ValueError):
            chunk(self.text, self.meta, "magic")


if __name__ == "__main__":
    unittest.main()
