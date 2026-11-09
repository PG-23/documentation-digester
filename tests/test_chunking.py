"""Tests for ingest/chunking.py.  Run:  python -m unittest tests.test_chunking -v

The tests use small sample pages written below, so they keep working
even when the files in data/docs change. Only the last class reads data/docs.
"""
import unittest
from pathlib import Path

from ingest.chunking import (
    CHUNK_SIZE,
    _clean_heading,
    _is_plain_heading,
    _is_underline_heading,
    _split_sections,
    _strip_header,
    chunk,
    semantic_chunker,
)

DOCS = Path(__file__).resolve().parent.parent / "data" / "docs"

# Old format: plain-text headings, first line is the page title.
PLAIN_PAGE = """Using signals

Signals let one node announce that something happened.

Connecting a signal in the editor

Select the node, open the Node dock and pick the signal.

Connecting a signal in code

Call connect on the signal and pass the function to run.
"""

# New format: TITLE/SOURCE/CATEGORY/CONTENT header and **bold** headings.
HEADER_PAGE = """TITLE: Overview of Godot's Key Concepts

SOURCE: https://docs.godotengine.org/en/stable/key_concepts_overview.html

CATEGORY: Getting started / Introduction

CONTENT:

Godot uses four core concepts.

**1. Nodes:**

Nodes are the basic building blocks.

**2. Scenes:**

A scene is a group of nodes.
"""

# What ingest.py passes after it removes the header itself.
STRIPPED_PAGE = HEADER_PAGE.split("CONTENT:", 1)[1].strip()

# A long section (well over CHUNK_SIZE) to force the length fallback.
PARA = "Signals let nodes talk to each other without tight coupling. " * 6
LONG_PAGE = "Big page\n\nLong part\n\n" + "\n\n".join([PARA] * 6)

META = {"title": "Using signals", "section": "Getting Started",
        "url": "https://example.com/signals.html", "source_file": "signals.txt"}


def headings_in(lines, check):
    return [l for i, l in enumerate(lines) if check(lines, i)]


class TestHeadingDetector(unittest.TestCase):
    def test_plain_headings(self):
        self.assertEqual(
            headings_in(PLAIN_PAGE.splitlines(), _is_plain_heading),
            ["Using signals", "Connecting a signal in the editor",
             "Connecting a signal in code"],
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

    def test_clean_heading(self):
        self.assertEqual(_clean_heading("**1. Nodes:**"), "1. Nodes")
        self.assertEqual(_clean_heading("**What Is a Game Engine?**"), "What Is a Game Engine?")
        self.assertEqual(_clean_heading("## Signals"), "Signals")
        self.assertEqual(_clean_heading("Using signals"), "Using signals")


class TestHeader(unittest.TestCase):
    def test_strip_header(self):
        title, content = _strip_header(HEADER_PAGE)
        self.assertEqual(title, "Overview of Godot's Key Concepts")
        self.assertNotIn("SOURCE:", content)
        self.assertNotIn("CONTENT:", content)
        self.assertTrue(content.strip().startswith("Godot uses four core concepts."))

    def test_page_without_header_is_unchanged(self):
        self.assertEqual(_strip_header(PLAIN_PAGE), ("", PLAIN_PAGE))


class TestSplitSections(unittest.TestCase):
    def test_plain_page(self):
        self.assertEqual([h for h, _ in _split_sections(PLAIN_PAGE)], [
            "Using signals",
            "Using signals > Connecting a signal in the editor",
            "Using signals > Connecting a signal in code",
        ])

    def test_header_page(self):
        self.assertEqual(_split_sections(HEADER_PAGE), [
            ("Overview of Godot's Key Concepts", "Godot uses four core concepts."),
            ("Overview of Godot's Key Concepts > 1. Nodes", "Nodes are the basic building blocks."),
            ("Overview of Godot's Key Concepts > 2. Scenes", "A scene is a group of nodes."),
        ])

    def test_stripped_page_headings_are_siblings_not_nested(self):
        # ingest.py removes the header, so there is no TITLE line.
        self.assertEqual([h for h, _ in _split_sections(STRIPPED_PAGE)],
                         ["", "1. Nodes", "2. Scenes"])

    def test_stripped_page_with_page_title(self):
        self.assertEqual(
            [h for h, _ in _split_sections(STRIPPED_PAGE, "Key Concepts")],
            ["Key Concepts", "Key Concepts > 1. Nodes", "Key Concepts > 2. Scenes"],
        )

    def test_page_title_repeated_in_text_is_not_nested(self):
        self.assertEqual(
            [h for h, _ in _split_sections(PLAIN_PAGE, "Using signals")][:2],
            ["Using signals", "Using signals > Connecting a signal in the editor"],
        )

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


class TestSemanticChunker(unittest.TestCase):
    def test_short_sections_one_chunk_each(self):
        chunks = semantic_chunker(PLAIN_PAGE)
        self.assertEqual(len(chunks), 3)
        self.assertTrue(chunks[2].startswith("Using signals > Connecting a signal in code\n\n"))

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
    def test_both_strategies_keep_metadata_and_number_chunks(self):
        for strategy in ["length", "semantic"]:
            with self.subTest(strategy=strategy):
                docs = chunk(PLAIN_PAGE, META, strategy)
                self.assertEqual([d.metadata["chunk_index"] for d in docs],
                                 list(range(len(docs))))
                for d in docs:
                    self.assertEqual(d.metadata["url"], META["url"])
                    self.assertEqual(d.metadata["source_file"], "signals.txt")
                    self.assertEqual(d.metadata["chunker"], strategy)
                    self.assertLessEqual(len(d.page_content), CHUNK_SIZE)

    def test_semantic_has_heading_metadata(self):
        docs = chunk(PLAIN_PAGE, META, "semantic")
        self.assertEqual(docs[2].metadata["heading"],
                         "Using signals > Connecting a signal in code")
        self.assertTrue(docs[2].page_content.startswith(docs[2].metadata["heading"]))

    def test_semantic_uses_metadata_title_for_stripped_text(self):
        meta = {**META, "title": "Key Concepts"}
        headings = [d.metadata["heading"] for d in chunk(STRIPPED_PAGE, meta, "semantic")]
        self.assertEqual(headings, ["Key Concepts", "Key Concepts > 1. Nodes",
                                    "Key Concepts > 2. Scenes"])

    def test_does_not_change_callers_metadata(self):
        before = dict(META)
        chunk(PLAIN_PAGE, META, "semantic")
        self.assertEqual(META, before)

    def test_chunk_size_is_passed_through(self):
        small = chunk(LONG_PAGE, META, "length", chunk_size=300, chunk_overlap=50)
        self.assertGreater(len(small), len(chunk(LONG_PAGE, META, "length")))

    def test_unknown_strategy_raises(self):
        with self.assertRaises(ValueError):
            chunk(PLAIN_PAGE, META, "magic")


class TestRealDocs(unittest.TestCase):
    """Runs on whatever is in data/docs right now."""

    def test_real_pages_chunk_cleanly(self):
        files = sorted(DOCS.glob("*.txt"))
        if not files:
            self.skipTest("no .txt files in data/docs")
        for f in files:
            with self.subTest(file=f.name):
                for c in semantic_chunker(f.read_text()):
                    self.assertLessEqual(len(c), CHUNK_SIZE)
                    for junk in ("TITLE:", "SOURCE:", "CATEGORY:", "CONTENT:"):
                        self.assertNotIn(junk, c)
                    self.assertNotIn("**", c.split("\n\n", 1)[0])   # heading line is clean


if __name__ == "__main__":
    unittest.main()
