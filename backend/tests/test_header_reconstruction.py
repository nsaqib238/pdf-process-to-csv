"""Tests for header_reconstruction post-processing."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from models.table import Table, TableRow
from services.header_reconstructor import (
    apply_reconstruction_to_tables,
    reconstruct_headers,
)
from services.output_generator import OutputGenerator


class TestHeaderReconstruction(unittest.TestCase):
    def test_promotes_repeated_header_row(self):
        t = Table(
            table_id="t1",
            page_start=1,
            page_end=1,
            header_rows=[TableRow(cells=["Type", "Rating"], is_header=True)],
            data_rows=[
                TableRow(cells=["Type", "Rating"], is_header=False),
                TableRow(cells=["X", "100"], is_header=False),
            ],
            normalized_text_representation="",
        )
        out = apply_reconstruction_to_tables([t])[0]
        self.assertEqual(len(out.data_rows), 1)
        self.assertTrue(out.promoted_header_rows)
        self.assertEqual(len(out.promoted_header_rows), 1)
        self.assertEqual(out.data_rows[0].cells, ["X", "100"])
        self.assertTrue(out.final_columns)
        self.assertIn("COLUMNS:", out.normalized_text_representation)

    def test_reconstruct_headers_dict_idempotent_shape(self):
        d = {
            "table_id": "x",
            "page_start": 1,
            "page_end": 1,
            "header_rows": [{"cells": ["A", "B"], "is_header": True}],
            "data_rows": [{"cells": ["1", "2"], "is_header": False}],
            "normalized_text_representation": "",
            "confidence": "medium",
            "footer_notes": [],
            "extraction_notes": [],
            "has_headers": True,
            "is_multipage": False,
            "has_merged_cells": False,
        }
        r = reconstruct_headers(d)
        self.assertIn("final_columns", r)
        self.assertEqual(len(r["final_columns"]), 2)
        self.assertIn("reconstruction_confidence", r)

    def test_tables_json_includes_final_columns_after_reconstruction(self):
        t = Table(
            table_id="t3",
            page_start=1,
            page_end=1,
            header_rows=[TableRow(cells=["Col A", "Col B"], is_header=True)],
            data_rows=[TableRow(cells=["x", "y"], is_header=False)],
            normalized_text_representation="",
        )
        rec = apply_reconstruction_to_tables([t])[0]
        path = Path(tempfile.gettempdir()) / "tables_header_test_rec.json"
        OutputGenerator().generate_tables_json([rec], str(path))
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("final_columns", data[0])
        self.assertEqual(len(data[0]["final_columns"]), 2)
        path.unlink(missing_ok=True)

    def test_tables_json_omits_null_reconstruction_fields(self):
        t = Table(
            table_id="t2",
            page_start=1,
            page_end=1,
            header_rows=[TableRow(cells=["C1"], is_header=True)],
            data_rows=[TableRow(cells=["v"], is_header=False)],
            normalized_text_representation="",
        )
        path = Path(tempfile.gettempdir()) / "tables_header_test.json"
        OutputGenerator().generate_tables_json([t], str(path))
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(data), 1)
        self.assertNotIn("final_columns", data[0])
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
