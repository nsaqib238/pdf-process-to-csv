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

        self.tables = self.pipeline.process(source_pdf_path, clauses=clauses or [])
        if getattr(settings, "enable_header_reconstruction", True):
            self.tables = apply_reconstruction_to_tables(self.tables)
        logger.info(f"Processed {len(self.tables)} tables")
        return self.tables
