"""
Adobe PDF Services integration module (pdfservices-sdk 4.x job-based API).
"""
import json
import logging
import os
import zipfile
from io import BytesIO
from typing import Any, Dict, List, Optional

from config import settings

logger = logging.getLogger(__name__)


class AdobePDFServices:
    """Adobe PDF Services SDK integration"""
    
    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None):
        """
        Initialize Adobe PDF Services
        
        Args:
            client_id: Adobe API client ID
            client_secret: Adobe API client secret
        """
        # Use Settings (reads backend/.env via pydantic-settings); os.getenv misses that file.
        self.client_id = client_id or settings.adobe_client_id
        self.client_secret = client_secret or settings.adobe_client_secret

        self.has_credentials = bool(self.client_id and self.client_secret)

        if not self.has_credentials:
            logger.warning(
                "Adobe PDF Services credentials not found. "
                "Set ADOBE_CLIENT_ID and ADOBE_CLIENT_SECRET in backend/.env."
            )

    @staticmethod
    def _resolve_ocr_locale():
        """Map settings.ocr_locale (e.g. en-US) to SDK OCRSupportedLocale."""
        from adobe.pdfservices.operation.pdfjobs.params.ocr_pdf.ocr_supported_locale import (
            OCRSupportedLocale,
        )

        raw = (settings.ocr_locale or "en-US").strip()
        for loc in OCRSupportedLocale:
            if loc.value == raw:
                return loc
        return OCRSupportedLocale.EN_US

    @staticmethod
    def _bytes_from_stream_asset(stream_asset) -> bytes:
        """SDK may return bytes or a readable stream from StreamAsset.get_input_stream()."""
        raw = stream_asset.get_input_stream()
        if isinstance(raw, (bytes, bytearray, memoryview)):
            return bytes(raw)
        return raw.read()

    @staticmethod
    def _build_pdf_services(client_id: str, client_secret: str):
        """Create PDFServices client with safer timeouts for long extract jobs."""
        from adobe.pdfservices.operation.auth.service_principal_credentials import (
            ServicePrincipalCredentials,
        )
        from adobe.pdfservices.operation.config.client_config import ClientConfig
        from adobe.pdfservices.operation.pdf_services import PDFServices

        credentials = ServicePrincipalCredentials(
            client_id=client_id,
            client_secret=client_secret,
        )
        client_config = ClientConfig(
            connect_timeout=int(settings.adobe_connect_timeout_ms),
            read_timeout=int(settings.adobe_read_timeout_ms),
        )
        return PDFServices(credentials=credentials, client_config=client_config)

    async def extract_pdf(self, input_path: str, output_dir: str) -> Dict[str, Any]:
        """
        Extract text, tables, and structure from PDF using Adobe Extract API
        
        Args:
            input_path: Path to input PDF
            output_dir: Directory for output files
            
        Returns:
            Dictionary containing extracted data
        """
        if not self.has_credentials:
            raise RuntimeError(
                "Adobe PDF Services credentials are not configured. "
                "Set ADOBE_CLIENT_ID and ADOBE_CLIENT_SECRET in backend/.env."
            )

        # IMPORTANT: fallback is intentionally disabled for now.
        # If Adobe SDK fails, we want the error to be visible so we can fix it.
        return await self._extract_with_adobe_sdk(input_path, output_dir)

    async def extract_pdfplumber(self, input_path: str, output_dir: str) -> Dict[str, Any]:
        """Extract using pdfplumber fallback path explicitly (user-selected)."""
        return await self._extract_fallback(input_path, output_dir)

    @staticmethod
    def _pdf_page_count(path: str) -> int:
        from pypdf import PdfReader

        reader = PdfReader(path)
        return len(reader.pages)

    @staticmethod
    def _write_pdf_pages(src_path: str, dest_path: str, start_idx: int, end_idx: int) -> None:
        """Copy pages [start_idx, end_idx) (0-based) into a new PDF."""
        from pypdf import PdfReader, PdfWriter

        reader = PdfReader(src_path)
        writer = PdfWriter()
        for i in range(start_idx, end_idx):
            writer.add_page(reader.pages[i])
        with open(dest_path, "wb") as out:
            writer.write(out)

    @staticmethod
    def _merge_chunked_structured(
        chunk_structured: List[Dict[str, Any]], chunk_first_page: List[int]
    ) -> Dict[str, Any]:
        """
        Merge structuredData dicts from per-chunk extracts. Fixes global Page numbers and
        makes Path unique (chunks reuse the same XPath roots).
        """
        if not chunk_structured:
            return {}
        merged: Dict[str, Any] = {k: v for k, v in chunk_structured[0].items() if k != "elements"}
        merged_elements: List[Dict[str, Any]] = []
        for sd, first_page in zip(chunk_structured, chunk_first_page):
            for el in sd.get("elements", []):
                el = dict(el)
                loc = el.get("Page", 1)
                el["Page"] = first_page + loc - 1
                path = el.get("Path", "")
                if path:
                    el["Path"] = f"{path}#part{first_page}_{loc}"
                merged_elements.append(el)
        merged["elements"] = merged_elements
        return merged

    def _extract_one_pdf_with_services(
        self,
        pdf_services: Any,
        input_path: str,
        work_dir: str,
    ) -> Dict[str, Any]:
        """Run Extract on one PDF; unzip under work_dir/extracted; return structuredData dict."""
        from adobe.pdfservices.operation.pdf_services_media_type import PDFServicesMediaType
        from adobe.pdfservices.operation.pdfjobs.jobs.extract_pdf_job import ExtractPDFJob
        from adobe.pdfservices.operation.pdfjobs.params.extract_pdf.extract_element_type import (
            ExtractElementType,
        )
        from adobe.pdfservices.operation.pdfjobs.params.extract_pdf.extract_pdf_params import (
            ExtractPDFParams,
        )
        from adobe.pdfservices.operation.pdfjobs.result.extract_pdf_result import ExtractPDFResult

        with open(input_path, "rb") as f:
            pdf_bytes = f.read()
        input_asset = pdf_services.upload(
            BytesIO(pdf_bytes), PDFServicesMediaType.PDF.mime_type
        )

        extract_pdf_params = ExtractPDFParams(
            elements_to_extract=[ExtractElementType.TEXT, ExtractElementType.TABLES],
            add_char_info=True,
            styling_info=True,
        )
        extract_pdf_job = ExtractPDFJob(
            input_asset=input_asset,
            extract_pdf_params=extract_pdf_params,
        )
        location = pdf_services.submit(extract_pdf_job)
        pdf_services_response = pdf_services.get_job_result(location, ExtractPDFResult)
        result_asset = pdf_services_response.get_result().get_resource()
        stream_asset = pdf_services.get_content(result_asset)

        os.makedirs(work_dir, exist_ok=True)
        result_path = os.path.join(work_dir, "extract_result.zip")
        with open(result_path, "wb") as out:
            out.write(self._bytes_from_stream_asset(stream_asset))

        extract_dir = os.path.join(work_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(result_path, "r") as zip_ref:
            zip_ref.extractall(extract_dir)

        json_path = os.path.join(extract_dir, "structuredData.json")
        if not os.path.exists(json_path):
            raise FileNotFoundError("structuredData.json not found in extraction output")
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _is_adobe_timeout_error(exc: Exception) -> bool:
        msg = str(exc).upper()
        return "REQUEST_TIMEOUT" in msg or "OPERATION HAS TIMED OUT" in msg

    async def _extract_with_adobe_sdk(self, input_path: str, output_dir: str) -> Dict[str, Any]:
        """Extract using Adobe PDF Services SDK (4.x: PDFServices + ExtractPDFJob)."""
        try:
            pdf_services = self._build_pdf_services(self.client_id, self.client_secret)

            chunk_pages = max(1, int(settings.adobe_extract_chunk_pages))
            min_chunk_pages = max(1, int(settings.adobe_extract_min_chunk_pages))
            total_pages = self._pdf_page_count(input_path)

            if total_pages <= chunk_pages:
                extract_dir = os.path.join(output_dir, "extracted")
                os.makedirs(extract_dir, exist_ok=True)
                structured_data = self._extract_one_pdf_with_services(
                    pdf_services, input_path, output_dir
                )
                merged_path = os.path.join(extract_dir, "structuredData.json")
                with open(merged_path, "w", encoding="utf-8") as f:
                    json.dump(structured_data, f, ensure_ascii=False)
                logger.info("Successfully extracted PDF using Adobe SDK (single pass)")
                return {
                    "method": "adobe_sdk",
                    "structured_data": structured_data,
                    "extract_dir": extract_dir,
                }

            logger.info(
                "Splitting %s-page PDF into %s-page Extract chunks (Adobe scan/page limits)",
                total_pages,
                chunk_pages,
            )
            chunks_root = os.path.join(output_dir, "adobe_extract_chunks")
            os.makedirs(chunks_root, exist_ok=True)
            chunk_structured: List[Dict[str, Any]] = []
            chunk_first_pages: List[int] = []
            # Work queue of 0-based [start, end) ranges.
            pending_ranges: List[tuple[int, int]] = [
                (start, min(start + chunk_pages, total_pages))
                for start in range(0, total_pages, chunk_pages)
            ]

            while pending_ranges:
                start, end = pending_ranges.pop(0)
                size = end - start
                first_1 = start + 1
                chunk_pdf = os.path.join(chunks_root, f"pages_{first_1}_{end}.pdf")
                chunk_work = os.path.join(chunks_root, f"work_{first_1}_{end}")
                self._write_pdf_pages(input_path, chunk_pdf, start, end)
                try:
                    sd = self._extract_one_pdf_with_services(
                        pdf_services, chunk_pdf, chunk_work
                    )
                    chunk_structured.append(sd)
                    chunk_first_pages.append(first_1)
                except Exception as e:
                    if self._is_adobe_timeout_error(e) and size > min_chunk_pages:
                        mid = start + max(1, size // 2)
                        logger.warning(
                            "Adobe timeout on pages %s-%s (size=%s). Splitting into %s-%s and %s-%s",
                            first_1,
                            end,
                            size,
                            first_1,
                            mid,
                            mid + 1,
                            end,
                        )
                        pending_ranges.insert(0, (mid, end))
                        pending_ranges.insert(0, (start, mid))
                        continue
                    raise

            structured_data = self._merge_chunked_structured(
                chunk_structured, chunk_first_pages
            )
            extract_dir = os.path.join(output_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)
            merged_path = os.path.join(extract_dir, "structuredData.json")
            with open(merged_path, "w", encoding="utf-8") as f:
                json.dump(structured_data, f, ensure_ascii=False)

            logger.info(
                "Successfully extracted PDF using Adobe SDK (%s chunks)",
                len(chunk_structured),
            )
            return {
                "method": "adobe_sdk",
                "structured_data": structured_data,
                "extract_dir": extract_dir,
                "extraction_chunked": True,
                "extraction_chunks": len(chunk_structured),
            }
        except Exception as e:
            logger.error(f"Adobe SDK extraction failed: {e}", exc_info=True)
            raise
    
    async def _extract_fallback(self, input_path: str, output_dir: str) -> Dict[str, Any]:
        """Fallback extraction using pdfplumber (better than pypdf alone for complex PDFs)"""
        import pdfplumber
        
        logger.info("Using fallback extraction method (pdfplumber)")
        
        extracted_data = {
            "method": "fallback",
            "elements": [],
            "pages": []
        }
        
        try:
            with pdfplumber.open(input_path) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    # Extract text with better encoding handling
                    text = page.extract_text() or ""
                    
                    # Generate unique element ID for tracking
                    element_id = f"page_{page_num}_element_0"
                    
                    page_data = {
                        "page": page_num,
                        "text": text,
                        "elements": [
                            {
                                "id": element_id,
                                "type": "text",
                                "text": text,
                                "page": page_num
                            }
                        ]
                    }
                    
                    extracted_data["pages"].append(page_data)
                    extracted_data["elements"].extend(page_data["elements"])
            
            logger.info(f"Extracted {len(extracted_data['pages'])} pages using pdfplumber")
            return extracted_data
            
        except Exception as e:
            logger.error(f"pdfplumber extraction failed: {e}, falling back to pypdf", exc_info=True)
            return await self._extract_with_pypdf2(input_path, output_dir)

    async def _extract_with_pypdf2(self, input_path: str, output_dir: str) -> Dict[str, Any]:
        """Last resort extraction using pypdf."""
        from pypdf import PdfReader

        logger.warning("Using pypdf as last resort (may have encoding issues)")

        extracted_data = {
            "method": "pypdf_fallback",
            "elements": [],
            "pages": [],
        }

        try:
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
                                "page": page_num
                            }
                        ]
                    }
                    
                    extracted_data["pages"].append(page_data)
                    extracted_data["elements"].extend(page_data["elements"])
            
            return extracted_data
            
        except Exception as e:
            logger.error(f"pypdf extraction failed: {e}", exc_info=True)
            raise
    
    async def ocr_pdf(self, input_path: str, output_path: str) -> str:
        """
        Perform OCR on scanned PDF
        
        Args:
            input_path: Path to input PDF
            output_path: Path for output searchable PDF
            
        Returns:
            Path to searchable PDF
        """
        if not self.has_credentials:
            raise RuntimeError(
                "Adobe OCR requires credentials. "
                "Set ADOBE_CLIENT_ID and ADOBE_CLIENT_SECRET in backend/.env."
            )

        # IMPORTANT: fallback is intentionally disabled for now.
        return await self._ocr_with_adobe_sdk(input_path, output_path)
    
    async def _ocr_with_adobe_sdk(self, input_path: str, output_path: str) -> str:
        """Perform OCR using Adobe PDF Services SDK (4.x: PDFServices + OCRPDFJob)."""
        try:
            from adobe.pdfservices.operation.pdf_services_media_type import PDFServicesMediaType
            from adobe.pdfservices.operation.pdfjobs.jobs.ocr_pdf_job import OCRPDFJob
            from adobe.pdfservices.operation.pdfjobs.params.ocr_pdf.ocr_params import OCRParams
            from adobe.pdfservices.operation.pdfjobs.result.ocr_pdf_result import OCRPDFResult

            pdf_services = self._build_pdf_services(self.client_id, self.client_secret)

            with open(input_path, "rb") as f:
                pdf_bytes = f.read()
            input_asset = pdf_services.upload(
                BytesIO(pdf_bytes), PDFServicesMediaType.PDF.mime_type
            )

            ocr_params = OCRParams(ocr_locale=self._resolve_ocr_locale())
            ocr_pdf_job = OCRPDFJob(input_asset=input_asset, ocr_pdf_params=ocr_params)
            location = pdf_services.submit(ocr_pdf_job)
            pdf_services_response = pdf_services.get_job_result(location, OCRPDFResult)
            result_asset = pdf_services_response.get_result().get_asset()
            stream_asset = pdf_services.get_content(result_asset)

            with open(output_path, "wb") as out:
                out.write(self._bytes_from_stream_asset(stream_asset))

            logger.info("Successfully performed OCR using Adobe SDK")
            return output_path

        except Exception as e:
            logger.error(f"Adobe SDK OCR failed: {e}", exc_info=True)
            raise
