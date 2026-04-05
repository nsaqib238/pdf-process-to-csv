"""
Modal.com Complete PDF Extractor for AS3000 Standards
======================================================
Extracts both TABLES and CLAUSES in a single endpoint.

TABLES: Microsoft Table Transformer + Tesseract OCR (GPU-based)
CLAUSES: Rule-based parser with regex + state machine (deterministic, $0 cost)

Returns complete clauses.json and tables.json structures.
Cost: ~$0.006/doc (99.9% cheaper than GPT-4 approach)
"""

import modal
import json
import re
from typing import List, Dict, Any

# Define Modal app
app = modal.App("as3000-pdf-extractor")

# Docker image with all dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "poppler-utils",      # PDF to image conversion
        "libgl1-mesa-glx",    # OpenCV dependencies
        "libglib2.0-0",
        "libgomp1",           # Required for PaddlePaddle
    )
    .pip_install(
        # Table extraction (GPU models)
        "torch==2.1.2",
        "torchvision==0.16.2",
        "transformers==4.36.2",
        "pdf2image==1.16.3",
        "Pillow==10.1.0",
        "timm==0.9.12",
        "numpy==1.24.3",
        "opencv-python==4.8.1.78",
        # PaddleOCR for high-quality text extraction (replaces Tesseract)
        "paddleocr==2.7.3",
        "paddlepaddle==2.6.0",
        # Clause extraction (rule-based parser)
        "pypdf==4.0.1",
        # Web framework
        "fastapi[standard]==0.115.0",
    )
)


# ============================================================================
# TABLES: GPU-Based Extraction (Microsoft Table Transformer)
# ============================================================================

def extract_tables_from_pdf(pdf_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Extract complete tables using Table Transformer + OCR.
    
    Returns:
        {
            "success": True,
            "tables": [
                {
                    "page": 1,
                    "table_number": "3.1",
                    "title": "Installation methods",
                    "header_rows": [[...], [...]],
                    "data_rows": [[...], [...]],
                    "confidence": 0.95,
                    "bbox": {...},
                    ...
                }
            ],
            "table_count": 12,
            "processing_time": 45.2
        }
    """
    import time
    import torch
    import numpy as np
    import cv2
    import pytesseract
    from transformers import AutoImageProcessor, TableTransformerForObjectDetection
    from pdf2image import convert_from_bytes
    from PIL import Image
    
    start_time = time.time()
    print(f"📊 Starting table extraction for {filename}")
    
    try:
        # Load models
        print("  Loading Table Transformer models...")
        detection_processor = AutoImageProcessor.from_pretrained(
            "microsoft/table-transformer-detection"
        )
        detection_model = TableTransformerForObjectDetection.from_pretrained(
            "microsoft/table-transformer-detection"
        )
        structure_processor = AutoImageProcessor.from_pretrained(
            "microsoft/table-transformer-structure-recognition"
        )
        structure_model = TableTransformerForObjectDetection.from_pretrained(
            "microsoft/table-transformer-structure-recognition"
        )
        
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        detection_model = detection_model.to(device)
        structure_model = structure_model.to(device)
        detection_model.eval()
        structure_model.eval()
        
        # Convert PDF to images
        print("  Converting PDF to images...")
        # Use 200 DPI - good balance between quality and performance
        images = convert_from_bytes(pdf_bytes, dpi=200)
        
        # Initialize PaddleOCR (once for all tables)
        print("  Initializing PaddleOCR...")
        from paddleocr import PaddleOCR
        ocr_engine = PaddleOCR(
            use_angle_cls=True,  # Enable text angle detection
            lang='en',           # English language
            use_gpu=torch.cuda.is_available(),  # Use GPU if available
            show_log=False       # Suppress verbose logs
        )
        
        all_tables = []
        
        # Process each page
        print("  Detecting and extracting tables...")
        for page_num, image in enumerate(images, start=1):
            # Detect table regions
            inputs = detection_processor(images=image, return_tensors="pt")
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = detection_model(**inputs)
            
            target_sizes = torch.tensor([image.size[::-1]])
            detection_results = detection_processor.post_process_object_detection(
                outputs, threshold=0.7, target_sizes=target_sizes
            )[0]
            
            # Process each detected table
            for detection_score, detection_box in zip(
                detection_results["scores"], detection_results["boxes"]
            ):
                box_coords = detection_box.cpu().tolist()
                x0, y0, x1, y1 = box_coords
                table_image = image.crop((x0, y0, x1, y1))
                
                # Extract caption
                caption_info = extract_table_caption(image, (x0, y0, x1, y1), page_num)
                
                # Recognize structure
                structure_data = recognize_table_structure(
                    table_image, structure_processor, structure_model, device
                )
                
                # Extract content with PaddleOCR
                table_content = extract_table_content(table_image, structure_data, ocr_engine)
                
                # Build table result
                table_result = {
                    "page": page_num,
                    "table_number": caption_info.get("table_number"),
                    "title": caption_info.get("title"),
                    "confidence": float(detection_score),
                    "bbox": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
                    "header_rows": table_content.get("header_rows", []),
                    "data_rows": table_content.get("data_rows", []),
                    "row_count": table_content.get("row_count", 0),
                    "column_count": table_content.get("column_count", 0),
                    "has_merged_cells": structure_data.get("has_merged_cells", False),
                    "extraction_method": "table_transformer_paddleocr",
                }
                all_tables.append(table_result)
        
        processing_time = time.time() - start_time
        print(f"  ✅ Extracted {len(all_tables)} tables in {processing_time:.2f}s")
        
        return {
            "success": True,
            "tables": all_tables,
            "table_count": len(all_tables),
            "processing_time": round(processing_time, 2),
        }
        
    except Exception as e:
        print(f"  ❌ Table extraction error: {e}")
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
            "tables": [],
            "table_count": 0,
        }


def extract_table_caption(page_image, table_bbox, page_num):
    """Extract table number and title from caption region above table using PaddleOCR."""
    from paddleocr import PaddleOCR
    
    x0, y0, x1, y1 = table_bbox
    caption_y0 = max(0, y0 - 100)
    caption_y1 = y0
    caption_region = page_image.crop((x0, caption_y0, x1, caption_y1))
    
    try:
        # Initialize PaddleOCR for caption
        ocr = PaddleOCR(use_angle_cls=True, lang='en', use_gpu=False, show_log=False)
        
        # Convert PIL to numpy array
        import numpy as np
        caption_array = np.array(caption_region)
        
        # Run OCR
        result = ocr.ocr(caption_array, cls=True)
        
        # Extract text from result
        caption_text = ""
        if result and result[0]:
            caption_text = ' '.join([line[1][0] for line in result[0]])
        
        caption_text = caption_text.strip()
        
        table_number = None
        title = None
        
        # Try to find table number
        number_patterns = [
            r'TABLE\s+([A-Z]?\d+\.?\d*)',
            r'Table\s+([A-Z]?\d+\.?\d*)',
            r'^([A-Z]?\d+\.?\d*)\s*[-–—]',
            r'^([A-Z]?\d+\.?\d*)\s+\w',
        ]
        
        for pattern in number_patterns:
            match = re.search(pattern, caption_text, re.IGNORECASE)
            if match:
                table_number = match.group(1).strip()
                title = caption_text[match.end():].strip()
                title = re.sub(r'^[-–—:\s]+', '', title)
                if len(title) < 3:
                    title = None
                break
        
        return {
            "table_number": table_number,
            "title": title if title and len(title) > 3 else None
        }
    except Exception as e:
        return {"table_number": None, "title": None}


def recognize_table_structure(table_image, processor, model, device):
    """Recognize table structure: rows, columns, headers."""
    import torch
    
    try:
        inputs = processor(images=table_image, return_tensors="pt")
        inputs = {k: v.to(device) for k, v in inputs.items()}
        
        with torch.no_grad():
            outputs = model(**inputs)
        
        target_sizes = torch.tensor([table_image.size[::-1]])
        results = processor.post_process_object_detection(
            outputs, threshold=0.5, target_sizes=target_sizes
        )[0]
        
        rows = []
        columns = []
        column_headers = []
        
        for score, label_id, box in zip(results["scores"], results["labels"], results["boxes"]):
            box_coords = box.cpu().tolist()
            element = {"bbox": box_coords, "confidence": float(score)}
            label = model.config.id2label[label_id.item()]
            
            if label == "table row":
                rows.append(element)
            elif label == "table column":
                columns.append(element)
            elif label == "table column header":
                column_headers.append(element)
        
        rows.sort(key=lambda r: r["bbox"][1])
        columns.sort(key=lambda c: c["bbox"][0])
        
        has_merged_cells = any(
            abs(r1["bbox"][1] - r2["bbox"][1]) < 5
            for i, r1 in enumerate(rows)
            for r2 in rows[i+1:i+2]
        ) if len(rows) > 1 else False
        
        return {
            "rows": rows,
            "columns": columns,
            "column_headers": column_headers,
            "has_merged_cells": has_merged_cells,
            "confidence": float(results["scores"].mean()) if len(results["scores"]) > 0 else 0.0,
        }
    except Exception as e:
        return {"rows": [], "columns": [], "column_headers": [], "has_merged_cells": False, "confidence": 0.0}


def extract_table_content(table_image, structure_data, ocr_engine):
    """Extract text content from table cells using PaddleOCR."""
    import numpy as np
    import cv2
    
    rows = structure_data.get("rows", [])
    columns = structure_data.get("columns", [])
    column_headers = structure_data.get("column_headers", [])
    
    if len(rows) == 0 or len(columns) == 0:
        return extract_table_content_fallback(table_image, ocr_engine)
    
    try:
        # Convert PIL to OpenCV format
        img_cv = cv2.cvtColor(np.array(table_image), cv2.COLOR_RGB2BGR)
        
        header_rows = []
        data_rows = []
        
        # Determine header row count
        header_row_count = 0
        if len(column_headers) > 0:
            max_header_y = max(h["bbox"][3] for h in column_headers)
            header_row_count = sum(1 for row in rows if row["bbox"][1] < max_header_y)
            header_row_count = max(1, min(header_row_count, 3))
        else:
            header_row_count = 1
        
        # Extract text from each cell
        for row_idx, row in enumerate(rows):
            row_cells = []
            for col in columns:
                cell_x0 = max(0, int(col["bbox"][0]))
                cell_y0 = max(0, int(row["bbox"][1]))
                cell_x1 = min(img_cv.shape[1], int(col["bbox"][2]))
                cell_y1 = min(img_cv.shape[0], int(row["bbox"][3]))
                
                if cell_x1 <= cell_x0 or cell_y1 <= cell_y0:
                    row_cells.append("")
                    continue
                
                cell_img = img_cv[cell_y0:cell_y1, cell_x0:cell_x1]
                
                # Use PaddleOCR for text extraction
                try:
                    result = ocr_engine.ocr(cell_img, cls=True)
                    if result and result[0]:
                        # Extract text from all detected text boxes in cell
                        cell_text = ' '.join([line[1][0] for line in result[0]])
                    else:
                        cell_text = ""
                except:
                    cell_text = ""
                
                cell_text = cell_text.strip()
                row_cells.append(cell_text)
            
            if row_idx < header_row_count:
                header_rows.append(row_cells)
            else:
                data_rows.append(row_cells)
        
        return {
            "header_rows": header_rows,
            "data_rows": data_rows,
            "row_count": len(rows),
            "column_count": len(columns),
        }
    except Exception as e:
        return extract_table_content_fallback(table_image, ocr_engine)


def extract_table_content_fallback(table_image, ocr_engine):
    """Fallback: simple line-by-line OCR when structure recognition fails using PaddleOCR."""
    import numpy as np
    
    try:
        # Convert PIL to numpy
        img_array = np.array(table_image)
        
        # Use PaddleOCR for full table extraction
        result = ocr_engine.ocr(img_array, cls=True)
        # Extract all text lines
        lines = []
        if result and result[0]:
            for line in result[0]:
                text = line[1][0].strip()
                if text:
                    lines.append(text)
        
        if len(lines) == 0:
            return {"header_rows": [], "data_rows": [], "row_count": 0, "column_count": 0}
        
        header_rows = [lines[0].split()] if len(lines) > 0 else []
        data_rows = [line.split() for line in lines[1:]]
        
        max_cols = max([len(row) for row in header_rows + data_rows]) if (header_rows or data_rows) else 0
        
        return {
            "header_rows": header_rows,
            "data_rows": data_rows,
            "row_count": len(lines),
            "column_count": max_cols,
        }
    except Exception as e:
        return {"header_rows": [], "data_rows": [], "row_count": 0, "column_count": 0}


# ============================================================================
# CLAUSES: Rule-Based Parser (Deterministic, No AI Cost)
# ============================================================================

def extract_clauses_from_pdf(pdf_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Extract structured clauses using rule-based parser with regex + state machine.
    
    Strategy:
    - Extract full text from PDF page-by-page
    - Use regex patterns to identify clause numbers, titles, notes, exceptions
    - State machine tracks parent-child hierarchy
    - Deterministic parsing (no AI inference required)
    
    Returns:
        {
            "success": True,
            "clauses": [
                {
                    "clause_id": "uuid",
                    "clause_number": "3.6.5.1",
                    "title": "Installation methods...",
                    "parent_clause_number": "3.6.5",
                    "level": 4,
                    "page_start": 45,
                    "page_end": 46,
                    "body_text": "Cables shall be...",
                    "notes": [...],
                    "exceptions": [...],
                    "confidence": "high"
                }
            ],
            "clause_count": 245,
            "processing_time": 2.5,
            "cost_estimate": 0.0  # No AI costs!
        }
    """
    import time
    from pypdf import PdfReader
    import io
    
    start_time = time.time()
    print(f"📝 Starting clause extraction for {filename}")
    
    try:
        # Extract text from PDF
        print("  Extracting text from PDF...")
        pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
        total_pages = len(pdf_reader.pages)
        
        # Extract text page by page
        page_texts = []
        for page_num, page in enumerate(pdf_reader.pages, start=1):
            text = page.extract_text() or ""
            page_texts.append({
                "page": page_num,
                "text": text
            })
        
        print(f"  Extracted text from {total_pages} pages")
        
        # Parse using rule-based parser (inline implementation)
        print("  Parsing clauses with rule-based parser...")
        clauses = parse_clauses_rule_based(page_texts)
        
        processing_time = time.time() - start_time
        print(f"  ✅ Extracted {len(clauses)} clauses in {processing_time:.2f}s")
        print(f"  💰 Cost estimate: $0.00 (rule-based, no AI)")
        
        return {
            "success": True,
            "clauses": clauses,
            "clause_count": len(clauses),
            "processing_time": round(processing_time, 2),
            "cost_estimate": 0.0,  # No AI costs!
            "pages_processed": total_pages,
        }
        
    except Exception as e:
        print(f"  ❌ Clause extraction error: {e}")
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
            "clauses": [],
            "clause_count": 0,
        }


def parse_clauses_rule_based(page_texts: List[Dict]) -> List[Dict]:
    """
    Rule-based clause parser (inline implementation).
    Parses clauses using regex patterns and state machine.
    """
    import uuid
    
    # Regex patterns for different clause types
    numbered_pattern = re.compile(r'^(\d+(?:\.\d+)*)\s+([A-Z][^\n]+?)(?:\n|$)', re.MULTILINE)
    appendix_pattern = re.compile(r'^APPENDIX\s+([A-Z](?:\.\d+)*)\s*[-–—:]*\s*([^\n]*?)(?:\n|$)', re.MULTILINE | re.IGNORECASE)
    letter_pattern = re.compile(r'^\(([a-z])\)\s+(.+?)(?:\n|$)', re.MULTILINE)
    
    all_clauses = []
    clause_stack = []  # Track current hierarchy
    
    for page_data in page_texts:
        page_num = page_data["page"]
        text = page_data["text"]
        lines = text.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                i += 1
                continue
            
            # Try numbered clause
            match = numbered_pattern.match(line)
            if match:
                number, title = match.groups()
                body, consumed = extract_body_text(lines, i + 1)
                
                level = number.count('.') + 1
                parent_number = '.'.join(number.split('.')[:-1]) if '.' in number else None
                
                clause = {
                    "clause_id": f"clause_{uuid.uuid4().hex[:8]}",
                    "clause_number": number,
                    "title": title.strip(),
                    "body_text": body,
                    "parent_clause_number": parent_number,
                    "level": level,
                    "page_start": page_num,
                    "page_end": page_num,
                    "notes": [],
                    "exceptions": [],
                    "confidence": "high",
                    "extraction_method": "rule_based_parser",
                    "has_parent": bool(parent_number),
                    "has_body": bool(body.strip()),
                    "is_orphan_note": False,
                }
                all_clauses.append(clause)
                clause_stack = [clause]  # Update current parent
                i += consumed + 1
                continue
            
            # Try appendix clause
            match = appendix_pattern.match(line)
            if match:
                number, title = match.groups()
                appendix_number = f"Appendix {number}"
                body, consumed = extract_body_text(lines, i + 1)
                
                level = number.count('.') + 1
                parent_number = None
                if '.' in number:
                    parent_parts = number.split('.')[:-1]
                    parent_number = f"Appendix {'.'.join(parent_parts)}"
                
                clause = {
                    "clause_id": f"clause_{uuid.uuid4().hex[:8]}",
                    "clause_number": appendix_number,
                    "title": title.strip() if title else None,
                    "body_text": body,
                    "parent_clause_number": parent_number,
                    "level": level,
                    "page_start": page_num,
                    "page_end": page_num,
                    "notes": [],
                    "exceptions": [],
                    "confidence": "high",
                    "extraction_method": "rule_based_parser",
                    "has_parent": bool(parent_number),
                    "has_body": bool(body.strip()),
                    "is_orphan_note": False,
                }
                all_clauses.append(clause)
                clause_stack = [clause]
                i += consumed + 1
                continue
            
            # Try letter subclause
            match = letter_pattern.match(line)
            if match and clause_stack:
                letter, text_part = match.groups()
                parent = clause_stack[-1]
                parent_number = parent["clause_number"]
                clause_number = f"{parent_number}({letter})"
                
                body, consumed = extract_body_text(lines, i + 1, max_lines=10)
                
                clause = {
                    "clause_id": f"clause_{uuid.uuid4().hex[:8]}",
                    "clause_number": clause_number,
                    "title": None,
                    "body_text": text_part + " " + body,
                    "parent_clause_number": parent_number,
                    "level": parent["level"] + 1,
                    "page_start": page_num,
                    "page_end": page_num,
                    "notes": [],
                    "exceptions": [],
                    "confidence": "high",
                    "extraction_method": "rule_based_parser",
                    "has_parent": True,
                    "has_body": bool((text_part + " " + body).strip()),
                    "is_orphan_note": False,
                }
                all_clauses.append(clause)
                i += consumed + 1
                continue
            
            i += 1
    
    # Link parent IDs
    clause_map = {c["clause_number"]: c for c in all_clauses}
    for clause in all_clauses:
        parent_number = clause["parent_clause_number"]
        if parent_number and parent_number in clause_map:
            clause["parent_clause_id"] = clause_map[parent_number]["clause_id"]
        else:
            clause["parent_clause_id"] = None
    
    # Build full normalized text
    for clause in all_clauses:
        parts = [f"[{clause['clause_number']}]"]
        if clause['title']:
            parts[0] += f" {clause['title']}"
        if clause['body_text']:
            parts.append(clause['body_text'])
        clause["full_normalized_text"] = "\n".join(parts)
        clause["body_with_subitems"] = clause["body_text"]
    
    return all_clauses


def extract_body_text(lines: List[str], start_idx: int, max_lines: int = 50) -> tuple:
    """Extract body text until next clause or empty line."""
    body_lines = []
    consumed = 0
    
    numbered_pattern = re.compile(r'^\d+(?:\.\d+)*\s+[A-Z]', re.MULTILINE)
    appendix_pattern = re.compile(r'^APPENDIX\s+[A-Z]', re.MULTILINE | re.IGNORECASE)
    letter_pattern = re.compile(r'^\([a-z]\)\s+', re.MULTILINE)
    
    for i in range(start_idx, min(start_idx + max_lines, len(lines))):
        line = lines[i].strip()
        
        if not line:  # Empty line = paragraph break
            break
        
        # Stop at next clause
        if (numbered_pattern.match(line) or 
            appendix_pattern.match(line) or 
            letter_pattern.match(line)):
            break
        
        body_lines.append(line)
        consumed += 1
    
    return " ".join(body_lines), consumed


# ============================================================================
# MAIN ENDPOINT: Extract Both Tables and Clauses
# ============================================================================

@app.function(
    image=image,
    gpu="T4",              # $0.43/hour for table extraction
    timeout=10800,         # 180 minutes (3 hours) for very large PDFs (500-700 pages)
    memory=16384,          # 16GB RAM
)
def extract_pdf_complete(pdf_bytes: bytes, filename: str = "document.pdf") -> dict:
    """
    Complete PDF extraction: TABLES (GPU) + CLAUSES (Rule-based).
    
    Args:
        pdf_bytes: PDF file as bytes
        filename: Original filename
        
    Returns:
        {
            "success": True,
            "tables": [...],  # Complete tables.json structure
            "clauses": [...],  # Complete clauses.json structure
            "table_count": 12,
            "clause_count": 245,
            "processing_time": 120.5,
            "cost_estimate": 0.006  # Only GPU costs, no AI!
        }
    """
    import time
    
    start_time = time.time()
    print(f"🚀 Starting COMPLETE PDF extraction for {filename}")
    print("=" * 70)
    
    try:
        # Extract tables (GPU-based)
        print("\n📊 STEP 1: TABLES (GPU)")
        print("-" * 70)
        tables_result = extract_tables_from_pdf(pdf_bytes, filename)
        
        # Extract clauses (Rule-based parser)
        print("\n📝 STEP 2: CLAUSES (Rule-based)")
        print("-" * 70)
        clauses_result = extract_clauses_from_pdf(pdf_bytes, filename)
        
        # Calculate total cost (only GPU, no AI costs!)
        total_cost = tables_result.get("processing_time", 0) / 3600 * 0.43  # GPU cost only
        
        processing_time = time.time() - start_time
        
        print("\n" + "=" * 70)
        print(f"✅ COMPLETE: {tables_result['table_count']} tables, {clauses_result['clause_count']} clauses")
        print(f"   Total time: {processing_time:.2f}s")
        print(f"   Total cost: ${total_cost:.4f} (GPU only, no AI costs!)")
        print("=" * 70)
        
        return {
            "success": True,
            "tables": tables_result.get("tables", []),
            "clauses": clauses_result.get("clauses", []),
            "table_count": tables_result.get("table_count", 0),
            "clause_count": clauses_result.get("clause_count", 0),
            "processing_time": round(processing_time, 2),
            "cost_estimate": round(total_cost, 4),
            "filename": filename,
        }
        
    except Exception as e:
        print(f"\n❌ EXTRACTION FAILED: {e}")
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
            "tables": [],
            "clauses": [],
            "processing_time": time.time() - start_time,
        }


# ============================================================================
# WEB ENDPOINTS
# ============================================================================

@app.function(image=image, gpu="T4", timeout=10800)
@modal.fastapi_endpoint(method="POST")
def extract(data: dict):
    """
    Main extraction endpoint - DEPRECATED: Use extract_tables + extract_clauses instead.
    
    This endpoint returns both tables and clauses but has issues with large responses
    (292 tables = 100-200MB JSON, gets truncated).
    
    POST /extract
    Body: {
        "pdf_base64": "base64_encoded_pdf",
        "filename": "document.pdf"
    }
    
    Returns: Complete extraction result with tables and clauses
    """
    import base64
    
    pdf_base64 = data.get("pdf_base64", "")
    filename = data.get("filename", "document.pdf")
    
    if not pdf_base64:
        return {
            "success": False,
            "error": "No pdf_base64 provided"
        }
    
    try:
        pdf_bytes = base64.b64decode(pdf_base64)
        result = extract_pdf_complete.remote(pdf_bytes, filename)
        return result
    except Exception as e:
        return {
            "success": False,
            "error": f"Extraction failed: {str(e)}"
        }


@app.function(image=image, gpu="T4", timeout=10800)
@modal.fastapi_endpoint(method="POST")
def extract_tables(data: dict):
    """
    Extract TABLES ONLY (avoids response size issues).
    
    POST /extract-tables
    Body: {
        "pdf_base64": "base64_encoded_pdf",
        "filename": "document.pdf"
    }
    
    Returns: {
        "success": True,
        "tables": [...],  # 292 tables
        "table_count": 292,
        "processing_time": 3444.13,
        "cost_estimate": 0.4114
    }
    """
    import base64
    
    pdf_base64 = data.get("pdf_base64", "")
    filename = data.get("filename", "document.pdf")
    
    if not pdf_base64:
        return {
            "success": False,
            "error": "No pdf_base64 provided",
            "tables": [],
            "table_count": 0
        }
    
    try:
        pdf_bytes = base64.b64decode(pdf_base64)
        result = extract_tables_from_pdf(pdf_bytes, filename)
        return result
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": f"Table extraction failed: {str(e)}",
            "traceback": traceback.format_exc(),
            "tables": [],
            "table_count": 0
        }


@app.function(image=image, timeout=300)  # No GPU needed for clauses
@modal.fastapi_endpoint(method="POST")
def extract_clauses(data: dict):
    """
    Extract CLAUSES ONLY (rule-based, no GPU).
    
    POST /extract-clauses
    Body: {
        "pdf_base64": "base64_encoded_pdf",
        "filename": "document.pdf"
    }
    
    Returns: {
        "success": True,
        "clauses": [...],  # 4219 clauses
        "clause_count": 4219,
        "processing_time": 31.13,
        "cost_estimate": 0.0
    }
    """
    import base64
    
    pdf_base64 = data.get("pdf_base64", "")
    filename = data.get("filename", "document.pdf")
    
    if not pdf_base64:
        return {
            "success": False,
            "error": "No pdf_base64 provided",
            "clauses": [],
            "clause_count": 0
        }
    
    try:
        pdf_bytes = base64.b64decode(pdf_base64)
        result = extract_clauses_from_pdf(pdf_bytes, filename)
        return result
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": f"Clause extraction failed: {str(e)}",
            "traceback": traceback.format_exc(),
            "clauses": [],
            "clause_count": 0
        }


@app.function(image=image, gpu="T4", timeout=600)
@modal.fastapi_endpoint(method="GET")
def warmup():
    """
    Warmup endpoint - loads models and initializes container.
    Call this before processing to avoid cold start delays.
    
    GET /warmup
    Returns: {"status": "warm", "warmup_time": 45.2}
    """
    import time
    import torch
    from transformers import AutoImageProcessor, TableTransformerForObjectDetection
    
    start_time = time.time()
    print("🔥 Warming up container...")
    
    try:
        # Load table detection model
        print("  Loading detection model...")
        detection_processor = AutoImageProcessor.from_pretrained(
            "microsoft/table-transformer-detection"
        )
        detection_model = TableTransformerForObjectDetection.from_pretrained(
            "microsoft/table-transformer-detection"
        )
        
        # Load structure recognition model
        print("  Loading structure model...")
        structure_processor = AutoImageProcessor.from_pretrained(
            "microsoft/table-transformer-structure-recognition"
        )
        structure_model = TableTransformerForObjectDetection.from_pretrained(
            "microsoft/table-transformer-structure-recognition"
        )
        
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        detection_model.to(device)
        structure_model.to(device)
        
        warmup_time = time.time() - start_time
        print(f"✅ Container warmed up in {warmup_time:.2f}s")
        
        return {
            "status": "warm",
            "message": "Models loaded and ready",
            "model_loaded": True,
            "warmup_time": round(warmup_time, 2),
            "device": str(device),
            "models": [
                "microsoft/table-transformer-detection",
                "microsoft/table-transformer-structure-recognition"
            ]
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "model_loaded": False
        }


@app.function(image=image)
@modal.fastapi_endpoint(method="GET")
def health():
    """
    Health check endpoint.
    
    GET /health
    Returns: {"status": "healthy"}
    """
    return {"status": "healthy", "service": "as3000-pdf-extractor"}
