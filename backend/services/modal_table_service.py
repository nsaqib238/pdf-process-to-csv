"""
Modal.com Table Extraction Service

Provides table detection using Microsoft Table Transformer on
Modal.com's serverless GPU platform.
99.93% cost savings vs OpenAI ($0.006/doc vs $8-10/doc).
"""

import logging
import base64
import requests
from typing import List, Dict, Any
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)


class ModalTableService:
    """Service for extracting tables using Modal.com"""

    def __init__(self):
        self.endpoint = settings.modal_endpoint
        self.timeout = settings.modal_timeout
        self.confidence_threshold = settings.modal_confidence_threshold

        if not self.endpoint:
            logger.warning(
                "Modal endpoint not configured in .env "
                "(MODAL_ENDPOINT)"
            )

    def is_available(self) -> bool:
        """Check if Modal.com service is configured and available"""
        return bool(self.endpoint)

    def warmup(self) -> Dict[str, Any]:
        """
        Warmup Modal.com container before processing PDFs.
        This initializes the container and loads the model,
        reducing subsequent processing time from 2-3 minutes to 30-45 seconds.

        Returns:
            Dict with:
                - status: "warm" or "error"
                - message: Status message
                - model_loaded: bool
                - warmup_time: float (seconds)
                - timestamp: float (unix timestamp)

        Example:
            >>> result = modal_service.warmup()
            >>> if result["status"] == "warm":
            >>>     # Container is ready, proceed with PDF upload
            >>>     pass
        """
        if not self.is_available():
            return {
                "status": "error",
                "message": "Modal.com endpoint not configured",
                "model_loaded": False
            }

        try:
            logger.info("🔥 Warming up Modal.com container...")
            
            # Call the warmup endpoint (GET /warmup)
            warmup_url = self.endpoint.replace("/extract", "/warmup")
            
            response = requests.get(
                warmup_url,
                timeout=self.timeout  # Allow full timeout for cold start
            )

            if response.status_code != 200:
                error_msg = (
                    f"Modal warmup returned status {response.status_code}: "
                    f"{response.text}"
                )
                logger.error(error_msg)
                return {
                    "status": "error",
                    "message": error_msg,
                    "model_loaded": False
                }

            result = response.json()
            warmup_time = result.get("warmup_time", 0)
            
            logger.info(
                f"✅ Modal.com container warmed up in {warmup_time:.2f}s"
            )
            logger.info("🚀 Ready for fast PDF processing (30-45s per doc)")

            return result

        except requests.exceptions.Timeout:
            # Even if timeout, container might be warming up
            logger.warning(
                f"Modal warmup timed out after {self.timeout}s, "
                f"but container may still be initializing"
            )
            return {
                "status": "warming",
                "message": f"Warmup in progress (timeout after {self.timeout}s)",
                "model_loaded": False,
                "note": "Container may still be initializing, retry in 30s"
            }

        except Exception as e:
            error_msg = f"Modal warmup error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "status": "error",
                "message": error_msg,
                "model_loaded": False
            }

    def extract_tables(self, pdf_path: Path, filename: str = None) -> Dict[str, Any]:
        """
        Extract tables from PDF using Modal.com Table Transformer.

        Args:
            pdf_path: Path to PDF file
            filename: Optional filename for logging

        Returns:
            Dict with:
                - success: bool
                - tables: List of detected tables with bounding boxes
                - table_count: int
                - pages_processed: int
                - processing_time: float (seconds)
                - model_info: Dict with model details
                - error: str (if failed)

        Raises:
            Exception: If extraction fails and no fallback configured
        """
        if not self.is_available():
            raise ValueError("Modal.com endpoint not configured")

        filename = filename or pdf_path.name

        try:
            logger.info(
                f"📡 Calling Modal.com for table extraction: {filename}"
            )

            # Read and encode PDF
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()

            pdf_size_mb = len(pdf_bytes) / 1024 / 1024
            logger.info(f"📦 PDF size: {pdf_size_mb:.1f}MB")

            pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")

            # Call Modal API
            response = requests.post(
                self.endpoint,
                json={
                    "pdf_base64": pdf_base64,
                    "filename": filename
                },
                timeout=self.timeout
            )

            if response.status_code != 200:
                error_msg = (
                    f"Modal API returned status {response.status_code}: "
                    f"{response.text}"
                )
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "tables": [],
                    "table_count": 0
                }

            result = response.json()

            if not result.get("success"):
                logger.error(
                    f"Modal extraction failed: {result.get('error')}"
                )
                return result

            # Log results
            table_count = result.get("table_count", 0)
            processing_time = result.get("processing_time", 0)
            pages_processed = result.get("pages_processed", 0)

            logger.info(
                f"✅ Modal.com extracted {table_count} tables in "
                f"{processing_time:.2f}s"
            )
            logger.info(f"📄 Processed {pages_processed} pages")

            # Calculate cost estimate
            cost_estimate = (
                (processing_time / 3600) * 0.43
            )  # T4 GPU $0.43/hour
            logger.info(f"💰 Estimated cost: ${cost_estimate:.4f}")

            # Filter by confidence threshold
            tables = result.get("tables", [])
            high_confidence_count = sum(
                1 for t in tables
                if t.get("confidence", 0) >= self.confidence_threshold
            )
            low_confidence_count = table_count - high_confidence_count

            if low_confidence_count > 0:
                logger.warning(
                    f"⚠️  {low_confidence_count} tables below "
                    f"confidence threshold ({self.confidence_threshold})"
                )

            result["cost_estimate"] = cost_estimate
            result["high_confidence_count"] = high_confidence_count
            result["low_confidence_count"] = low_confidence_count

            return result

        except requests.exceptions.Timeout:
            error_msg = f"Modal.com request timed out after {self.timeout}s"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "tables": [],
                "table_count": 0
            }

        except Exception as e:
            error_msg = f"Modal.com extraction error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "error": error_msg,
                "tables": [],
                "table_count": 0
            }

    def convert_to_pipeline_format(self, modal_tables: List[Dict]) -> List[Dict]:
        """
        Convert Modal.com table format to pipeline table format.
        
        NEW: Modal now returns COMPLETE table data including:
        - table_number and title (from caption extraction)
        - header_rows and data_rows (from structure recognition + OCR)
        - row_count and column_count (from structure analysis)
        
        Modal format (new structure extraction):
        {
            "page": 12,
            "table_number": "3.1",
            "title": "Installation methods",
            "confidence": 0.95,
            "bbox": {"x0": 100, "y0": 200, "x1": 500, "y1": 400},
            "header_rows": [["Type", "Rating", "Application"]],
            "data_rows": [["Type A", "10A", "Indoor"], ...],
            "row_count": 10,
            "column_count": 3,
            "has_merged_cells": true,
            "extraction_method": "table_transformer_structure"
        }

        Pipeline format:
        {
            "table_number": "3.1",  # From Modal caption extraction
            "title": "Installation methods",
            "page": 12,
            "detection_method": "modal_table_transformer_structure",
            "confidence": 0.95,
            "bbox": {...},
            "header_rows": [...],  # Complete data from Modal
            "data_rows": [...],
            "has_merged_cells": true,
            "metadata": {...}
        }

        Args:
            modal_tables: List of tables from Modal.com (with complete data)

        Returns:
            List of tables in pipeline format (ready to use, no pdfplumber needed)
        """
        from models.table import TableRow
        
        pipeline_tables = []

        # Group tables by page for fallback numbering
        tables_by_page = {}
        for table in modal_tables:
            page = table.get("page", 0)
            if page not in tables_by_page:
                tables_by_page[page] = []
            tables_by_page[page].append(table)

        # Convert to pipeline format
        for page, page_tables in sorted(tables_by_page.items()):
            for idx, table in enumerate(page_tables, 1):
                # Use Modal's table number if available, otherwise generate
                table_number = table.get("table_number") or f"MODAL_P{page}_T{idx}"
                
                # Convert header_rows to TableRow objects
                header_rows = []
                for row_cells in table.get("header_rows", []):
                    header_rows.append(TableRow(
                        cells=row_cells,
                        is_header=True
                    ))
                
                # Convert data_rows to TableRow objects
                data_rows = []
                for row_cells in table.get("data_rows", []):
                    data_rows.append(TableRow(
                        cells=row_cells,
                        is_header=False
                    ))
                
                # Build normalized text representation
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
                    "detection_method": table.get(
                        "extraction_method", 
                        "modal_table_transformer_structure"
                    ),
                    "confidence": table.get("confidence", 0.0),
                    "bbox": table.get("bbox", {}),
                    "header_rows": header_rows,
                    "data_rows": data_rows,
                    "has_merged_cells": table.get("has_merged_cells", False),
                    "normalized_text_representation": normalized_text,
                    "source_method": table.get(
                        "extraction_method",
                        "modal_table_transformer_structure"
                    ),
                    "metadata": {
                        "model": table.get(
                            "model",
                            "microsoft/table-transformer-structure-recognition"
                        ),
                        "row_count": table.get("row_count", 0),
                        "column_count": table.get("column_count", 0),
                        "structure_confidence": table.get("structure_confidence", 0.0),
                        "has_merged_cells": table.get("has_merged_cells", False),
                        "processing_time": table.get("processing_time", 0.0),
                    }
                }
                pipeline_tables.append(pipeline_table)

        logger.info(
            f"✅ Converted {len(pipeline_tables)} Modal tables to "
            f"pipeline format (complete data, no extraction needed)"
        )
        return pipeline_tables
    
    def _build_normalized_text(
        self, 
        table_number: str, 
        title: str,
        header_rows: List,
        data_rows: List
    ) -> str:
        """
        Build normalized text representation from table data.
        
        Args:
            table_number: Table number (e.g., "3.1")
            title: Table title
            header_rows: List of TableRow objects (headers)
            data_rows: List of TableRow objects (data)
            
        Returns:
            Normalized text representation
        """
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


# Global instance
modal_service = ModalTableService()
