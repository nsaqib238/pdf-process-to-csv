"""
Table processor facade.
"""
import logging
from typing import Any, Dict, List, Optional

from config import settings
from models.table import Table
from services.header_reconstructor import apply_reconstruction_to_tables
from services.table_pipeline import TablePipeline

logger = logging.getLogger(__name__)


class TableProcessor:
    """Thin wrapper around the dedicated table pipeline."""

    def __init__(self):
        self.tables: List[Table] = []
        self.pipeline = TablePipeline()

    def process_tables(
        self,
        extracted_data: Dict,
        page_map: Dict[str, int],
        source_pdf_path: Optional[str] = None,
        clauses: Optional[List[Any]] = None,
    ) -> List[Table]:
        if not source_pdf_path:
            logger.warning("Table pipeline skipped: source PDF path missing")
            self.tables = []
            return self.tables

        # Try Modal.com first if enabled
        if getattr(settings, "use_modal_extraction", False):
            try:
                from pathlib import Path
                from services.modal_table_service import modal_service

                logger.info(
                    "🚀 Attempting Modal.com table extraction..."
                )
                modal_result = modal_service.extract_tables(
                    Path(source_pdf_path),
                    filename=Path(source_pdf_path).name
                )

                if modal_result.get("success"):
                    modal_tables = modal_result.get("tables", [])
                    low_conf_count = modal_result.get(
                        "low_confidence_count", 0
                    )
                    high_conf_count = modal_result.get(
                        "high_confidence_count", 0
                    )

                    logger.info(
                        f"✅ Modal.com extracted {len(modal_tables)} "
                        f"tables ({high_conf_count} high confidence, "
                        f"{low_conf_count} low confidence)"
                    )

                    # Check if we should use Modal results or fall back
                    fallback_mode = getattr(
                        settings, "modal_fallback_mode", "openai"
                    )

                    if low_conf_count == 0 or fallback_mode == "skip":
                        # All tables have high confidence or skip mode
                        logger.info(
                            f"✅ Using Modal.com complete table data: "
                            f"{len(modal_tables)} tables"
                        )
                        pipeline_tables = (
                            modal_service.convert_to_pipeline_format(
                                modal_tables
                            )
                        )
                        self.tables = (
                            self._convert_dicts_to_table_objects(
                                pipeline_tables
                            )
                        )
                        # SKIP header reconstruction - Modal already extracted complete data
                        logger.info(
                            f"✅ Processed {len(self.tables)} tables "
                            f"via Modal.com (complete extraction, no post-processing needed)"
                        )
                        return self.tables
                    elif fallback_mode == "fail":
                        # Fail mode - error on low confidence
                        raise Exception(
                            f"Modal.com returned {low_conf_count} "
                            f"low confidence tables. "
                            f"Fallback mode is 'fail'."
                        )
                    else:
                        # OpenAI fallback mode
                        logger.warning(
                            f"⚠️  {low_conf_count} tables below "
                            f"confidence threshold. "
                            f"Falling back to OpenAI/geometric pipeline."
                        )
                        # Fall through to existing pipeline
                else:
                    # Modal extraction failed
                    error = modal_result.get("error", "Unknown error")
                    logger.warning(
                        f"⚠️  Modal.com extraction failed: {error}"
                    )

                    fallback_mode = getattr(
                        settings, "modal_fallback_mode", "openai"
                    )
                    if fallback_mode == "fail":
                        raise Exception(f"Modal.com failed: {error}")
                    elif fallback_mode == "skip":
                        logger.info(
                            "Falling back to geometric extraction only "
                            "(skip mode)"
                        )
                    else:
                        logger.info(
                            "Falling back to OpenAI/geometric pipeline"
                        )
                    # Fall through to existing pipeline

            except Exception as e:
                logger.error(
                    f"❌ Modal.com extraction error: {e}",
                    exc_info=True
                )
                fallback_mode = getattr(
                    settings, "modal_fallback_mode", "openai"
                )
                if fallback_mode == "fail":
                    raise
                logger.info(
                    "Falling back to OpenAI/geometric pipeline "
                    "due to error"
                )

        # Existing pipeline (OpenAI + geometric extraction)
        self.tables = self.pipeline.process(source_pdf_path, clauses=clauses or [])
        if getattr(settings, "enable_header_reconstruction", True):
            self.tables = apply_reconstruction_to_tables(self.tables)
        logger.info(f"Processed {len(self.tables)} tables")
        return self.tables
    
    def _convert_dicts_to_table_objects(self, table_dicts: List[Dict]) -> List[Table]:
        """Convert dictionary format tables to Table objects."""
        table_objects = []
        for table_dict in table_dicts:
            try:
                # Create Table object from dictionary
                table = Table(
                    table_number=table_dict.get("table_number", ""),
                    page=table_dict.get("page", 0),
                    detection_method=table_dict.get("detection_method", "modal_table_transformer"),
                    bbox=table_dict.get("bbox", {}),
                    data=table_dict.get("data", []),
                    parent_clause_id=table_dict.get("parent_clause_id"),
                    confidence=table_dict.get("confidence", 0.0),
                    metadata=table_dict.get("metadata", {})
                )
                table_objects.append(table)
            except Exception as e:
                logger.warning(f"Failed to convert table dict to Table object: {e}")
                continue
        return table_objects
