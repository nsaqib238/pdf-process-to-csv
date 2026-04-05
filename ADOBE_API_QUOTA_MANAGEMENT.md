# Adobe API Quota Management

## Understanding Adobe API Usage

### API Call Counting

Adobe PDF Services free tier includes **500 document transactions per month**.

**Important**: For PDF chunking (PDFs >100 pages), each chunk counts as **1 API call**.

#### Example Calculations:

| PDF Size | Chunks | API Calls Per Upload |
|----------|--------|---------------------|
| 50 pages | 1 chunk | **1 API call** |
| 100 pages | 1 chunk | **1 API call** |
| 150 pages | 2 chunks | **2 API calls** |
| 650 pages | 7 chunks | **7 API calls** |

### Why API Usage Grows Quickly

If you're testing with large PDFs (e.g., standards documents like AS3000 with 650+ pages):
- Each upload of a 650-page PDF = **7 API calls**
- 18 uploads × 7 calls = **126 API calls**
- This can exhaust your 500-call monthly quota with just 71 large PDF uploads

### Current Chunking Strategy

The system automatically splits large PDFs into 93-page chunks to stay under Adobe's 100-page scanned PDF limit:
- **Chunk size**: 93 pages (safe buffer under 100-page limit)
- **Automatic splitting**: PDFs >100 pages are automatically chunked
- **Seamless merging**: Results are automatically merged back together

## Conserving Your Adobe API Quota

### Option 1: Disable Adobe Hybrid Mode (Recommended for Testing)

Set `ENABLE_ADOBE_HYBRID=false` in your `.env` file:

```bash
# Disable Adobe Hybrid Mode to use only Modal Tesseract OCR
ENABLE_ADOBE_HYBRID=false
```

**When to use this:**
- Testing and development with large PDFs
- When Adobe API quota is running low
- When OCR quality from Modal Tesseract is sufficient

**Trade-offs:**
- ✅ **Zero Adobe API calls** - conserves your quota
- ✅ **Still processes large PDFs** - Modal handles documents of any size
- ❌ **Lower OCR quality** - Tesseract OCR instead of Adobe's high-quality OCR
- ❌ **More OCR errors** - especially on complex fonts, scanned documents, or poor-quality PDFs

### Option 2: Upgrade Adobe Plan

If you need high-quality OCR for many large PDFs:

**Free Tier:**
- 500 document transactions/month
- Perfect for: Small projects, testing, occasional use
- Cost: $0

**Pay-as-you-go:**
- $0.05 per document transaction
- For 650-page PDF (7 chunks): ~$0.35 per upload
- Cost: Variable based on usage

**Enterprise Plans:**
- Higher quotas or unlimited usage
- Contact Adobe for pricing

### Option 3: Optimize Your Workflow

**For testing:**
1. Use `ENABLE_ADOBE_HYBRID=false` during development
2. Enable Adobe only for production/final runs

**For production:**
1. Process smaller PDFs first (≤100 pages = 1 API call)
2. Batch large PDF processing when needed
3. Monitor your API usage dashboard

## Monitoring Your Usage

### Adobe Dashboard
Check your current API usage at: https://developer.adobe.com/console

### Backend Logs
The system logs Adobe API calls:

```
🔥 Large PDF detected: 650 pages
   Will split into 7 chunks of ~93 pages
   Estimated cost: $0.392 | Time: 84s
   
   Processing chunk 1/7: pages 1-93
      ✅ Chunk 1: 93 pages extracted
   Processing chunk 2/7: pages 94-186
      ✅ Chunk 2: 93 pages extracted
   ...
✅ Chunked extraction complete: 7/7 chunks successful
```

**API calls made**: 7 (one per chunk)

## Configuration Reference

### Environment Variables

```bash
# Adobe credentials (required for hybrid mode)
ADOBE_CLIENT_ID=your_client_id_here
ADOBE_CLIENT_SECRET=your_client_secret_here
ADOBE_ORG_ID=your_org_id_here

# Enable/disable Adobe Hybrid Mode
# Default: true (best quality)
ENABLE_ADOBE_HYBRID=true
```

### Python Config (backend/config.py)

```python
class Settings(BaseSettings):
    # Adobe Hybrid Mode Control
    # Set to False to disable Adobe OCR and use only Modal Tesseract OCR
    # Useful for conserving Adobe API quota (500 requests/month free tier)
    # When disabled, processing uses Modal's Tesseract OCR for all text extraction
    enable_adobe_hybrid: bool = True
```

## Quality Comparison

### Adobe Hybrid Mode (ENABLE_ADOBE_HYBRID=true)
✅ Best OCR quality - Adobe's industry-leading OCR  
✅ Handles complex fonts and encodings  
✅ Superior scanned document processing  
✅ Fewer OCR errors in table cell text  
❌ Consumes Adobe API quota (7 calls for 650-page PDF)  

### Standard Mode (ENABLE_ADOBE_HYBRID=false)
✅ Zero Adobe API calls - unlimited usage  
✅ Still extracts table structures perfectly  
✅ Works for clean, digitally-created PDFs  
❌ Lower OCR quality - Tesseract instead of Adobe  
❌ More errors on scanned documents or complex fonts  

## Troubleshooting

### "Adobe quota exceeded" error

**Symptoms:**
- Backend logs show Adobe API errors
- Processing fails with quota-related messages

**Solution:**
1. Set `ENABLE_ADOBE_HYBRID=false` in `.env`
2. Restart backend: `python backend/main.py`
3. System will use Modal Tesseract OCR instead

### Check current mode

Look for startup logs:
```
🔥 HYBRID MODE: Adobe OCR + Modal Structure
   This will provide best-in-class text quality
```

OR

```
📊 STANDARD MODE: Modal with Tesseract OCR (Adobe disabled in config)
```

### Toggle modes without credential changes

You can keep your Adobe credentials configured but disable the feature:

```bash
# Keep credentials
ADOBE_CLIENT_ID=your_client_id_here
ADOBE_CLIENT_SECRET=your_client_secret_here
ADOBE_ORG_ID=your_org_id_here

# Disable Adobe hybrid mode
ENABLE_ADOBE_HYBRID=false
```

This lets you easily toggle between modes without removing/re-adding credentials.

## Best Practices

### For Development/Testing
1. Start with `ENABLE_ADOBE_HYBRID=false`
2. Test your pipeline with Modal Tesseract OCR
3. Enable Adobe only when you need to verify OCR quality

### For Production
1. Use `ENABLE_ADOBE_HYBRID=true` for best results
2. Monitor your API usage regularly
3. Consider upgrading to pay-as-you-go if processing many large PDFs
4. Budget ~7 API calls per 650-page document

### For Cost Optimization
1. **Small PDFs** (<100 pages): Adobe has minimal impact (1 call per PDF)
2. **Large PDFs** (>100 pages): Consider testing with Modal first
3. **Very large documents** (500+ pages): Each upload uses 5-6+ API calls

## Summary

**Quick Reference:**

| Your Situation | Recommended Setting | API Calls |
|----------------|-------------------|-----------|
| Testing/development | `ENABLE_ADOBE_HYBRID=false` | 0 |
| Small PDFs (<100 pages) | `ENABLE_ADOBE_HYBRID=true` | 1 per PDF |
| Large PDFs (650 pages) | `ENABLE_ADOBE_HYBRID=false` for testing, `true` for production | 7 per PDF |
| Quota running low | `ENABLE_ADOBE_HYBRID=false` | 0 |
| Need best OCR quality | `ENABLE_ADOBE_HYBRID=true` + consider paid plan | Variable |

**Remember**: The system works perfectly well with `ENABLE_ADOBE_HYBRID=false`. The only difference is OCR text quality - table structure detection and extraction quality remain excellent in both modes.
