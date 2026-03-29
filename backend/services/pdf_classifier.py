"""
PDF classification module - detect scanned vs text-based PDFs
"""
from pypdf import PdfReader
import logging
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)


class PDFClassifier:
    """Classify PDFs as scanned or text-based"""
    
    def __init__(self, text_threshold: int = 50):
        """
        Initialize classifier
        
        Args:
            text_threshold: Minimum characters per page to consider text-based
        """
        self.text_threshold = text_threshold
    
    def classify(self, pdf_path: str) -> Tuple[str, dict]:
        """
        Classify PDF as 'scanned' or 'text-based'
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Tuple of (classification, metadata)
        """
        try:
            with open(pdf_path, 'rb') as file:
                reader = PdfReader(file)
                
                num_pages = len(reader.pages)
                total_text_chars = 0
                pages_with_text = 0
                
                # Sample up to 5 pages for efficiency
                sample_size = min(5, num_pages)
                sample_indices = [
                    0,  # First page
                    num_pages // 4,  # Quarter
                    num_pages // 2,  # Middle
                    3 * num_pages // 4,  # Three quarters
                    num_pages - 1  # Last page
                ][:sample_size]
                
                for idx in sample_indices:
                    try:
                        page = reader.pages[idx]
                        text = page.extract_text() or ""
                        text_chars = len(text.strip())
                        total_text_chars += text_chars
                        
                        if text_chars > self.text_threshold:
                            pages_with_text += 1
                            
                    except Exception as e:
                        logger.warning(f"Error extracting text from page {idx}: {e}")
                
                avg_chars_per_page = total_text_chars / sample_size if sample_size > 0 else 0
                text_page_ratio = pages_with_text / sample_size if sample_size > 0 else 0
                
                # Classification logic
                if avg_chars_per_page > self.text_threshold and text_page_ratio > 0.6:
                    classification = "text-based"
                else:
                    classification = "scanned"
                
                metadata = {
                    "num_pages": num_pages,
                    "sampled_pages": sample_size,
                    "avg_chars_per_page": avg_chars_per_page,
                    "text_page_ratio": text_page_ratio,
                    "classification": classification
                }
                
                logger.info(
                    f"PDF classified as '{classification}': "
                    f"{num_pages} pages, avg {avg_chars_per_page:.1f} chars/page"
                )
                
                return classification, metadata
                
        except Exception as e:
            logger.error(f"Error classifying PDF: {e}", exc_info=True)
            # Default to scanned if classification fails
            return "scanned", {"error": str(e), "classification": "scanned"}
