# Quick Setup Instructions

## 🚀 What You Need to Do

### 1. Add Your OpenAI API Key

Edit `backend/.env` and replace this line:
```env
OPENAI_API_KEY=sk-proj-your-key-here
```

With your actual API key:
```env
OPENAI_API_KEY=sk-proj-abc123...your-actual-key
```

Get your key from: https://platform.openai.com/api-keys

### 2. Restart the Server

```bash
# Stop current server (if running)
# Then restart:
cd backend
python -m uvicorn app:app --reload
```

### 3. Process Your PDF

Upload your PDF through the API - it will now use **comprehensive AI mode**.

---

## ✅ Current Configuration (backend/.env)

Your `.env` is now configured for **maximum table coverage**:

```env
# Core extraction enabled
ENABLE_TABLE_CAMELOT_TABULA=true
ENABLE_HEADER_RECONSTRUCTION=true

# AI enhancement enabled
ENABLE_AI_TABLE_DISCOVERY=true
AI_DISCOVERY_MODE=comprehensive  ← Analyzes ALL pages

# Cost protection
AI_COMPREHENSIVE_MAX_COST=2.00  ← Stops at $2.00
```

---

## 📊 Expected Results

| Mode | Before (No AI) | After (Comprehensive) | Cost | Speed |
|------|----------------|----------------------|------|-------|
| **AS3000 2018.pdf** | 19 tables | **37-42 tables** | ~$1.10 | 2x slower |
| **158 pages** | 34% coverage | **60%+ coverage** | $0.007/page | 4-6 sec/page |

---

## 🔧 Other Available Modes

If comprehensive is too expensive, you can change `AI_DISCOVERY_MODE`:

### Option 1: Balanced Mode (Recommended Alternative)
```env
AI_DISCOVERY_MODE=balanced
```
- Cost: ~$0.30-0.50 per PDF
- Coverage: 28-35 tables (+8-12 vs no AI)
- Speed: +30% processing time

### Option 2: Weak Signals (Current GitHub Output)
```env
AI_DISCOVERY_MODE=weak_signals
```
- Cost: ~$0.02-0.10 per PDF
- Coverage: 19-22 tables (+2-5 vs no AI)
- Speed: +10% processing time
- **This is what produced your 19-table output**

---

## 📁 Key Files

- `backend/.env` - Your configuration (just add OpenAI key)
- `HOW_TO_GET_MORE_AI_COVERAGE.md` - Detailed guide
- `AI_COVERAGE_DIAGNOSIS.md` - Why you only got 2 AI-discovered tables
- `backend/.env.example` - Full documentation of all options

---

## 🐛 Troubleshooting

### Server won't start?
```bash
cd backend
pip install openai  # If not installed
python -m uvicorn app:app --reload
```

### Still getting 19 tables?
- Check that `ENABLE_AI_TABLE_DISCOVERY=true`
- Check that `AI_DISCOVERY_MODE=comprehensive`
- Verify your OpenAI API key is valid
- Check server logs for AI processing messages

### Cost concerns?
- `AI_COMPREHENSIVE_MAX_COST=2.00` protects against runaway costs
- Processing stops automatically when limit reached
- Monitor usage at: https://platform.openai.com/usage

---

## ✨ Next Steps

1. ✅ Add OpenAI API key to `backend/.env`
2. ✅ Restart server
3. ✅ Process AS3000 2018.pdf
4. ✅ Verify 35-40+ tables extracted (vs previous 19)
5. ✅ Check `tables.json` for AI-discovered tables

**Need help?** See `HOW_TO_GET_MORE_AI_COVERAGE.md` for more details.
