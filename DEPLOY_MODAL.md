# Deploy Updated Modal Configuration

The timeout has been increased from 30 minutes to 60 minutes to handle large PDFs (70MB+).

## Changes Made

- **`extract_pdf_complete` function**: timeout increased from 1800s (30min) to 3600s (60min)
- **`/extract` web endpoint**: timeout increased to 3600s (60min)
- **`/warmup` endpoint**: timeout set to 600s (10min)

## Deploy Commands

### Option 1: Using Virtual Environment (Recommended)

**Windows:**
```bash
cd backend
.venv\Scripts\activate
modal deploy modal_extractor.py
```

**macOS/Linux:**
```bash
cd backend
source .venv/bin/activate
modal deploy ../modal_extractor.py
```

### Option 2: Direct Python Execution

**From backend directory:**
```bash
cd backend
python -m modal deploy ../modal_extractor.py
```

## Verify Deployment

After deployment, test with:

```bash
curl -X GET https://your-endpoint.modal.run/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "as3000-pdf-extractor"
}
```

## Timeout Configuration Summary

| Function | Old Timeout | New Timeout | Purpose |
|----------|-------------|-------------|---------|
| `extract_pdf_complete` | 30 min | **60 min** | Main extraction (handles 70MB PDFs) |
| `/extract` endpoint | None | **60 min** | Web endpoint wrapper |
| `/warmup` endpoint | None | **10 min** | Model loading |

## Cost Impact

With 60-minute timeout, maximum cost per document (if it takes full hour):
- GPU cost: $0.43/hour × 1 hour = $0.43
- Expected cost for 70MB PDF: ~$0.10-0.20 (processing takes ~15-30 min)

## Notes

- 70MB PDFs with ~500-700 pages can take 20-40 minutes to process
- Table extraction (GPU) is the bottleneck, not clause parsing (rule-based)
- Consider reducing DPI from 150 to 100 if still timing out
