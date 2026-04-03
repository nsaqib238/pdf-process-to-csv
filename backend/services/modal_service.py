"""
Modal.com Complete Extraction Service
======================================
Handles both TABLES and CLAUSES extraction using Modal.com.

Modal extracts complete JSON structures, backend just validates and saves.
"""

import logging
import base64
import requests
from typing import Dict, Any, List
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)


class ModalService:
    """Service for complete PDF extraction using Modal.com (tables + clauses)"""

    def __init__(self):
        self.endpoint = settings.modal_endpoint
        self.timeout = settings.modal_timeout

        if not self.endpoint:
            logger.warning(
                "Modal endpoint not configured in .env (MODAL_ENDPOINT)"
            )

    def is_available(self) -> bool:
        """Check if Modal.com service is configured"""
        return bool(self.endpoint)

    def warmup(self) -> Dict[str, Any]:
        """
        Warmup Modal.com container (loads GPU models).
        Reduces processing time from 2-3 minutes to 30-45 seconds.

        Returns:
            {
                "status": "warm" or "error",
                "message": str,
                "model_loaded": bool,
                "warmup_time": float
            }
        """
        if not self.is_available():
            return {
                "status": "error",
                "message": "Modal.com endpoint not configured",
                "model_loaded": False
            }

        try:
            logger.info("🔥 Warming up Modal.com container...")
            
            warmup_url = self.endpoint.replace("/extract", "/warmup")
            response = requests.get(warmup_url, timeout=self.timeout)

            if response.status_code != 200:
                error_msg = f"Modal warmup returned status {response.status_code}"
                logger.error(error_msg)
                return {
                    "status": "error",
                    "message": error_msg,
                    "model_loaded": False
                }

            result = response.json()
            warmup_time = result.get("warmup_time", 0)
            
            logger.info(f"✅ Modal.com warmed up in {warmup_time:.2f}s")
            return result

        except Exception as e:
            error_msg = f"Modal warmup error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "status": "error",
                "message": error_msg,
                "model_loaded": False
            }

    def extract_complete(self, pdf_path: Path, filename: str = None) -> Dict[str, Any]:
        """
        Extract BOTH tables and clauses from PDF using Modal.com.

        Args:
            pdf_path: Path to PDF file
            filename: Optional filename for logging

        Returns:
            {
                "success": True,
                "tables": [...],  # Complete table data
                "clauses": [...],  # Complete clause data
                "table_count": 12,
                "clause_count": 245,
                "processing_time": 120.5,
                "cost_estimate": 0.35
            }

        Raises:
            Exception: If extraction fails
        """
        if not self.is_available():
            raise ValueError("Modal.com endpoint not configured")

        filename = filename or pdf_path.name

        try:
            logger.info(f"📡 Calling Modal.com for complete extraction: {filename}")

            # Read and encode PDF
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()

            pdf_size_mb = len(pdf_bytes) / 1024 / 1024
            logger.info(f"📦 PDF size: {pdf_size_mb:.1f}MB")

            pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")

            # Call Modal API (single endpoint for both tables and clauses)
            response = requests.post(
                self.endpoint,
                json={
                    "pdf_base64": pdf_base64,
                    "filename": filename
                },
                timeout=self.timeout
            )

            if response.status_code != 200:
                error_msg = f"Modal API returned status {response.status_code}: {response.text}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "tables": [],
                    "clauses": [],
                }

            result = response.json()

            if not result.get("success"):
                logger.error(f"Modal extraction failed: {result.get('error')}")
                return result

            # Log results
            table_count = result.get("table_count", 0)
            clause_count = result.get("clause_count", 0)
            processing_time = result.get("processing_time", 0)
            cost_estimate = result.get("cost_estimate", 0)

            logger.info(f"✅ Modal.com extracted {table_count} tables, {clause_count} clauses")
            logger.info(f"   Time: {processing_time:.2f}s | Cost: ${cost_estimate:.3f}")

            return result

        except requests.exceptions.Timeout:
            error_msg = f"Modal.com request timed out after {self.timeout}s"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "tables": [],
                "clauses": [],
            }

        except Exception as e:
            error_msg = f"Modal.com extraction error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "error": error_msg,
                "tables": [],
                "clauses": [],
            }

    def convert_tables_to_objects(self, modal_tables: List[Dict]) -> List[Dict]:
        """
        Convert Modal's table format to backend Table objects.
        Modal already provides complete data, just normalize format.

        Args:
            modal_tables: Tables from Modal.com

        Returns:
            List of table dicts ready for Table model
        """
        from models.table import TableRow

        pipeline_tables = []

        # Group tables by page
        tables_by_page = {}
        for table in modal_tables:
            page = table.get("page", 1)
            if page not in tables_by_page:
                tables_by_page[page] = []
            tables_by_page[page].append(table)

        # Convert to pipeline format
        for page, page_tables in sorted(tables_by_page.items()):
            for idx, table in enumerate(page_tables, 1):
                # Use Modal's table number or generate one
                table_number = table.get("table_number") or f"MODAL_P{page}_T{idx}"

                # Convert header_rows
                header_rows = []
                for row_cells in table.get("header_rows", []):
                    header_rows.append(TableRow(
                        cells=row_cells,
                        is_header=True
                    ))

                # Convert data_rows
                data_rows = []
                for row_cells in table.get("data_rows", []):
                    data_rows.append(TableRow(
                        cells=row_cells,
                        is_header=False
                    ))

                # Build normalized text
                normalized_text = self._build_normalized_text(
                    table_number,
                    table.get("title"),
                    header_rows,
                    data_rows
                )

                pipeline_table = {
                    "table_number": table_number,
                    "title": table.get("title"),
                    "page_start": page,
                    "page_end": page,
                    "detection_method": "modal_complete",
                    "confidence": table.get("confidence", 0.0),
                    "bbox": table.get("bbox", {}),
                    "header_rows": header_rows,
                    "data_rows": data_rows,
                    "has_merged_cells": table.get("has_merged_cells", False),
                    "normalized_text_representation": normalized_text,
                    "source_method": "modal_table_transformer_structure",
                    "metadata": {
                        "model": "microsoft/table-transformer-structure-recognition",
                        "row_count": table.get("row_count", 0),
                        "column_count": table.get("column_count", 0),
                        "extraction_method": table.get("extraction_method", "modal_complete"),
                    }
                }
                pipeline_tables.append(pipeline_table)

        logger.info(f"✅ Converted {len(pipeline_tables)} Modal tables to pipeline format")
        return pipeline_tables

    def _build_normalized_text(
        self, 
        table_number: str, 
        title: str,
        header_rows: List,
        data_rows: List
    ) -> str:
        """Build normalized text representation from table data."""
        lines = []

        if table_number:
            lines.append(f"TABLE {table_number}")

        if title:
            lines.append(f"TITLE: {title}")

        # Add headers
        if header_rows:
            header_cells = header_rows[0].cells if hasattr(header_rows[0], 'cells') else header_rows[0]
            lines.append("COLUMNS: " + " | ".join(str(c) for c in header_cells))

        # Add data rows
        for i, row in enumerate(data_rows, start=1):
            cells = row.cells if hasattr(row, 'cells') else row
            lines.append(f"ROW {i}: " + " | ".join(str(c) for c in cells))

        return "\n".join(lines).strip()

    def convert_clauses_to_objects(self, modal_clauses: List[Dict]) -> List[Dict]:
        """
        Convert Modal's clause format to backend Clause objects.
        Modal already provides complete structured data, just normalize.

        Args:
            modal_clauses: Clauses from Modal.com

        Returns:
            List of clause dicts ready for Clause model
        """
        from models.clause import Note, Exception as ClauseException

        logger.info(f"Converting {len(modal_clauses)} Modal clauses to pipeline format")

        # Modal already provides complete clause data with hierarchy
        # Just ensure format matches backend models
        for clause in modal_clauses:
            # Convert notes to Note objects
            notes = clause.get("notes", [])
            if notes and isinstance(notes[0], dict):
                # Already in correct format
                pass
            else:
                # Convert string notes to dict format
                clause["notes"] = [
                    {"text": note, "type": "NOTE"} 
                    for note in notes if note
                ]

            # Convert exceptions to Exception objects
            exceptions = clause.get("exceptions", [])
            if exceptions and isinstance(exceptions[0], dict):
                # Already in correct format
                pass
            else:
                # Convert string exceptions to dict format
                clause["exceptions"] = [
                    {"text": exc, "type": "Exception"} 
                    for exc in exceptions if exc
                ]

        logger.info(f"✅ Converted {len(modal_clauses)} Modal clauses to pipeline format")
        return modal_clauses
