# AS3000 PDF Extraction System

Extract structured clauses and tables from PDF standards documents (like AS3000 2018) with 95%+ accuracy using Modal.com GPU-powered extraction.

**Input**: AS3000 2018.pdf (158 pages)  
**Output**: `clauses.json` (200-250 structured clauses), `tables.json` (12+ tables), `normalized_document.txt`

## 🎯 Quick Start

### 1. Install System Dependencies

**macOS:**
```bash
brew install python@3.12 node openjdk ghostscript
```

**Windows (with Chocolatey):**
```bash
choco install python nodejs openjdk ghostscript
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install python3.12 python3.12-venv nodejs default-jre ghostscript
```

### 2. Clone Repository

```bash
git clone git@github.com:nsaqib238/pdf-process-to-csv.git
cd pdf-process-to-csv
```

### 3. Backend Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Frontend Setup

```bash
cd ..  # Back to repository root
npm install
```

### 5. Environment Configuration

```bash
cd backend
cp .env.example .env
```

**Edit `backend/.env` with your credentials:**

```env
# Required: Modal.com endpoint (see deployment section below)
USE_MODAL_EXTRACTION=true
MODAL_ENDPOINT=https://your-username--app-name-web-extract-tables.modal.run/extract

# Optional: OpenAI API key for fallback (recommended)
OPENAI_API_KEY=sk-proj-your-key-here

# Optional: Enable AI enhancement features
ENABLE_AI_TABLE_DISCOVERY=true
ENABLE_AI_CAPTION_DETECTION=true
ENABLE_AI_STRUCTURE_VALIDATION=true
```

### 6. Deploy Modal.com (Required)

Modal.com provides 99.93% cost savings vs OpenAI ($0.006/doc vs $8-10/doc).

**Setup:**
```bash
cd backend
pip install modal
modal setup  # Opens browser for authentication
modal deploy modal_extractor.py
```

**Copy the endpoint URL and add to `.env`:**
```env
MODAL_ENDPOINT=https://your-username--as3000-table-extractor-web-extract-tables.modal.run/extract
```

## 🚀 Running the Application

### Option 1: Web UI (Full Stack)

**Terminal 1 - Start Backend:**
```bash
cd backend
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python main.py
```

**Terminal 2 - Start Frontend:**
```bash
npm run dev
```

**Access the application:**
- Frontend: http://localhost:3000
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Option 2: Command Line (Faster)

**Basic usage:**
```bash
cd backend
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m services.pdf_processor path/to/file.pdf
```

**Process specific pages:**
```bash
python -m services.pdf_processor path/to/file.pdf --max-pages 50
```

## 📁 Output Files

All outputs are saved to `backend/outputs/{job_id}/`:

- **`clauses.json`** - Structured clauses with hierarchy
- **`tables.json`** - Extracted tables with metadata
- **`normalized_document.txt`** - Human-readable text representation

### tables.json Example

```json
{
  "table_id": "t001",
  "table_number": "3.2",
  "page_start": 45,
  "header_rows": [{"cells": ["Column 1", "Column 2"]}],
  "data_rows": [{"cells": ["Data 1", "Data 2"]}],
  "source_method": "modal:table_transformer",
  "confidence": "high",
  "quality_metrics": {
    "fill_ratio": 0.92,
    "unified_score": 0.85
  }
}
```

## 🔧 API Endpoints

### Process Full PDF (Clauses + Tables)
```bash
curl -X POST http://localhost:8000/api/process-pdf \
  -F "file=@AS3000 2018.pdf"
```

### Process Tables Only (Faster)
```bash
curl -X POST http://localhost:8000/api/process-pdf-tables \
  -F "file=@AS3000 2018.pdf"
```

### Download Results
```bash
curl http://localhost:8000/api/download/{job_id}/tables.json -o tables.json
```

## 💰 Cost Comparison

| Method | Cost/Doc | Accuracy | Best For |
|--------|----------|----------|----------|
| **Modal.com** | $0.006 | 85-92% | Ruled tables, high volume |
| Modal + OpenAI fallback | $0.10-0.50 | 90-95% | Mixed table types |
| OpenAI only | $8-10 | 90-95% | Low volume, complex tables |
| Geometric only | $0 | 70-80% | Simple ruled tables |

**Free tiers:**
- Modal.com: $30 credits = ~5000 extractions
- OpenAI: $5 credits = ~1 extraction

## 🛠️ Tech Stack

- **Backend**: Python 3.12, FastAPI, pdfplumber, Camelot, Tabula
- **Frontend**: Next.js 14, TypeScript, Tailwind CSS
- **AI/GPU**: Modal.com serverless GPU (T4) with Microsoft Table Transformer
- **Optional**: OpenAI GPT-4o-mini for fallback

## ⚠️ Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'pdfplumber'` | Run `pip install -r requirements.txt` |
| `camelot import failed` | Install Java and Ghostscript, verify with `java -version` |
| `Modal authentication failed` | Run `modal setup` |
| `Modal endpoint not responding` | Wait 2-3 min for cold start, or redeploy |
| Frontend won't start | Run `npm install` from repository root |

**Verify installation:**
```bash
cd backend
python -c "import pdfplumber, camelot, tabula, modal; print('✅ All installed')"
java -version  # Should show Java 8+
gs --version   # Should show Ghostscript
```

## 📊 Performance

### With Modal.com (Recommended)
- **Coverage**: 95%+ of tables
- **Processing time**: 30-45 sec/page (after warm-up)
- **Cost**: $0.006 per document
- **Accuracy**: 85-92% (excellent for ruled tables)

### With AI Enhancement Enabled
- **Coverage**: 95%+ of tables
- **Processing time**: 2x slower
- **Cost**: ~$1.40 per 200-page PDF (Modal + OpenAI fallback)
- **Accuracy**: 90-95% (handles all table types)

### Without AI (Geometric Only)
- **Coverage**: 70-80% of tables
- **Processing time**: 2-3 sec/page
- **Cost**: $0
- **Accuracy**: 70-80% (basic ruled tables only)

## 📚 Documentation

Comprehensive guides available:
- **`COMPLETE_GUIDE.md`** - Comprehensive system documentation
- **`modal_setup/MODAL_SETUP_GUIDE.md`** - Modal.com deployment guide
- **`modal_setup/MODAL_QUICK_START.md`** - Quick start for Modal.com
- **`modal_setup/MODAL_COST_COMPARISON.md`** - Cost analysis

## 🔑 Environment Variables

### Required
```env
USE_MODAL_EXTRACTION=true
MODAL_ENDPOINT=https://your-endpoint.modal.run/extract
```

### Recommended
```env
OPENAI_API_KEY=sk-proj-your-key-here
MODAL_FALLBACK_MODE=openai
```

### Optional
```env
ENABLE_AI_TABLE_DISCOVERY=true
ENABLE_AI_CAPTION_DETECTION=true
ENABLE_AI_STRUCTURE_VALIDATION=true
AI_DISCOVERY_MODE=comprehensive
```

See `backend/.env.example` for all configuration options.

## 🐛 Getting Help

- **GitHub Issues**: https://github.com/nsaqib238/pdf-process-to-csv/issues
- **Modal.com Docs**: https://modal.com/docs
- **OpenAI API Docs**: https://platform.openai.com/docs

## 📝 License

See LICENSE file in repository.

---

**Quick Commands Reference:**

```bash
# Setup (one-time)
git clone git@github.com:nsaqib238/pdf-process-to-csv.git
cd pdf-process-to-csv/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd .. && npm install
cd backend && modal setup && modal deploy modal_extractor.py

# Run (every time)
cd backend && source .venv/bin/activate && python main.py  # Terminal 1
npm run dev  # Terminal 2 (from root)

# Access
# Frontend: http://localhost:3000
# API: http://localhost:8000
```
