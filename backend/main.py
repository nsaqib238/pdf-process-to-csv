"""
FastAPI backend for PDF processing pipeline
"""
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uuid
from pathlib import Path
import logging

from services.pdf_processor import PDFProcessor
from services.modal_service import ModalService
from config import settings

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed from INFO to DEBUG for better diagnostics
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Console output
        logging.FileHandler('backend_logs.txt', mode='a')  # File output
    ]
)
# pdfplumber pulls pdfminer; at DEBUG it spams millions of lines and hides pipeline logs.
logging.getLogger("pdfminer").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Log startup information
logger.info("="*80)
logger.info("PDF Processing Pipeline Starting...")
logger.info("="*80)

app = FastAPI(title="PDF Structure Extraction Pipeline")

# CORS: browser calls from Next (3000) to API (8000) are cross-origin.
# allow_credentials=True with allow_origins=["*"] is invalid per spec and can block responses.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create necessary directories
UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Initialize services
pdf_processor = PDFProcessor()
modal_service = ModalService()

logger.info("="*80)
logger.info("Server ready. Logs are being written to: backend_logs.txt")
logger.info("="*80)


@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "ok", "message": "PDF Processing Pipeline API"}


@app.post("/api/modal/warmup")
async def modal_warmup():
    """
    Warmup Modal.com container before processing PDFs.
    This initializes the container and loads the model (2-3 minutes cold start).
    Subsequent PDF uploads within 5 minutes will be fast (30-45 seconds).
    
    Returns:
        {
            "status": "warm" | "warming" | "error",
            "message": "Status message",
            "model_loaded": bool,
            "warmup_time": float (seconds),
            "timestamp": float
        }
    """
    try:
        logger.info("🔥 Warmup request received")
        
        # Check if Modal is configured
        if not modal_service.is_available():
            logger.warning("⚠️  Modal.com not configured")
            return {
                "status": "error",
                "message": "Modal.com integration not configured. Set MODAL_ENDPOINT in .env",
                "model_loaded": False,
                "configured": False
            }
        
        # Call warmup
        result = modal_service.warmup()
        
        if result.get("status") == "warm":
            logger.info(
                f"✅ Modal warmup successful: {result.get('warmup_time')}s"
            )
        else:
            logger.warning(f"⚠️  Modal warmup status: {result.get('status')}")
        
        return result
        
    except Exception as e:
        error_msg = f"Warmup endpoint error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise HTTPException(status_code=500, detail=error_msg)


@app.post("/api/process-pdf")
async def process_pdf(file: UploadFile = File(...)):
    """
    Process uploaded PDF and extract structured data
    """
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    job_id = str(uuid.uuid4())
    upload_path = UPLOAD_DIR / f"{job_id}.pdf"
    output_path = OUTPUT_DIR / job_id
    max_bytes = settings.max_file_size

    try:
        # Save uploaded file (enforce max size; aligns with Adobe 100MB service limit)
        logger.info(f"Processing PDF upload: {file.filename} (Job ID: {job_id})")
        total_written = 0
        chunk_size = 1024 * 1024
        with open(upload_path, "wb") as buffer:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total_written += len(chunk)
                if total_written > max_bytes:
                    buffer.close()
                    upload_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum size of {max_bytes // (1024 * 1024)}MB",
                    )
                buffer.write(chunk)

        output_path.mkdir(exist_ok=True)
        
        # Process PDF
        result = await pdf_processor.process_pdf(
            input_path=str(upload_path),
            output_dir=str(output_path),
            job_id=job_id,
        )
        
        logger.info(f"Successfully processed PDF (Job ID: {job_id})")
        
        return {
            "job_id": job_id,
            "status": "success",
            "result": result,
            "downloads": {
                "normalized_text": f"/api/download/{job_id}/normalized_document.txt",
                "clauses_json": f"/api/download/{job_id}/clauses.json",
                "tables_json": f"/api/download/{job_id}/tables.json"
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        msg = str(e)
        logger.error(f"Error processing PDF (Job ID: {job_id}): {msg}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {msg}")


@app.post("/api/process-pdf-tables")
async def process_pdf_tables_only(file: UploadFile = File(...)):
    """
    Extract tables only: writes outputs/{job_id}/tables.json (faster; skips clauses and normalized document).
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    job_id = str(uuid.uuid4())
    upload_path = UPLOAD_DIR / f"{job_id}.pdf"
    output_path = OUTPUT_DIR / job_id
    max_bytes = settings.max_file_size

    try:
        logger.info(f"Tables-only upload: {file.filename} (Job ID: {job_id})")
        total_written = 0
        chunk_size = 1024 * 1024
        with open(upload_path, "wb") as buffer:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total_written += len(chunk)
                if total_written > max_bytes:
                    buffer.close()
                    upload_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum size of {max_bytes // (1024 * 1024)}MB",
                    )
                buffer.write(chunk)

        output_path.mkdir(exist_ok=True)
        result = await pdf_processor.process_pdf_tables_only(
            input_path=str(upload_path),
            output_dir=str(output_path),
            job_id=job_id,
        )
        logger.info(f"Tables-only finished (Job ID: {job_id})")
        return {
            "job_id": job_id,
            "status": "success",
            "mode": "tables_only",
            "result": result,
            "downloads": {
                "tables_json": f"/api/download/{job_id}/tables.json",
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        msg = str(e)
        logger.error(f"Tables-only error (Job ID: {job_id}): {msg}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error extracting tables: {msg}")


@app.get("/api/download/{job_id}/{filename}")
async def download_file(job_id: str, filename: str):
    """
    Download processed output files
    """
    file_path = OUTPUT_DIR / job_id / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type='application/octet-stream'
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
