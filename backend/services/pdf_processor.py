"""
Main PDF processing pipeline orchestrator
"""
import logging
from pathlib import Path
from typing import Dict, Any
from collections import Counter

from services.pdf_classifier import PDFClassifier
from services.document_zone_classifier import DocumentZoneClassifier
from services.clause_processor import ClauseProcessor
from services.table_processor import TableProcessor
from services.validator import Validator
from services.output_generator import OutputGenerator

logger = logging.getLogger(__name__)


class PDFProcessor:
    """Main orchestrator for PDF processing pipeline"""
    
    def __init__(self):
        self.classifier = PDFClassifier()
        self.zone_classifier = DocumentZoneClassifier()
        self.clause_processor = ClauseProcessor()
        self.table_processor = TableProcessor()
        self.validator = Validator()
        self.output_generator = OutputGenerator()
    
    async def process_pdf(self, input_path: str, output_dir: str, job_id: str) -> Dict[str, Any]:
        """
        Main processing pipeline
        
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
            # Step 1: Classify PDF
            logger.info("Step 1: Classifying PDF...")
            classification, metadata = self.classifier.classify(input_path)
            result["steps"]["classification"] = {
                "status": "success",
                "classification": classification,
                "metadata": metadata
            }
            logger.info(f"PDF classified as: {classification}")
            
            # Step 2: OCR if needed
            ocr_path = input_path
            if classification == "scanned":
                result["steps"]["ocr"] = {
                    "status": "skipped",
                    "message": "OCR skipped (pdfplumber-only mode)"
                }
            else:
                result["steps"]["ocr"] = {
                    "status": "skipped",
                    "message": "PDF is text-based, OCR not needed"
                }
            
            # Step 3: Extract text and tables
            logger.info("Step 3: Extracting text and tables...")
            extracted_data = await self._extract_with_pdfplumber(ocr_path)
            result["steps"]["extraction"] = {
                "status": "success",
                "method": extracted_data.get("method", "unknown")
            }
            logger.info(f"Extraction completed using method: {extracted_data.get('method')}")
            
            # Step 4: Build page map
            page_map = self._build_page_map(extracted_data)
            
            # Step 4.5: Classify document zones
            logger.info("Step 4.5: Classifying document zones...")
            pages = self._extract_pages(extracted_data)
            zone_map = self.zone_classifier.classify_pages(pages)
            result["steps"]["zone_classification"] = {
                "status": "success",
                "zone_summary": dict(Counter(zone_map.values()))
            }
            
            # Step 5: Process clauses (with zone filtering)
            logger.info("Step 5: Processing clauses...")
            elements = self._extract_elements(extracted_data)
            
            # Filter elements to only parseable zones
            filtered_elements = self.zone_classifier.filter_elements_by_zone(elements, page_map)
            
            # Clean text from repeated headers/footers
            for element in filtered_elements:
                if 'text' in element:
                    element['text'] = self.zone_classifier.clean_text(element['text'])
            
            clauses = self.clause_processor.process_elements(filtered_elements, page_map)
            result["steps"]["clause_processing"] = {
                "status": "success",
                "count": len(clauses),
                "filtered_elements": len(filtered_elements),
                "original_elements": len(elements)
            }
            logger.info(f"Processed {len(clauses)} clauses from {len(filtered_elements)} filtered elements")
            
            # Step 6: Process tables
            logger.info("Step 6: Processing tables...")
            tables = self.table_processor.process_tables(
                extracted_data, page_map, source_pdf_path=ocr_path, clauses=clauses
            )
            result["steps"]["table_processing"] = {
                "status": "success",
                "count": len(tables)
            }
            logger.info(f"Processed {len(tables)} tables")
            
            # Step 7: Validate
            logger.info("Step 7: Validating results...")
            clause_issues = self.validator.validate_clauses(clauses)
            table_issues = self.validator.validate_tables(tables)
            validation_summary = self.validator.get_summary()
            result["steps"]["validation"] = {
                "status": "success",
                "summary": validation_summary,
                "issues": [issue.model_dump() for issue in self.validator.issues]
            }
            logger.info(f"Validation completed: {validation_summary}")
            
            # Step 8: Generate outputs
            logger.info("Step 8: Generating output files...")
            document_title = self._extract_document_title(extracted_data)
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
                "document_title": document_title
            }
            
            logger.info(f"PDF processing completed successfully (Job ID: {job_id})")
            return result
            
        except Exception as e:
            logger.error(f"Error in PDF processing pipeline: {e}", exc_info=True)
            result["error"] = str(e)
            result["status"] = "failed"
            raise

    async def process_pdf_tables_only(self, input_path: str, output_dir: str, job_id: str) -> Dict[str, Any]:
        """
        Run only the table pipeline and write tables.json (skips clauses, zones, full text outputs).
        Parent clause links on tables will be empty unless clauses are provided elsewhere.
        """
        logger.info(f"Starting tables-only processing (Job ID: {job_id})")
        result: Dict[str, Any] = {
            "job_id": job_id,
            "mode": "tables_only",
            "steps": {},
        }
        try:
            tables = self.table_processor.process_tables(
                {}, {}, source_pdf_path=input_path, clauses=[]
            )
            result["steps"]["table_processing"] = {
                "status": "success",
                "count": len(tables),
            }
            self.validator.issues = []
            table_issues = self.validator.validate_tables(tables)
            validation_summary = self.validator.get_summary()
            result["steps"]["validation"] = {
                "status": "success",
                "summary": validation_summary,
                "issues": [issue.model_dump() for issue in table_issues],
            }
            out = Path(output_dir)
            out.mkdir(exist_ok=True, parents=True)
            tables_path = out / "tables.json"
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
            logger.info(f"Tables-only processing completed (Job ID: {job_id}, {len(tables)} tables)")
            return result
        except Exception as e:
            logger.error(f"Error in tables-only processing: {e}", exc_info=True)
            result["error"] = str(e)
            result["status"] = "failed"
            raise

    async def _extract_with_pdfplumber(self, input_path: str) -> Dict[str, Any]:
        """Local text extraction path (pdfplumber primary, pypdf fallback)."""
        try:
            import pdfplumber

            extracted_data = {
                "method": "pdfplumber",
                "elements": [],
                "pages": [],
            }
            with pdfplumber.open(input_path) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text() or ""
                    element_id = f"page_{page_num}_element_0"
                    page_data = {
                        "page": page_num,
                        "text": text,
                        "elements": [
                            {
                                "id": element_id,
                                "type": "text",
                                "text": text,
                                "page": page_num,
                            }
                        ],
                    }
                    extracted_data["pages"].append(page_data)
                    extracted_data["elements"].extend(page_data["elements"])
            return extracted_data
        except Exception as e:
            logger.warning("pdfplumber extraction failed; falling back to pypdf: %s", e, exc_info=True)
            return await self._extract_with_pypdf2(input_path)

    async def _extract_with_pypdf2(self, input_path: str) -> Dict[str, Any]:
        from pypdf import PdfReader

        extracted_data = {
            "method": "pypdf_fallback",
            "elements": [],
            "pages": [],
        }
        with open(input_path, "rb") as file:
            reader = PdfReader(file)
            for page_num, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                element_id = f"page_{page_num}_element_0"
                page_data = {
                    "page": page_num,
                    "text": text,
                    "elements": [
                        {
                            "id": element_id,
                            "type": "text",
                            "text": text,
                            "page": page_num,
                        }
                    ],
                }
                extracted_data["pages"].append(page_data)
                extracted_data["elements"].extend(page_data["elements"])
        return extracted_data
    
    def _build_page_map(self, extracted_data: Dict) -> Dict[str, int]:
        """Build mapping of element IDs to page numbers"""
        page_map = {}
        pages = extracted_data.get("pages", [])
        for page_data in pages:
            page_num = page_data.get("page", 1)
            for element in page_data.get("elements", []):
                element_id = element.get("id", f"page_{page_num}")
                page_map[element_id] = page_num
        
        return page_map
    
    def _extract_elements(self, extracted_data: Dict) -> list:
        """Extract text elements from extracted data"""
        elements = []
        pages = extracted_data.get("pages", [])
        for page_data in pages:
            elements.extend(page_data.get("elements", []))
        return elements
    
    def _extract_pages(self, extracted_data: Dict) -> list:
        """Extract page data for zone classification"""
        return extracted_data.get("pages", [])
    
    def _extract_document_title(self, extracted_data: Dict) -> str:
        """Attempt to extract document title"""
        # Simple heuristic: look for first heading or use first line
        elements = self._extract_elements(extracted_data)
        
        for element in elements[:5]:  # Check first 5 elements
            text = (element.get("text") or "").strip()
            if text and len(text) < 200:  # Reasonable title length
                return text
        
        return "Extracted Document"
