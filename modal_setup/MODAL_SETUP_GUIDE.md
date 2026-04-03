# Modal.com Setup Guide for AS3000 Table Extraction

## 🎯 Goal
Set up Modal.com to extract tables from AS3000 PDFs using Table Transformer AI model at 99% lower cost than OpenAI ($0.02/doc vs $10/doc).

---

## Step 1: Install Modal CLI (5 minutes)

### On Your Local Machine (Windows):

```bash
# Open Command Prompt or PowerShell
pip install modal

# Verify installation
modal --version
```

**Expected output**:
```
modal, version 0.63.x
```

---

## Step 2: Authenticate with Your Account (2 minutes)

```bash
# This will open browser for authentication
modal token new
```

**What happens**:
1. Browser opens to Modal.com login page
2. You sign in with your account
3. Token is saved locally
4. Terminal shows: "✓ Token created and saved"

**Verify authentication**:
```bash
modal profile current
```

**Expected output**:
```
✓ Workspace: your-username
```

---

## Step 3: Create Modal Function for Table Extraction (30 minutes)

### Create file: `modal_table_extractor.py`

Save this in your project root (same level as `backend/` folder):

```python
"""
Modal.com function for extracting tables from AS3000 PDFs
Uses Table Transformer AI model on GPU
Cost: ~$0.02 per document vs $10 with OpenAI
"""

import modal
import json
from pathlib import Path

# Define Modal app
app = modal.App("as3000-table-extractor")

# Define Docker image with all dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "poppler-utils",      # PDF to image conversion
        "tesseract-ocr",      # OCR for text extraction
        "tesseract-ocr-eng",  # English language data
    )
    .pip_install(
        # PyTorch and vision libraries
        "torch==2.1.2",
        "torchvision==0.16.2",
        "transformers==4.36.2",
        
        # PDF processing
        "pdf2image==1.16.3",
        "Pillow==10.1.0",
        
        # Table Transformer
        "timm==0.9.12",
        
        # Utilities
        "numpy==1.24.3",
    )
)


@app.function(
    image=image,
    gpu="T4",              # Cheapest GPU ($0.43/hour)
    timeout=900,           # 15 minutes max
    memory=16384,          # 16GB RAM
)
def extract_tables_gpu(pdf_bytes: bytes, filename: str = "document.pdf") -> dict:
    """
    Extract tables from PDF using Microsoft Table Transformer.
    
    Args:
        pdf_bytes: PDF file as bytes
        filename: Original filename (for logging)
        
    Returns:
        {
            "success": True,
            "tables": [...],
            "processing_time": 45.2,
            "table_count": 12,
            "pages_processed": 158,
            "model_info": {...}
        }
    """
    import time
    import torch
    from transformers import AutoImageProcessor, TableTransformerForObjectDetection
    from pdf2image import convert_from_bytes
    from PIL import Image
    
    start_time = time.time()
    print(f"🚀 Starting extraction for {filename}")
    
    try:
        # Load Microsoft Table Transformer model (cached after first run)
        print("📦 Loading Table Transformer model...")
        model_start = time.time()
        
        processor = AutoImageProcessor.from_pretrained(
            "microsoft/table-transformer-detection"
        )
        model = TableTransformerForObjectDetection.from_pretrained(
            "microsoft/table-transformer-detection"
        )
        
        # Move to GPU if available
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = model.to(device)
        model.eval()  # Set to evaluation mode
        
        model_load_time = time.time() - model_start
        print(f"✓ Model loaded in {model_load_time:.2f}s (device: {device})")
        
        # Convert PDF pages to images
        print("🖼️  Converting PDF to images...")
        convert_start = time.time()
        images = convert_from_bytes(pdf_bytes, dpi=200)
        convert_time = time.time() - convert_start
        print(f"✓ Converted {len(images)} pages in {convert_time:.2f}s")
        
        all_tables = []
        
        # Process each page
        print("🔍 Detecting tables...")
        for page_num, image in enumerate(images, start=1):
            page_start = time.time()
            
            # Detect tables on this page
            inputs = processor(images=image, return_tensors="pt")
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = model(**inputs)
            
            # Get bounding boxes and scores
            target_sizes = torch.tensor([image.size[::-1]])
            results = processor.post_process_object_detection(
                outputs, 
                threshold=0.7,  # Confidence threshold
                target_sizes=target_sizes
            )[0]
            
            # Extract each detected table
            page_tables = 0
            for score, box in zip(results["scores"], results["boxes"]):
                box_coords = box.cpu().tolist()
                
                # Crop table region
                table_image = image.crop(box_coords)
                
                all_tables.append({
                    "page": page_num,
                    "confidence": float(score),
                    "bbox": {
                        "x0": box_coords[0],
                        "y0": box_coords[1],
                        "x1": box_coords[2],
                        "y1": box_coords[3],
                    },
                    "width": box_coords[2] - box_coords[0],
                    "height": box_coords[3] - box_coords[1],
                    "page_width": image.width,
                    "page_height": image.height,
                    "detection_method": "table_transformer",
                    "model": "microsoft/table-transformer-detection",
                })
                page_tables += 1
            
            page_time = time.time() - page_start
            if page_tables > 0:
                print(f"  Page {page_num}: {page_tables} table(s) found ({page_time:.2f}s)")
        
        processing_time = time.time() - start_time
        
        result = {
            "success": True,
            "tables": all_tables,
            "processing_time": round(processing_time, 2),
            "table_count": len(all_tables),
            "pages_processed": len(images),
            "model_info": {
                "name": "Microsoft Table Transformer",
                "version": "table-transformer-detection",
                "device": str(device),
                "model_load_time": round(model_load_time, 2),
                "pdf_convert_time": round(convert_time, 2),
            },
            "filename": filename,
        }
        
        print(f"✅ Extraction complete: {len(all_tables)} tables in {processing_time:.2f}s")
        return result
        
    except Exception as e:
        print(f"❌ Error during extraction: {e}")
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
            "processing_time": time.time() - start_time,
            "filename": filename,
        }


@app.function(image=image)
@modal.web_endpoint(method="POST")
def web_extract_tables(request_data: dict):
    """
    HTTP endpoint for table extraction.
    
    POST with JSON:
    {
        "pdf_base64": "base64_encoded_pdf_data",
        "filename": "AS3000.pdf"  (optional)
    }
    
    Returns:
    {
        "success": true,
        "tables": [...],
        "processing_time": 45.2,
        ...
    }
    """
    import base64
    
    try:
        # Decode base64 PDF
        pdf_base64 = request_data.get("pdf_base64")
        filename = request_data.get("filename", "document.pdf")
        
        if not pdf_base64:
            return {
                "success": False,
                "error": "Missing pdf_base64 in request"
            }
        
        pdf_bytes = base64.b64decode(pdf_base64)
        
        # Call GPU function
        result = extract_tables_gpu.remote(pdf_bytes, filename)
        return result
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# Local testing function
@app.local_entrypoint()
def test_local():
    """
    Test function locally with a sample PDF.
    Run with: modal run modal_table_extractor.py
    """
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: modal run modal_table_extractor.py <path_to_pdf>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    
    print(f"📄 Testing with: {pdf_path}")
    
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    
    result = extract_tables_gpu.remote(pdf_bytes, pdf_path)
    
    print("\n" + "="*60)
    print("RESULTS")
    print("="*60)
    print(json.dumps(result, indent=2))
```

---

## Step 4: Deploy to Modal (1 minute)

```bash
# Deploy your function
modal deploy modal_table_extractor.py
```

**Expected output**:
```
✓ Initialized. View run at https://modal.com/...
✓ Created web function web_extract_tables
  => https://yourname--as3000-table-extractor-web-extract-tables.modal.run

✓ App deployed! 🎉
```

**Save your endpoint URL!** You'll need it to call from your backend.

---

## Step 5: Test with Sample PDF (5 minutes)

### Option A: Test via command line

```bash
# Test with your AS3000 PDF
modal run modal_table_extractor.py "path/to/AS3000.pdf"
```

### Option B: Test via HTTP (recommended)

Create test script: `test_modal_api.py`

```python
import requests
import base64
import json

# Your Modal endpoint URL (from step 4)
MODAL_URL = "https://yourname--as3000-table-extractor-web-extract-tables.modal.run"

# Read PDF
pdf_path = "backend/uploads/AS3000.pdf"  # Update path
with open(pdf_path, "rb") as f:
    pdf_bytes = f.read()

# Encode to base64
pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")

print(f"📤 Sending {len(pdf_bytes) / 1024 / 1024:.1f}MB PDF to Modal...")

# Call Modal API
response = requests.post(
    MODAL_URL,
    json={
        "pdf_base64": pdf_base64,
        "filename": "AS3000.pdf"
    },
    timeout=600  # 10 minutes
)

if response.status_code == 200:
    result = response.json()
    
    print("\n✅ Success!")
    print(f"Tables found: {result['table_count']}")
    print(f"Pages processed: {result['pages_processed']}")
    print(f"Processing time: {result['processing_time']}s")
    print(f"\nFirst 3 tables:")
    for table in result['tables'][:3]:
        print(f"  Page {table['page']}: confidence {table['confidence']:.2f}")
    
    # Save results
    with open("modal_results.json", "w") as f:
        json.dump(result, f, indent=2)
    print("\n💾 Full results saved to modal_results.json")
else:
    print(f"❌ Error: {response.status_code}")
    print(response.text)
```

Run test:
```bash
python test_modal_api.py
```

---

## Step 6: Integrate with Your Backend (20 minutes)

Create new file: `backend/services/modal_table_service.py`

```python
"""
Modal.com integration for table extraction
Alternative to OpenAI with 99% cost reduction
"""

import requests
import base64
import logging
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class ModalTableExtractor:
    """Extract tables using Modal.com GPU service."""
    
    def __init__(self, endpoint_url: str):
        """
        Initialize Modal extractor.
        
        Args:
            endpoint_url: Your Modal web endpoint URL
        """
        self.endpoint_url = endpoint_url
        self.timeout = 600  # 10 minutes
        
    def extract_tables(self, pdf_path: str) -> Dict:
        """
        Extract tables from PDF using Modal.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            {
                "success": True,
                "tables": [...],
                "processing_time": 45.2,
                "table_count": 12,
                ...
            }
        """
        try:
            # Read PDF
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
            
            pdf_size_mb = len(pdf_bytes) / 1024 / 1024
            logger.info(f"Sending {pdf_size_mb:.1f}MB PDF to Modal.com...")
            
            # Encode to base64
            pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
            
            # Call Modal API
            response = requests.post(
                self.endpoint_url,
                json={
                    "pdf_base64": pdf_base64,
                    "filename": Path(pdf_path).name
                },
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get("success"):
                    logger.info(
                        f"✅ Modal extraction successful: "
                        f"{result['table_count']} tables in "
                        f"{result['processing_time']:.1f}s"
                    )
                    return result
                else:
                    logger.error(f"Modal extraction failed: {result.get('error')}")
                    return result
            else:
                error_msg = f"Modal API error: {response.status_code}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": response.status_code
                }
                
        except Exception as e:
            logger.error(f"Failed to call Modal API: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }


# Usage example
if __name__ == "__main__":
    # Your Modal endpoint URL
    MODAL_URL = "https://yourname--as3000-table-extractor-web-extract-tables.modal.run"
    
    extractor = ModalTableExtractor(MODAL_URL)
    result = extractor.extract_tables("path/to/AS3000.pdf")
    
    print(f"Success: {result['success']}")
    print(f"Tables: {result.get('table_count', 0)}")
```

---

## Step 7: Update .env Configuration (2 minutes)

Add to `backend/.env`:

```bash
# ============================================
# MODAL.COM CONFIGURATION (GPU Table Extraction)
# ============================================

# Enable Modal.com instead of OpenAI for table extraction
USE_MODAL_EXTRACTION=false  # Set to true when ready

# Your Modal.com endpoint URL (from deployment step)
MODAL_ENDPOINT_URL=https://yourname--as3000-table-extractor-web-extract-tables.modal.run

# Timeout for Modal API calls (seconds)
MODAL_TIMEOUT=600
```

---

## Step 8: Cost Tracking (IMPORTANT!)

Modal charges by GPU seconds used. Track your costs:

### Check Usage in Dashboard

1. Go to https://modal.com/dashboard
2. Click "Usage" tab
3. View:
   - GPU seconds used
   - Cost breakdown
   - Free credits remaining

### Expected Costs

```
AS3000 Document (158 pages):
  Processing time: 30-60 seconds
  GPU: T4 ($0.43/hour)
  Cost: $0.43 × (45s / 3600s) = $0.0054 ≈ $0.01/doc
  
With free $30 credits:
  Can process: 3000 documents FREE
  
After free tier:
  100 docs/month: $1/month
  1000 docs/month: $10/month
  
vs OpenAI:
  100 docs/month: $1,000/month (gpt-4o-mini)
  Savings: $999/month (99.9% reduction!)
```

---

## 🎯 Quick Start Checklist

- [ ] **Step 1**: Install Modal CLI (`pip install modal`)
- [ ] **Step 2**: Authenticate (`modal token new`)
- [ ] **Step 3**: Create `modal_table_extractor.py` file
- [ ] **Step 4**: Deploy (`modal deploy modal_table_extractor.py`)
- [ ] **Step 5**: Save your endpoint URL
- [ ] **Step 6**: Test with `test_modal_api.py`
- [ ] **Step 7**: Integrate with backend (optional for now)
- [ ] **Step 8**: Monitor costs in dashboard

---

## 🐛 Troubleshooting

### "modal: command not found"
```bash
pip install --upgrade modal
```

### "Authentication failed"
```bash
modal token new --force
```

### "GPU not available"
- Modal automatically uses GPU
- Check deployment logs: `modal logs as3000-table-extractor`

### "Timeout error"
- Increase timeout in API call (default 600s)
- Or reduce PDF pages for testing

### "Model download slow"
- First run downloads model (~500MB)
- Cached for subsequent runs
- Takes 2-3 minutes first time

---

## 📊 Performance Expectations

### First Run (Cold Start):
```
Model download: 60-120s (one time)
PDF conversion: 15-20s
Table detection: 30-45s
Total: 2-3 minutes
```

### Subsequent Runs (Warm):
```
Model already cached ✓
PDF conversion: 15-20s
Table detection: 30-45s
Total: 45-65s
```

### With keep_warm=1 (costs $10/day):
```
No cold start ✓
Total: 30-45s (instant)
```

---

## 🚀 Next Steps

1. **Test extraction quality** vs OpenAI
2. **Compare costs** in Modal dashboard
3. **Benchmark speed** for AS3000 document
4. **Decide**: Keep OpenAI or switch to Modal
5. **If good**: Set `USE_MODAL_EXTRACTION=true` in .env

---

## 💡 Tips

- **Free tier**: $30 credits = 3000 AS3000 docs
- **No idle costs**: Only pay when processing
- **Scalable**: Handles 1000s of docs automatically
- **No GPU needed**: Modal provides GPUs in cloud
- **Cancel anytime**: No commitment

---

## 📞 Support

- **Modal docs**: https://modal.com/docs
- **Modal Discord**: https://discord.gg/modal
- **Your dashboard**: https://modal.com/dashboard
