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
        Uses separate endpoints to avoid HTTP response size limits.

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
            logger.info(f"   Using split endpoints to avoid response size limits")

            # Read and encode PDF
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()

            pdf_size_mb = len(pdf_bytes) / 1024 / 1024
            logger.info(f"📦 PDF size: {pdf_size_mb:.1f}MB")

            pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")

            # STEP 1: Extract tables (separate endpoint)
            logger.info("📊 Step 1: Extracting tables...")
            tables_endpoint = self.endpoint.replace("/extract", "/extract-tables")
            tables_response = requests.post(
                tables_endpoint,
                json={
                    "pdf_base64": pdf_base64,
                    "filename": filename
                },
                timeout=self.timeout
            )

            if tables_response.status_code != 200:
                error_msg = f"Modal tables API returned status {tables_response.status_code}: {tables_response.text}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "tables": [],
                    "clauses": [],
                }

            tables_result = tables_response.json()
            
            if not tables_result.get("success"):
                logger.error(f"Modal table extraction failed: {tables_result.get('error')}")
                return {
                    "success": False,
                    "error": tables_result.get("error"),
                    "tables": [],
                    "clauses": [],
                }

            tables = tables_result.get("tables", [])
            table_count = tables_result.get("table_count", 0)
            tables_time = tables_result.get("processing_time", 0)
            tables_cost = tables_result.get("cost_estimate", 0)

            logger.info(f"✅ Tables extracted: {table_count} tables in {tables_time:.2f}s (${tables_cost:.4f})")

            # STEP 2: Extract clauses (separate endpoint)
            logger.info("📝 Step 2: Extracting clauses...")
            clauses_endpoint = self.endpoint.replace("/extract", "/extract-clauses")
            clauses_response = requests.post(
                clauses_endpoint,
                json={
                    "pdf_base64": pdf_base64,
                    "filename": filename
                },
                timeout=self.timeout  # Clauses are fast (~30s), but use same timeout for consistency
            )

            if clauses_response.status_code != 200:
                error_msg = f"Modal clauses API returned status {clauses_response.status_code}: {clauses_response.text}"
                logger.error(error_msg)
                # Tables succeeded but clauses failed - still return tables
                return {
                    "success": True,  # Partial success
                    "error": f"Clauses extraction failed: {error_msg}",
                    "tables": tables,
                    "clauses": [],
                    "table_count": table_count,
                    "clause_count": 0,
                    "processing_time": tables_time,
                    "cost_estimate": tables_cost,
                }

            clauses_result = clauses_response.json()

            if not clauses_result.get("success"):
                logger.error(f"Modal clause extraction failed: {clauses_result.get('error')}")
                # Tables succeeded but clauses failed - still return tables
                return {
                    "success": True,  # Partial success
                    "error": f"Clauses extraction failed: {clauses_result.get('error')}",
                    "tables": tables,
                    "clauses": [],
                    "table_count": table_count,
                    "clause_count": 0,
                    "processing_time": tables_time,
                    "cost_estimate": tables_cost,
                }

            clauses = clauses_result.get("clauses", [])
            clause_count = clauses_result.get("clause_count", 0)
            clauses_time = clauses_result.get("processing_time", 0)

            total_time = tables_time + clauses_time
            total_cost = tables_cost  # Clauses are rule-based, no cost

            logger.info(f"✅ Clauses extracted: {clause_count} clauses in {clauses_time:.2f}s")
            logger.info(f"✅ Modal.com complete: {table_count} tables, {clause_count} clauses")
            logger.info(f"   Total time: {total_time:.2f}s | Total cost: ${total_cost:.4f}")

            return {
                "success": True,
                "tables": tables,
                "clauses": clauses,
                "table_count": table_count,
                "clause_count": clause_count,
                "processing_time": total_time,
                "cost_estimate": total_cost,
            }

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
