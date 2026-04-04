"""
Simplified PDF Processor - Uses Modal.com for All Extraction
============================================================
Modal.com extracts both tables and clauses, backend validates and saves.
"""

import logging
from pathlib import Path
from typing import Dict, Any

from services.modal_service import ModalService
from services.table_processor import TableProcessor
from services.validator import Validator
from services.output_generator import OutputGenerator
from models.clause import Clause

logger = logging.getLogger(__name__)


class PDFProcessor:
    """Simplified PDF processor using Modal.com for extraction"""

    def __init__(self):
        self.modal_service = ModalService()
        self.table_processor = TableProcessor()
        self.validator = Validator()
        self.output_generator = OutputGenerator()

    async def process_pdf(self, input_path: str, output_dir: str, job_id: str) -> Dict[str, Any]:
        """
        Complete PDF processing pipeline using Modal.com.

        Pipeline:
        1. Call Modal.com → Extract tables + clauses
        2. Convert to backend objects
        3. Validate data quality
        4. Generate output files (clauses.json, tables.json, normalized_document.txt)

        Args:
            input_path: Path to input PDF
            output_dir: Directory for output files
            job_id: Unique job identifier

        Returns:
            Processing result summary
        """
        logger.info(f"Starting PDF processing pipeline (Job ID: {job_id})")
        result = {
            "job_id": job_id,
            "steps": {}
        }

        try:
            # Check if Modal.com is available
            if not self.modal_service.is_available():
                raise ValueError(
                    "Modal.com is not configured. "
                    "Please set MODAL_ENDPOINT in .env file."
                )

            # Step 1: Extract complete data from Modal.com
            logger.info("Step 1: Extracting tables and clauses via Modal.com...")
            extraction_result = self.modal_service.extract_complete(
                Path(input_path),
                filename=Path(input_path).name
            )

            # DEBUG: Log what Modal actually returned
            logger.info(f"Modal extraction result keys: {list(extraction_result.keys())}")
            logger.info(f"Modal success: {extraction_result.get('success')}")
            logger.info(f"Modal table_count: {extraction_result.get('table_count')}")
            logger.info(f"Modal clause_count: {extraction_result.get('clause_count')}")
            logger.info(f"Modal tables list length: {len(extraction_result.get('tables', []))}")
            logger.info(f"Modal clauses list length: {len(extraction_result.get('clauses', []))}")
            if extraction_result.get("error"):
                logger.error(f"Modal returned error: {extraction_result.get('error')}")

            if not extraction_result.get("success"):
                error_msg = extraction_result.get("error", "Unknown error")
                raise Exception(f"Modal.com extraction failed: {error_msg}")

            result["steps"]["modal_extraction"] = {
                "status": "success",
                "table_count": extraction_result.get("table_count", 0),
                "clause_count": extraction_result.get("clause_count", 0),
                "processing_time": extraction_result.get("processing_time", 0),
                "cost_estimate": extraction_result.get("cost_estimate", 0),
            }
            
            logger.info(
                f"✅ Modal.com extracted {extraction_result['table_count']} tables, "
                f"{extraction_result['clause_count']} clauses "
                f"(${extraction_result.get('cost_estimate', 0):.3f})"
            )

            # Step 2: Convert Modal tables to backend objects
            logger.info("Step 2: Converting Modal data to backend objects...")
            
            modal_tables = extraction_result.get("tables", [])
            modal_clauses = extraction_result.get("clauses", [])
            
            # Convert tables
            table_dicts = self.modal_service.convert_tables_to_objects(modal_tables)
            
            # Convert clauses
            clause_dicts = self.modal_service.convert_clauses_to_objects(modal_clauses)
            clauses = [Clause(**c) for c in clause_dicts]
            
            # Process tables (with clause linking)
            tables = self.table_processor.process_tables_from_modal(
                table_dicts,
                clauses=clauses
            )

            result["steps"]["conversion"] = {
                "status": "success",
                "tables_converted": len(tables),
                "clauses_converted": len(clauses),
            }

            logger.info(f"✅ Converted {len(tables)} tables, {len(clauses)} clauses")

            # Step 3: Validate
            logger.info("Step 3: Validating results...")
            clause_issues = self.validator.validate_clauses(clauses)
            table_issues = self.validator.validate_tables(tables)
            validation_summary = self.validator.get_summary()

            result["steps"]["validation"] = {
                "status": "success",
                "summary": validation_summary,
                "issues": [issue.model_dump() for issue in self.validator.issues]
            }

            logger.info(f"Validation completed: {validation_summary}")

            # Step 4: Generate outputs
            logger.info("Step 4: Generating output files...")
            document_title = self._extract_document_title(clauses)
            self.output_generator.generate_all(clauses, tables, output_dir, document_title)

            result["steps"]["output_generation"] = {
                "status": "success",
                "files": [
                    "normalized_document.txt",
                    "clauses.json",
                    "tables.json"
                ]
            }

            # Summary
            result["summary"] = {
                "total_clauses": len(clauses),
                "total_tables": len(tables),
                "validation_issues": validation_summary,
                "document_title": document_title,
                "extraction_cost": extraction_result.get("cost_estimate", 0),
                "extraction_time": extraction_result.get("processing_time", 0),
            }

            logger.info(f"✅ PDF processing completed successfully (Job ID: {job_id})")
            return result

        except Exception as e:
            logger.error(f"Error in PDF processing pipeline: {e}", exc_info=True)
            result["error"] = str(e)
            result["status"] = "failed"
            raise

    async def process_pdf_tables_only(
        self, 
        input_path: str, 
        output_dir: str, 
        job_id: str
    ) -> Dict[str, Any]:
        """
        Process tables only (skip clauses).

        Args:
            input_path: Path to input PDF
            output_dir: Directory for output files
            job_id: Unique job identifier

        Returns:
            Processing result summary
        """
        logger.info(f"Starting tables-only processing (Job ID: {job_id})")
        result = {
            "job_id": job_id,
            "mode": "tables_only",
            "steps": {},
        }

        try:
            if not self.modal_service.is_available():
                raise ValueError("Modal.com is not configured")

            # Extract via Modal.com
            extraction_result = self.modal_service.extract_complete(
                Path(input_path),
                filename=Path(input_path).name
            )

            if not extraction_result.get("success"):
                raise Exception(f"Modal.com extraction failed: {extraction_result.get('error')}")

            # Convert and process tables only
            modal_tables = extraction_result.get("tables", [])
            table_dicts = self.modal_service.convert_tables_to_objects(modal_tables)
            tables = self.table_processor.process_tables_from_modal(table_dicts, clauses=[])

            result["steps"]["modal_extraction"] = {
                "status": "success",
                "table_count": len(tables),
            }

            # Validate tables
            self.validator.issues = []
            table_issues = self.validator.validate_tables(tables)
            validation_summary = self.validator.get_summary()

            result["steps"]["validation"] = {
                "status": "success",
                "summary": validation_summary,
                "issues": [issue.model_dump() for issue in table_issues],
            }

            # Generate tables.json only
            output_path = Path(output_dir)
            output_path.mkdir(exist_ok=True, parents=True)
            tables_path = output_path / "tables.json"
            self.output_generator.generate_tables_json(tables, str(tables_path))

            result["steps"]["output_generation"] = {
                "status": "success",
                "files": ["tables.json"],
            }

            result["summary"] = {
                "total_clauses": 0,
                "total_tables": len(tables),
                "validation_issues": validation_summary,
                "document_title": None,
            }

            logger.info(f"✅ Tables-only processing completed (Job ID: {job_id}, {len(tables)} tables)")
            return result

        except Exception as e:
            logger.error(f"Error in tables-only processing: {e}", exc_info=True)
            result["error"] = str(e)
            result["status"] = "failed"
            raise

    def _extract_document_title(self, clauses: list) -> str:
        """Extract document title from first top-level clause or default."""
        if clauses:
            # Try to find title from first clause
            for clause in clauses:
                if clause.level == 1 and clause.title:
                    return clause.title
            
            # Fallback to first clause with title
            for clause in clauses:
                if clause.title:
                    return clause.title

        return "Technical Standard Document"
