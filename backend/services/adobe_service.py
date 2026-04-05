"""
Adobe PDF Extract API Service
==============================
Provides high-quality OCR and text extraction with coordinates.
Replaces Tesseract OCR in Modal pipeline for better text quality.

Usage Limit: 500 documents/month
Cost: ~$0.05-0.10 per document

Returns text with bounding box coordinates for mapping to Modal table structures.
"""

import logging
import json
import time
import zipfile
import io
from typing import Dict, Any, List, Optional
from pathlib import Path

try:
    from adobe.pdfservices.operation.auth.credentials import Credentials
    from adobe.pdfservices.operation.execution_context import ExecutionContext
    from adobe.pdfservices.operation.pdfops.extract_pdf_operation import ExtractPDFOperation
    from adobe.pdfservices.operation.pdfops.options.extractpdf.extract_pdf_options import ExtractPDFOptions
    from adobe.pdfservices.operation.pdfops.options.extractpdf.extract_element_type import ExtractElementType
    from adobe.pdfservices.operation.pdfops.options.extractpdf.extract_renditions_element_type import ExtractRenditionsElementType
    from adobe.pdfservices.operation.io.file_ref import FileRef
    ADOBE_SDK_AVAILABLE = True
except ImportError:
    ADOBE_SDK_AVAILABLE = False

from config import settings

logger = logging.getLogger(__name__)


class AdobeService:
    """Adobe PDF Extract API client for high-quality text extraction"""

    def __init__(self):
        self.client_id = settings.adobe_client_id
        self.client_secret = settings.adobe_client_secret
        self.org_id = getattr(settings, 'adobe_org_id', None)
        
        self.available = False
        self.credentials = None
        self.execution_context = None

        if not ADOBE_SDK_AVAILABLE:
            logger.warning("❌ Adobe PDF Services SDK not installed. Install with: pip install pdfservices-sdk")
            return

        if not self.client_id or not self.client_secret:
            logger.warning("⚠️ Adobe credentials not configured in .env")
            logger.info("   Add ADOBE_CLIENT_ID and ADOBE_CLIENT_SECRET to use Adobe OCR")
            return

        try:
            # Initialize credentials
            self.credentials = Credentials.service_principal_credentials_builder().\
                with_client_id(self.client_id).\
                with_client_secret(self.client_secret).\
                build()

            # Create execution context
            self.execution_context = ExecutionContext.create(self.credentials)
            
            self.available = True
            logger.info("✅ Adobe PDF Services initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Adobe PDF Services: {e}")
            self.available = False

    def is_available(self) -> bool:
        """Check if Adobe service is available and configured"""
        return self.available

    def extract_text_with_coordinates(
        self, 
        pdf_path: Path, 
        filename: str = None
    ) -> Dict[str, Any]:
        """
        Extract text with bounding box coordinates from PDF.
        
        Args:
            pdf_path: Path to PDF file
            filename: Optional filename for logging
            
        Returns:
            {
                "success": True,
                "pages": [
                    {
                        "page_number": 1,
                        "width": 612,
                        "height": 792,
                        "elements": [
                            {
                                "text": "Table 3.1",
                                "bbox": {"x": 100, "y": 200, "width": 50, "height": 12},
                                "font": "Arial-Bold",
                                "font_size": 12
                            },
                            ...
                        ]
                    },
                    ...
                ],
                "processing_time": 12.5,
                "page_count": 158
            }
            
        Raises:
            Exception: If extraction fails
        """
        if not self.is_available():
            raise ValueError("Adobe PDF Services not available")

        filename = filename or pdf_path.name
        start_time = time.time()

        try:
            logger.info(f"📄 Adobe Extract API: {filename}")
            
            # Create ExtractPDF operation
            extract_pdf_operation = ExtractPDFOperation.create_new()

            # Set operation input from source file
            source = FileRef.create_from_local_file(str(pdf_path))
            extract_pdf_operation.set_input(source)

            # Set options: extract text with coordinates
            extract_pdf_options = ExtractPDFOptions.builder().\
                with_element_to_extract(ExtractElementType.TEXT).\
                build()
            
            extract_pdf_operation.set_options(extract_pdf_options)

            # Execute operation
            logger.info("   Executing Adobe Extract API...")
            result: FileRef = extract_pdf_operation.execute(self.execution_context)

            # Save result to temporary location
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_file:
                result.save_as(temp_file.name)
                temp_path = Path(temp_file.name)

            # Extract JSON from ZIP
            logger.info("   Parsing extraction results...")
            with zipfile.ZipFile(temp_path, 'r') as zip_ref:
                # Adobe returns structuredData.json
                json_content = zip_ref.read('structuredData.json')
                adobe_data = json.loads(json_content)

            # Clean up temp file
            temp_path.unlink()

            # Parse Adobe JSON to our format
            parsed_data = self._parse_adobe_json(adobe_data)
            
            processing_time = time.time() - start_time
            
            logger.info(f"   ✅ Extracted {parsed_data['page_count']} pages in {processing_time:.2f}s")
            
            return {
                "success": True,
                "pages": parsed_data["pages"],
                "page_count": parsed_data["page_count"],
                "processing_time": round(processing_time, 2),
                "raw_data": adobe_data  # Keep for debugging
            }

        except Exception as e:
            error_msg = f"Adobe Extract API error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "error": error_msg,
                "pages": [],
                "page_count": 0
            }

    def _parse_adobe_json(self, adobe_data: Dict) -> Dict[str, Any]:
        """
        Parse Adobe structuredData.json to our coordinate format.
        
        Adobe JSON structure:
        {
            "elements": [
                {
                    "Path": "//Document/P",
                    "Text": "Table 3.1",
                    "Bounds": [100, 200, 150, 212],
                    "Font": {"name": "Arial-Bold", "size": 12},
                    "Page": 0
                },
                ...
            ]
        }
        """
        pages_dict = {}
        
        for element in adobe_data.get("elements", []):
            page_num = element.get("Page", 0) + 1  # Adobe uses 0-indexed pages
            
            if page_num not in pages_dict:
                pages_dict[page_num] = {
                    "page_number": page_num,
                    "width": 612,  # Default US Letter, update if available
                    "height": 792,
                    "elements": []
                }
            
            text = element.get("Text", "").strip()
            if not text:
                continue
            
            bounds = element.get("Bounds", [])
            font_info = element.get("Font", {})
            
            # Adobe Bounds: [x, y, x+width, y+height]
            if len(bounds) == 4:
                x0, y0, x1, y1 = bounds
                bbox = {
                    "x": x0,
                    "y": y0,
                    "width": x1 - x0,
                    "height": y1 - y0
                }
            else:
                # Fallback if bounds missing
                bbox = {"x": 0, "y": 0, "width": 0, "height": 0}
            
            pages_dict[page_num]["elements"].append({
                "text": text,
                "bbox": bbox,
                "font": font_info.get("name", ""),
                "font_size": font_info.get("size", 0)
            })

        # Convert to sorted list
        pages = [pages_dict[i] for i in sorted(pages_dict.keys())]
        
        return {
            "pages": pages,
            "page_count": len(pages)
        }

    def extract_text_in_region(
        self,
        pages: List[Dict],
        page_num: int,
        bbox: Dict[str, float]
    ) -> str:
        """
        Extract text within a specific bounding box region.
        
        Args:
            pages: Parsed Adobe pages data
            page_num: Page number (1-indexed)
            bbox: {"x": x0, "y": y0, "width": w, "height": h}
            
        Returns:
            Combined text from all elements in the region
        """
        if page_num < 1 or page_num > len(pages):
            return ""
        
        page = pages[page_num - 1]
        x0 = bbox["x"]
        y0 = bbox["y"]
        x1 = x0 + bbox["width"]
        y1 = y0 + bbox["height"]
        
        # Find overlapping elements
        region_text = []
        for element in page["elements"]:
            elem_bbox = element["bbox"]
            elem_x0 = elem_bbox["x"]
            elem_y0 = elem_bbox["y"]
            elem_x1 = elem_x0 + elem_bbox["width"]
            elem_y1 = elem_y0 + elem_bbox["height"]
            
            # Check for overlap
            if not (elem_x1 < x0 or elem_x0 > x1 or elem_y1 < y0 or elem_y0 > y1):
                region_text.append(element["text"])
        
        return " ".join(region_text)

    def map_text_to_table_structure(
        self,
        pages: List[Dict],
        table_bbox: Dict,
        page_num: int,
        structure_data: Dict
    ) -> Dict[str, Any]:
        """
        Map Adobe high-quality text to Modal table structure.
        
        Args:
            pages: Adobe text with coordinates
            table_bbox: Table bounding box from Modal
            page_num: Page number
            structure_data: Modal table structure (rows, columns, cells)
            
        Returns:
            Table with high-quality text mapped to structure cells
        """
        # Extract text in table region
        table_text = self.extract_text_in_region(pages, page_num, table_bbox)
        
        # Get all text elements in table region
        page = pages[page_num - 1]
        x0 = table_bbox["x"]
        y0 = table_bbox["y"]
        x1 = x0 + table_bbox["width"]
        y1 = y0 + table_bbox["height"]
        
        table_elements = []
        for element in page["elements"]:
            elem_bbox = element["bbox"]
            elem_x0 = elem_bbox["x"]
            elem_y0 = elem_bbox["y"]
            elem_x1 = elem_x0 + elem_bbox["width"]
            elem_y1 = elem_y0 + elem_bbox["height"]
            
            # Check if element is within table
            if not (elem_x1 < x0 or elem_x0 > x1 or elem_y1 < y0 or elem_y0 > y1):
                table_elements.append({
                    "text": element["text"],
                    "x": elem_x0,
                    "y": elem_y0,
                    "width": elem_bbox["width"],
                    "height": elem_bbox["height"]
                })
        
        # Map elements to cells based on Modal structure
        # Structure has rows with cell bboxes
        for row in structure_data.get("rows", []):
            for cell in row.get("cells", []):
                cell_bbox = cell.get("bbox", {})
                if not cell_bbox:
                    continue
                
                # Find text elements in this cell
                cell_x0 = cell_bbox.get("x", 0)
                cell_y0 = cell_bbox.get("y", 0)
                cell_x1 = cell_x0 + cell_bbox.get("width", 0)
                cell_y1 = cell_y0 + cell_bbox.get("height", 0)
                
                cell_text = []
                for elem in table_elements:
                    elem_center_x = elem["x"] + elem["width"] / 2
                    elem_center_y = elem["y"] + elem["height"] / 2
                    
                    # Check if element center is in cell
                    if (cell_x0 <= elem_center_x <= cell_x1 and 
                        cell_y0 <= elem_center_y <= cell_y1):
                        cell_text.append(elem["text"])
                
                # Update cell text with Adobe OCR (better quality)
                cell["text"] = " ".join(cell_text)
        
        return structure_data
