"""
Modal.com Table Extractor for AS3000 PDFs
Uses Microsoft Table Transformer on GPU
Cost: ~$0.02/doc vs $10/doc with OpenAI (99.8% savings)
"""

import modal
import json

# Define Modal app
app = modal.App("as3000-table-extractor")

# Docker image with dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "poppler-utils",
        "tesseract-ocr",
        "tesseract-ocr-eng",
    )
    .pip_install(
        "torch==2.1.2",
        "torchvision==0.16.2",
        "transformers==4.36.2",
        "pdf2image==1.16.3",
        "Pillow==10.1.0",
        "timm==0.9.12",
        "numpy==1.24.3",
    )
)


@app.function(
    image=image,
    gpu="T4",              # $0.43/hour (cheapest)
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
            "pages_processed": 158
        }
    """
    import time
    import torch
    from transformers import AutoImageProcessor, TableTransformerForObjectDetection
    from pdf2image import convert_from_bytes
    
    start_time = time.time()
    print(f"🚀 Starting extraction for {filename}")
    
    try:
        # Load model (cached after first run)
        print("📦 Loading Table Transformer model...")
        model_start = time.time()
        
        processor = AutoImageProcessor.from_pretrained(
            "microsoft/table-transformer-detection"
        )
        model = TableTransformerForObjectDetection.from_pretrained(
            "microsoft/table-transformer-detection"
        )
        
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = model.to(device)
        model.eval()
        
        model_load_time = time.time() - model_start
        print(f"✓ Model loaded in {model_load_time:.2f}s (device: {device})")
        
        # Convert PDF to images
        print("🖼️  Converting PDF to images...")
        convert_start = time.time()
        images = convert_from_bytes(pdf_bytes, dpi=200)
        convert_time = time.time() - convert_start
        print(f"✓ Converted {len(images)} pages in {convert_time:.2f}s")
        
        all_tables = []
        
        # Detect tables on each page
        print("🔍 Detecting tables...")
        for page_num, image in enumerate(images, start=1):
            page_start = time.time()
            
            inputs = processor(images=image, return_tensors="pt")
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = model(**inputs)
            
            target_sizes = torch.tensor([image.size[::-1]])
            results = processor.post_process_object_detection(
                outputs, 
                threshold=0.7,
                target_sizes=target_sizes
            )[0]
            
            page_tables = 0
            for score, box in zip(results["scores"], results["boxes"]):
                box_coords = box.cpu().tolist()
                
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
                print(f"  Page {page_num}: {page_tables} table(s) ({page_time:.2f}s)")
        
        processing_time = time.time() - start_time
        
        print(f"✅ Complete: {len(all_tables)} tables in {processing_time:.2f}s")
        
        return {
            "success": True,
            "tables": all_tables,
            "processing_time": round(processing_time, 2),
            "table_count": len(all_tables),
            "pages_processed": len(images),
            "model_info": {
                "name": "Microsoft Table Transformer",
                "device": str(device),
                "model_load_time": round(model_load_time, 2),
            },
            "filename": filename,
        }
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
            "processing_time": time.time() - start_time,
        }


@app.function(image=image)
@modal.asgi_app()
def web_extract_tables():
    from fastapi import FastAPI, Request
    
    web_app = FastAPI()
    
    @web_app.post("/extract")
    async def extract_endpoint(request: Request):
        """
        HTTP endpoint for table extraction.
        
        POST JSON to /extract:
        {
            "pdf_base64": "base64_encoded_pdf",
            "filename": "AS3000.pdf"
        }
        
        Returns extraction results.
        """
        import base64
        
        try:
            request_data = await request.json()
            pdf_base64 = request_data.get("pdf_base64")
            filename = request_data.get("filename", "document.pdf")
            
            if not pdf_base64:
                return {
                    "success": False,
                    "error": "Missing pdf_base64 in request"
                }
            
            pdf_bytes = base64.b64decode(pdf_base64)
            result = extract_tables_gpu.remote(pdf_bytes, filename)
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    return web_app


@app.local_entrypoint()
def test_local():
    """
    Test locally: modal run modal_table_extractor.py <pdf_path>
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
