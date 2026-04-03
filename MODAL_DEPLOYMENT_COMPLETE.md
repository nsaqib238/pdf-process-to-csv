# Modal.com Deployment Guide
## Complete Tables + Clauses Extraction

**Target**: Deploy unified extractor to Modal.com  
**Time**: 10-15 minutes  
**Prerequisites**: Modal account, OpenAI API key

---

## 🎯 Quick Start (5 Steps)

### 1. Install Modal CLI
```bash
pip install modal
```

### 2. Authenticate
```bash
modal token new
# Opens browser → login with your Modal.com account
```

### 3. Create OpenAI Secret
```bash
# Replace with your actual OpenAI API key
modal secret create openai-secret OPENAI_API_KEY=sk-proj-YOUR_KEY_HERE
```

### 4. Deploy Extractor
```bash
# From project root
modal deploy modal_extractor.py

# ✅ Output will show your endpoint URL:
# → https://your-username--as3000-pdf-extractor-extract.modal.run
```

### 5. Configure Backend
```bash
cd backend

# Edit .env file
nano .env

# Add these lines:
USE_MODAL_EXTRACTION=true
MODAL_ENDPOINT=https://your-username--as3000-pdf-extractor-extract.modal.run
MODAL_TIMEOUT=300
```

**Done!** Your system is now using Modal.com for extraction.

---

## 🧪 Testing

### Test 1: Warmup (Optional)
```bash
# Warmup container (loads models, takes 30-60s)
curl -X GET https://your-username--as3000-pdf-extractor-warmup.modal.run

# Expected response:
{
  "status": "warm",
  "warmup_time": 45.2,
  "model_loaded": true
}
```

### Test 2: Upload PDF via Frontend
```bash
# Start backend
cd backend
python main.py

# Start frontend (new terminal)
cd ..
npm run dev

# Open browser
# → http://localhost:3000
# → Upload AS3000 2018.pdf
# → Wait 2-3 minutes
# → Download clauses.json and tables.json
```

### Test 3: Verify Outputs
```bash
# Check output directory
ls -la backend/outputs/<uuid>/

# Should see:
# - clauses.json      (~245 clauses)
# - tables.json       (~12+ tables)
# - normalized_document.txt
```

### Test 4: Validate Quality
```python
import json

# Check clauses
with open('backend/outputs/<uuid>/clauses.json') as f:
    clauses = json.load(f)
    
print(f"✅ Clauses: {len(clauses)}")
print(f"   Top-level: {sum(1 for c in clauses if c['level'] == 1)}")
print(f"   With parents: {sum(1 for c in clauses if c['has_parent'])}")
print(f"   With body: {sum(1 for c in clauses if c['has_body'])}")

# Check tables
with open('backend/outputs/<uuid>/tables.json') as f:
    tables = json.load(f)
    
print(f"\n✅ Tables: {len(tables)}")
print(f"   With numbers: {sum(1 for t in tables if t['table_number'])}")
print(f"   With titles: {sum(1 for t in tables if t['title'])}")
print(f"   With data: {sum(1 for t in tables if t['data_rows'])}")

# Expected for AS3000 2018.pdf:
# ✅ Clauses: 200-250 (95%+ accuracy)
# ✅ Tables: 12-15 (95%+ with numbers and titles)
```

---

## 📊 Cost Estimate

### Development (Testing)
- **Warmup calls**: Free (or ~$0.001/call)
- **Test PDFs** (1-10 docs): ~$3-5 total
- **Cold starts**: Included

### Production (AS3000 2018.pdf - 158 pages)
| Component | Cost per Document |
|-----------|-------------------|
| GPU (T4 @ $0.43/h) | $0.005-0.01 |
| GPT-4o (clauses) | $0.25-0.35 |
| **Total** | **$0.30-0.40** |

**Comparison**:
- Manual processing: $150/document
- OpenAI vision only: $8-10/document
- **Modal.com**: $0.30-0.40/document (99.7% savings)

### Monthly Estimate (100 documents)
- **Documents**: 100 × $0.35 = **$35/month**
- **Optional warm container**: $10/month (keeps container always ready)
- **Total**: **$35-45/month**

---

## 🔧 Configuration

### Modal.com Settings

#### GPU Selection
```python
# modal_extractor.py (line 688)
@app.function(
    gpu="T4",              # $0.43/hour (recommended)
    # gpu="A10G",          # $1.10/hour (2x faster)
    # gpu="A100",          # $3.00/hour (4x faster)
)
```

#### Container Persistence
```python
# modal_extractor.py (line 693)
min_containers=0,          # 0 = cold start (free when idle)
# min_containers=1,        # 1 = always warm ($10/month)
```

#### Timeout
```python
# modal_extractor.py (line 689)
timeout=1800,              # 30 minutes
# timeout=3600,            # 60 minutes (for very large PDFs)
```

#### Memory
```python
# modal_extractor.py (line 690)
memory=16384,              # 16GB (recommended)
# memory=32768,            # 32GB (for large PDFs with many tables)
```

### GPT-4 Settings

#### Model Selection
```python
# modal_extractor.py (extract_clauses_from_chunk function, line 547)
model="gpt-4o",            # Best quality, $0.25-0.35/doc
# model="gpt-4o-mini",     # 60% cheaper, 90% quality, $0.10-0.15/doc
```

#### Chunk Size
```python
# modal_extractor.py (extract_clauses_from_pdf function, line 468)
chunk_size = 20            # 20 pages per chunk (recommended)
# chunk_size = 30          # 30 pages (faster, higher GPT-4 cost)
# chunk_size = 10          # 10 pages (slower, lower GPT-4 cost)
```

### Backend Settings

```bash
# backend/.env

# Modal.com endpoint (from modal deploy output)
MODAL_ENDPOINT=https://your-username--as3000-pdf-extractor-extract.modal.run

# Enable Modal.com extraction
USE_MODAL_EXTRACTION=true

# Timeout (seconds) - adjust for large PDFs
MODAL_TIMEOUT=300          # 5 minutes (recommended)
# MODAL_TIMEOUT=600        # 10 minutes (for very large PDFs)
```

---

## 🐛 Troubleshooting

### Issue 1: `modal: command not found`
**Cause**: Modal CLI not installed

**Solution**:
```bash
pip install modal
# or
pip install modal --upgrade
```

### Issue 2: `Authentication failed`
**Cause**: Not logged in to Modal.com

**Solution**:
```bash
modal token new
# Opens browser → login
```

### Issue 3: `OpenAI API key not found`
**Cause**: Secret not created or incorrect name

**Solution**:
```bash
# List secrets
modal secret list

# Create/recreate secret (use exact name: openai-secret)
modal secret create openai-secret OPENAI_API_KEY=sk-proj-YOUR_KEY_HERE

# Redeploy
modal deploy modal_extractor.py
```

### Issue 4: `Container timeout (cold start)`
**Cause**: First call downloads models (2-3 minutes)

**Solution**:
```bash
# Option 1: Warmup before processing
curl -X GET https://your-endpoint-warmup.modal.run

# Option 2: Enable persistent container (costs $10/month)
# Edit modal_extractor.py line 693:
min_containers=1  # Always keep 1 container warm
```

### Issue 5: `GPU out of memory`
**Cause**: Large PDF with many tables

**Solution**:
```python
# Option 1: Reduce image DPI (modal_extractor.py line 127)
images = convert_from_bytes(pdf_bytes, dpi=100)  # Was 150

# Option 2: Increase GPU memory (modal_extractor.py line 690)
memory=32768  # 32GB instead of 16GB

# Option 3: Use bigger GPU (modal_extractor.py line 688)
gpu="A10G"  # More VRAM than T4
```

### Issue 6: `Request timeout after 300s`
**Cause**: Large PDF (200+ pages) or slow GPT-4 API

**Solution**:
```bash
# Increase timeout in backend/.env
MODAL_TIMEOUT=600  # 10 minutes

# Or split PDF into smaller parts (50-100 pages each)
```

### Issue 7: `OpenAI rate limit exceeded`
**Cause**: Too many concurrent requests

**Solution**:
```python
# Option 1: Process PDFs sequentially (not in parallel)

# Option 2: Increase OpenAI rate limits
# → https://platform.openai.com/account/limits

# Option 3: Use gpt-4o-mini (higher rate limits)
# Edit modal_extractor.py line 547:
model="gpt-4o-mini"
```

---

## 📈 Monitoring

### Check Modal.com Usage
```bash
# View logs
modal app logs as3000-pdf-extractor

# View running containers
modal container list

# View usage/costs
# → https://modal.com/usage
```

### Backend Logs
```bash
# Check backend logs
tail -f backend/backend_logs.txt

# Look for:
# "✅ Modal.com extracted X tables, Y clauses"
# "Extraction cost: $0.327"
```

### Quality Metrics
```python
# backend/services/validator.py logs validation issues
# Check for:
# - Missing parent clauses
# - Empty clause bodies
# - Invalid table numbers
# - Low confidence scores
```

---

## 🔄 Updates & Maintenance

### Update Modal Extractor
```bash
# Edit modal_extractor.py
# Then redeploy:
modal deploy modal_extractor.py

# No downtime - Modal.com handles rollout
```

### Update Backend
```bash
cd backend

# Pull latest changes
git pull

# Restart backend
# (if using systemd/docker, restart service)
python main.py
```

### Monitor Costs
```bash
# Check Modal.com dashboard
# → https://modal.com/usage

# Set up cost alerts:
# → Settings → Alerts → Add alert (e.g., $50/month)
```

---

## 🎓 Best Practices

### 1. Warmup for Batch Processing
```python
# Before processing multiple PDFs, warmup once
modal_service.warmup()

# Then process all PDFs (container stays warm 5 minutes)
for pdf in pdf_files:
    result = modal_service.extract_complete(pdf)
```

### 2. Use Persistent Container for High Volume
```python
# If processing >20 PDFs/day:
# Edit modal_extractor.py line 693:
min_containers=1  # Costs $10/month, saves 2-3 min per call
```

### 3. Monitor GPT-4 Costs
```python
# Log costs per document
total_cost = result.get("cost_estimate", 0)
logger.info(f"Document cost: ${total_cost:.3f}")

# Alert if unusually high
if total_cost > 1.0:
    logger.warning(f"High cost detected: ${total_cost}")
```

### 4. Handle Errors Gracefully
```python
try:
    result = modal_service.extract_complete(pdf_path)
except requests.exceptions.Timeout:
    logger.error("Timeout - PDF too large or Modal.com slow")
    # Retry or split PDF
except Exception as e:
    logger.error(f"Extraction failed: {e}")
    # Fallback to manual processing
```

---

## 📝 Deployment Checklist

**Before Deployment**:
- [ ] Modal.com account created
- [ ] OpenAI API key obtained
- [ ] Modal CLI installed (`pip install modal`)
- [ ] Authenticated (`modal token new`)

**Deployment**:
- [ ] OpenAI secret created (`modal secret create openai-secret OPENAI_API_KEY=...`)
- [ ] Modal extractor deployed (`modal deploy modal_extractor.py`)
- [ ] Endpoint URL copied from deploy output
- [ ] Backend `.env` updated with `MODAL_ENDPOINT`
- [ ] Backend restarted

**Testing**:
- [ ] Warmup endpoint called (optional but recommended)
- [ ] Test PDF uploaded via frontend
- [ ] Outputs generated (`clauses.json`, `tables.json`)
- [ ] Quality validated (clause count, table numbers, etc.)

**Production**:
- [ ] Cost monitoring enabled (Modal.com dashboard)
- [ ] Error handling tested (timeouts, API failures)
- [ ] Backup extraction method configured (if Modal.com fails)
- [ ] Documentation shared with team

---

## 🚀 Next Steps

1. **Deploy Now**: Run the 5-step quick start above
2. **Test Quality**: Upload AS3000 2018.pdf and verify outputs
3. **Monitor Costs**: Check Modal.com usage dashboard
4. **Scale Up**: Process your entire PDF library
5. **Optimize**: Adjust GPU/model settings based on cost/quality tradeoff

---

**Questions?** Check the troubleshooting section or:
- Modal.com docs: https://modal.com/docs
- OpenAI docs: https://platform.openai.com/docs
- Project README: ../README.md

---

**Ready to deploy?** Run: `modal deploy modal_extractor.py` 🚀
