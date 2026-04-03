# 🚀 Deploy Modal.com Complete Table Extraction

**Quick deployment guide for the upgraded Modal.com table extractor**

---

## ✅ Pre-Deployment Checklist

Before deploying, ensure you have:

- [ ] Modal account with GPU access
- [ ] Modal CLI installed (`pip install modal`)
- [ ] Modal authentication completed (`modal token new`)
- [ ] `modal_table_extractor.py` with complete extraction code
- [ ] Sufficient Modal credits (T4 GPU usage)

---

## 📦 Step 1: Deploy to Modal.com

### From Your Local Machine (Windows)

```powershell
# Navigate to project directory
cd C:\path\to\your\project

# Deploy the updated extractor
modal deploy modal_table_extractor.py
```

**Expected Output:**
```
✓ Initialized. View run at https://modal.com/...
✓ Created objects.
├── 🔨 Created mount /modal_table_extractor.py
├── 🔨 Created function extract_tables_gpu.
├── 🔨 Created function keep_warm_ping.
├── 🔨 Created web_extract_tables => https://nsaqib238--as3000-table-extractor-web-extract-tables.modal.run
└── 🔨 App deployed successfully

✅ Deployed complete table extractor with structure recognition!
```

---

## 🧪 Step 2: Test the Deployment

### 2a. Test Warmup Endpoint

```powershell
# Test warmup (should load both detection + structure models)
curl https://nsaqib238--as3000-table-extractor-web-extract-tables.modal.run/warmup
```

**Expected Response:**
```json
{
  "status": "warm",
  "message": "Container initialized with detection + structure models",
  "model_loaded": true,
  "warmup_time": 45.2,
  "timestamp": 1743897234.5
}
```

### 2b. Test with Small PDF

```powershell
# Encode a test PDF to base64
$pdfBytes = [System.IO.File]::ReadAllBytes("path\to\test.pdf")
$base64Pdf = [Convert]::ToBase64String($pdfBytes)

# Call extraction endpoint
$body = @{
    pdf_base64 = $base64Pdf
    filename = "test.pdf"
} | ConvertTo-Json

Invoke-RestMethod -Uri "https://nsaqib238--as3000-table-extractor-web-extract-tables.modal.run/extract" `
    -Method Post `
    -Body $body `
    -ContentType "application/json"
```

**Expected Response:**
```json
{
  "success": true,
  "tables": [
    {
      "page": 1,
      "table_number": "3.1",
      "title": "Installation methods",
      "confidence": 0.95,
      "header_rows": [["Type", "Rating", "Application"]],
      "data_rows": [["Type A", "10A", "Indoor"]],
      "row_count": 2,
      "column_count": 3,
      "has_merged_cells": false
    }
  ],
  "table_count": 1,
  "processing_time": 12.3,
  "pages_processed": 1
}
```

---

## 🔧 Step 3: Update Backend Configuration

### Update `.env` File

```env
# Modal.com configuration
USE_MODAL_EXTRACTION=true
MODAL_ENDPOINT=https://nsaqib238--as3000-table-extractor-web-extract-tables.modal.run/extract
MODAL_TIMEOUT=1800
MODAL_FALLBACK_MODE=openai
MODAL_CONFIDENCE_THRESHOLD=0.70
```

### Restart Backend

```powershell
# Stop backend (Ctrl+C)
# Restart backend
cd backend
uvicorn main:app --reload --port 8000
```

---

## ✅ Step 4: Verify End-to-End Flow

### 4a. Warmup Modal

```powershell
curl -X POST http://localhost:8000/api/modal/warmup
```

### 4b. Upload PDF via Frontend

1. Open browser: `http://localhost:3000`
2. Click "Warm Up" button (optional, but recommended)
3. Upload a test PDF (e.g., AS3000 sample)
4. Wait for processing
5. Check results in `backend/outputs/<uuid>/tables.json`

### 4c. Verify Quality

Check the `tables.json` file:

```json
{
  "table_number": "3.1",        // ✅ Should be present (95%+)
  "title": "Installation methods",  // ✅ Should be present (90%+)
  "header_rows": [
    {
      "cells": ["Type", "Rating", "Application"],  // ✅ Clean headers
      "is_header": true
    }
  ],
  "data_rows": [
    {
      "cells": ["Type A", "10A", "Indoor"],  // ✅ Clean data
      "is_header": false
    }
  ],
  "confidence": 0.95,
  "source_method": "modal_table_transformer_structure"  // ✅ New method
}
```

---

## 📊 Step 5: Performance Monitoring

### Check Modal Dashboard

1. Go to: https://modal.com/dashboard
2. Navigate to: `as3000-table-extractor` app
3. Check metrics:
   - **GPU time:** Should be ~10 minutes per 158-page PDF
   - **Cost:** Should be ~$0.07 per document
   - **Success rate:** Should be 95%+

### Check Backend Logs

```powershell
# View backend logs
tail -f backend/backend_logs.txt
```

Look for:
```
✅ Modal.com extracted 61 tables (61 high confidence, 0 low confidence)
✅ Using Modal.com complete table data: 61 tables
✅ Processed 61 tables via Modal.com (complete extraction, no post-processing needed)
```

---

## 🐛 Troubleshooting

### Issue 1: Deployment Failed

**Error:** `ImportError: No module named 'cv2'`

**Solution:** Modal image already includes opencv-python. If still failing, check image definition:
```python
.pip_install("opencv-python==4.8.1.78")
```

### Issue 2: Timeout During Extraction

**Error:** `Modal.com request timed out after 1800s`

**Solution:** Increase timeout in `.env`:
```env
MODAL_TIMEOUT=3600  # 60 minutes
```

And in `modal_table_extractor.py`:
```python
@app.function(
    timeout=3600,  # 60 minutes
    ...
)
```

### Issue 3: Low-Quality Table Numbers

**Symptom:** Table numbers still missing (< 90%)

**Solution:** Adjust caption search region:
```python
# In extract_table_caption function
caption_y0 = max(0, y0 - 150)  # Increase from 100px to 150px
```

### Issue 4: Structure Recognition Failed

**Symptom:** Tables have empty `header_rows` or `data_rows`

**Solution:** Check fallback OCR:
```python
# Fallback should trigger automatically
# Verify in logs:
"⚠️  Structure recognition failed: ..."
"Using fallback OCR..."
```

---

## 📈 Success Metrics

After deployment, verify these metrics:

| Metric | Target | How to Check |
|--------|--------|--------------|
| **Table Numbers** | 95%+ | Count tables with `table_number != null` |
| **Titles** | 90%+ | Count tables with `title != null` |
| **Clean Headers** | 95%+ | Check `header_rows` for fragmentation |
| **Processing Time** | < 10 min | Check `processing_time` in response |
| **Cost per Doc** | ~$0.07 | Check Modal dashboard |
| **Success Rate** | 95%+ | Check `success: true` in responses |

---

## 🔄 Rollback Plan

If issues occur, rollback to detection-only version:

### 1. Deploy Old Version

```powershell
# Restore previous version from git
git checkout HEAD~1 modal_table_extractor.py

# Redeploy
modal deploy modal_table_extractor.py
```

### 2. Update Backend

```env
# Keep using Modal, but backend will do extraction
USE_MODAL_EXTRACTION=true
MODAL_ENDPOINT=https://...
```

Backend will automatically fall back to pdfplumber extraction if Modal returns incomplete data.

---

## 📝 Deployment Checklist

- [ ] Deployed `modal_table_extractor.py` successfully
- [ ] Tested warmup endpoint (returns `"model_loaded": true`)
- [ ] Tested extraction with small PDF (returns complete table data)
- [ ] Updated backend `.env` with correct endpoint
- [ ] Restarted backend server
- [ ] Tested end-to-end flow (upload → extract → verify)
- [ ] Verified table quality (95%+ table numbers, 90%+ titles)
- [ ] Checked Modal dashboard (cost ~$0.07 per doc)
- [ ] Reviewed backend logs (no errors)
- [ ] Committed changes to git

---

## 🎉 Post-Deployment

Once deployed and verified:

1. **Monitor Performance:**
   - Check Modal dashboard daily
   - Review extraction logs
   - Track quality metrics

2. **Optimize Costs:**
   - Enable business-hours warmup schedule (already configured)
   - Disable warmup for weekends if not needed

3. **Gather Feedback:**
   - Test with various PDF types
   - Note any quality issues
   - Report edge cases for improvement

---

## 📞 Support

If issues persist:

1. Check logs: `backend/backend_logs.txt`
2. Check Modal logs: https://modal.com/dashboard
3. Review documentation: `MODAL_COMPLETE_EXTRACTION.md`
4. Contact Modal support: https://modal.com/support

---

**Deployment complete! Modal.com now handles complete table extraction.** 🚀
