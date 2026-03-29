# Adobe PDF Services Setup Guide

## Why Adobe API?

The pipeline currently uses **fallback extraction** (pdfplumber) because Adobe credentials are not configured.

### Current Behavior:
```
Adobe API (not configured) → pdfplumber → pypdf (last resort)
```

### What You're Missing Without Adobe API:

1. **Better Text Extraction**: Adobe's SDK handles complex font encodings better than open-source libraries
2. **OCR Support**: Scanned PDFs remain as images without Adobe OCR
3. **Table Detection**: Adobe provides structured table extraction with cell boundaries
4. **Document Structure**: Better detection of headers, footers, sections

### When is Fallback Good Enough?

✅ **pdfplumber works well for:**
- Text-based PDFs with standard fonts
- Simple documents with clear hierarchical numbering
- PDFs without complex tables
- Most technical standards like AS/NZS 3000

❌ **Adobe API is needed for:**
- Scanned image-based PDFs (requires OCR)
- PDFs with complex embedded fonts
- Documents with intricate table structures
- When you need the highest accuracy

## How to Enable Adobe API

### Step 1: Get Credentials

1. Go to https://developer.adobe.com/document-services/apis/pdf-services/
2. Sign up for a free trial or paid account
3. Create a new project
4. Note your **Client ID** and **Client Secret**

### Step 2: Configure Credentials

Create `backend/.env` file:

```bash
cd backend
cp .env.example .env
```

Edit `.env` and add your credentials:

```env
ADOBE_CLIENT_ID=your_actual_client_id
ADOBE_CLIENT_SECRET=your_actual_client_secret
```

### Step 3: Install Adobe SDK

```bash
cd backend
pip install pdfservices-sdk
```

### Step 4: Restart Server

```bash
# Stop current server
# Restart
python main.py
```

### Step 5: Verify

You should see in logs:
```
INFO - Successfully extracted PDF using Adobe SDK
```

Instead of:
```
WARNING - Adobe PDF Services credentials not found. Using fallback extraction method.
```

## Cost Considerations

**Adobe PDF Services Pricing:**
- Free Tier: 1,000 API calls per month
- Pay-as-you-go: $0.05 per API call after free tier
- Enterprise: Custom pricing for high volume

**For AS/NZS 3000 and similar standards:**
- The free tier (1,000 calls/month) is usually sufficient for development/testing
- pdfplumber fallback works well enough for most cases
- Only upgrade if you need OCR or have complex table requirements

## Current Status

✅ **Working right now:**
- Text extraction with pdfplumber
- Clause detection and hierarchy
- Zone classification
- Basic table extraction

❌ **Not working without Adobe:**
- OCR for scanned PDFs
- Advanced table structure detection
- Optimal handling of complex fonts

## Recommendation

**For AS/NZS 3000 PDF:** The current pdfplumber fallback should work fine if the PDF is text-based (not scanned). If you're still getting 0 clauses, the issue is likely:
1. PDF content structure (not text extraction)
2. Clause pattern matching (regex needs tuning)
3. Zone classification being too aggressive

**Test first:** Try the current setup before getting Adobe credentials. Only upgrade if you confirm the PDF requires OCR or better extraction.
