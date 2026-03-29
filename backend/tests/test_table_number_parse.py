"""Tests for AS/NZS-style table caption parsing."""
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from services.table_pipeline import TablePipeline, _RawTable, _parse_table_number_from_text


class TestTableNumberParse(unittest.TestCase):
    def test_numeric_variants(self):
        for line, want in [
            ("Table 3.1 CABLE TYPES", "3.1"),
            ("TABLE 3 , 1 CABLE", "3.1"),
            ("Table 3. 1 CABLE", "3.1"),
            ("Table 3 ,1 TITLE", "3.1"),
            ("Table 104.101 VALUES", "104.101"),
            ("Table 104 , 101 X", "104.101"),
            ("Table 41 FOOTER", "41"),
        ]:
            with self.subTest(line=line):
                p = _parse_table_number_from_text(line)
                self.assertIsNotNone(p, line)
                self.assertEqual(p[0], want)

    def test_appendix(self):
        for line, want in [
            ("Table B1 CIRCUIT", "B1"),
            ("table c12 MAXIMUM", "C12"),
            ("Table D12(A) STEEL", "D12(A)"),
            ("Table D12 ( a ) X", "D12(A)"),
            ("Table H1 DEGREE", "H1"),
            ("Table N2 THIRD", "N2"),
        ]:
            with self.subTest(line=line):
                p = _parse_table_number_from_text(line)
                self.assertIsNotNone(p, line)
                self.assertEqual(p[0], want)

    def test_title_slice(self):
        line = "Table 3 , 1 CABLE TYPES AND"
        p = _parse_table_number_from_text(line)
        self.assertIsNotNone(p)
        _, _s, e = p
        self.assertTrue(line[e:].strip().startswith("CABLE"))

    def test_line_start_anchor(self):
        self.assertEqual(
            _parse_table_number_from_text("Table 3.1 METHODS", anchor="line_start")[0],
            "3.1",
        )
        self.assertIsNone(
            _parse_table_number_from_text("See Table 3.1 for details", anchor="line_start")
        )
        self.assertIsNone(
            _parse_table_number_from_text(
                "  Subject to Clause 3.11 and Table 3.1", anchor="line_start"
            )
        )
        self.assertEqual(
            _parse_table_number_from_text(" Table B1 X", anchor="line_start")[0],
            "B1",
        )

    def test_caption_anchor_word_lines(self):
        p = TablePipeline()
        words = [
            {"text": "TABLE", "x0": 50, "x1": 92, "top": 100, "bottom": 112},
            {"text": "3.2", "x0": 95, "x1": 118, "top": 100, "bottom": 112},
            {"text": "CABLE", "x0": 122, "x1": 180, "top": 100, "bottom": 112},
        ]
        anchors = p._discover_caption_anchors_from_page_words(words, 400.0, 800.0)
        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].table_number, "3.2")

    def test_adjacent_page_body_continuation_merge_gate(self):
        p = TablePipeline()
        p._diag = {"duplicate_headers_removed": 0, "continuation_body_merges": 0}
        prev = _RawTable(
            page_start=5,
            page_end=5,
            bbox=(0.0, 0.0, 400.0, 200.0),
            rows=[["Col1", "Col2"], ["a", "b"]],
            table_number="3.1",
            title="Demo",
            source_method="pdfplumber",
        )
        nxt_ok = _RawTable(
            page_start=6,
            page_end=6,
            bbox=(0.0, 0.0, 400.0, 200.0),
            rows=[["c", "d"], ["e", "f"]],
            table_number=None,
            title=None,
            source_method="pdfplumber",
        )
        self.assertTrue(p._merge_adjacent_body_only_continuation(prev, nxt_ok))
        nxt_bad_page = _RawTable(
            page_start=7,
            page_end=7,
            bbox=(0.0, 0.0, 400.0, 200.0),
            rows=[["c", "d"]],
            table_number=None,
            title=None,
            source_method="pdfplumber",
        )
        self.assertFalse(p._merge_adjacent_body_only_continuation(prev, nxt_bad_page))


if __name__ == "__main__":
    unittest.main()
