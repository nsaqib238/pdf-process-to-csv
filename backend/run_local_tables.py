"""
Extract tables from a local PDF and write tables.json (same pipeline as /api/process-pdf-tables).

Examples (from repo root; reference PDF lives in input/):
  python backend/run_local_tables.py "input/AS3000 2018.pdf"
  python backend/run_local_tables.py "input/AS3000 2018.pdf" --out-dir "input/as3000_tables_out"
  python backend/run_local_tables.py "input/AS3000 2018.pdf" --max-pages 200 --no-fusion

Env (optional): TABLE_PIPELINE_MAX_PAGES, ENABLE_TABLE_CAMELOT_TABULA=false,
  OMIT_UNNUMBERED_TABLE_FRAGMENTS=true (strict noise filter; default is false for recall),
  TABLE_PIPELINE_FUSION_TRIGGER_SCORE=0.82, TABLE_PIPELINE_ALWAYS_TRY_FUSION=true (slow).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from pathlib import Path


def main() -> None:
    backend_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(backend_dir))

    parser = argparse.ArgumentParser(description="Run tables-only extraction on a PDF file.")
    parser.add_argument(
        "pdf",
        type=Path,
        help="Path to PDF (e.g. ../inout/AS3000 2018.pdf)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (default: backend/outputs/<pdf_stem>/)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Process only the first N pages (overrides TABLE_PIPELINE_MAX_PAGES)",
    )
    parser.add_argument(
        "--no-fusion",
        action="store_true",
        help="Disable Camelot/Tabula fusion (faster; pdfplumber only)",
    )
    parser.add_argument(
        "--no-header-reconstruction",
        action="store_true",
        help="Skip post-process header reconstruction (TABLE_HEADER RECONSTRUCT.md)",
    )
    args = parser.parse_args()

    pdf_path = args.pdf.resolve()
    if not pdf_path.is_file():
        raise SystemExit(f"PDF not found: {pdf_path}")

    # Default: alongside the PDF (e.g. inout/AS3000 2018_tables_out/tables.json)
    default_out = pdf_path.parent / f"{pdf_path.stem}_tables_out"
    out_dir = (args.out_dir or default_out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    from config import settings

    if args.max_pages is not None:
        settings.table_pipeline_max_pages = max(1, int(args.max_pages))
    if args.no_fusion:
        settings.enable_table_camelot_tabula = False
    if args.no_header_reconstruction:
        settings.enable_header_reconstruction = False

    async def _run() -> None:
        from services.pdf_processor import PDFProcessor

        proc = PDFProcessor()
        job_id = str(uuid.uuid4())
        return await proc.process_pdf_tables_only(
            input_path=str(pdf_path),
            output_dir=str(out_dir),
            job_id=job_id,
        )

    asyncio.run(_run())
    tables_json = out_dir / "tables.json"
    print(f"Wrote {tables_json}")


if __name__ == "__main__":
    main()
