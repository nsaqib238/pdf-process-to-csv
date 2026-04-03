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

        Modal format:
        {
            "page": 12,
            "confidence": 0.95,
            "bbox": {"x0": 100, "y0": 200, "x1": 500, "y1": 400},
            "width": 400,
            "height": 200,
            "page_width": 595,
            "page_height": 842
        }

        Pipeline format:
        {
            "table_number": "MODAL_P12_T1",
            "page": 12,
            "detection_method": "modal_table_transformer",
            "confidence": 0.95,
            "bbox": {...},
            "data": []  # Empty, will be extracted later
        }

        Args:
            modal_tables: List of tables from Modal.com

        Returns:
            List of tables in pipeline format
        """
        pipeline_tables = []

        # Group tables by page for numbering
        tables_by_page = {}
        for table in modal_tables:
            page = table.get("page", 0)
            if page not in tables_by_page:
                tables_by_page[page] = []
            tables_by_page[page].append(table)

        # Convert to pipeline format with page-specific numbering
        for page, page_tables in sorted(tables_by_page.items()):
            for idx, table in enumerate(page_tables, 1):
                pipeline_table = {
                    "table_number": f"MODAL_P{page}_T{idx}",
                    "page": page,
                    "detection_method": "modal_table_transformer",
                    "confidence": table.get("confidence", 0.0),
                    "bbox": table.get("bbox", {}),
                    "width": table.get("width", 0),
                    "height": table.get("height", 0),
                    "page_width": table.get("page_width", 0),
                    "page_height": table.get("page_height", 0),
                    "data": [],  # Will be populated by table extraction
                    "metadata": {
                        "model": table.get(
                            "model",
                            "microsoft/table-transformer-detection"
                        ),
                        "detection_method": table.get(
                            "detection_method", "table_transformer"
                        )
                    }
                }
                pipeline_tables.append(pipeline_table)

        logger.info(
            f"✅ Converted {len(pipeline_tables)} Modal tables to "
            f"pipeline format"
        )
        return pipeline_tables


# Global instance
modal_service = ModalTableService()
