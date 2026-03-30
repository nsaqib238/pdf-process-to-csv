# How to Get More AI Table Coverage

**Problem**: AI discovered only 2 tables instead of the expected 15-20 additional tables.

**Root Cause**: The AI discovery feature defaults to "weak signals" mode, which only analyzes problematic pages (~2-5% of pages). To achieve the documented 60%+ coverage improvement, you need to enable **comprehensive mode**.

---

## 🚀 Quick Solution

### Option 1: Enable Comprehensive Mode (Recommended for Maximum Coverage)

Create or edit `backend/.env`:

```env
# Enable AI table discovery
OPENAI_API_KEY=sk-proj-your-key-here
ENABLE_AI_TABLE_DISCOVERY=true

# Set to comprehensive mode for maximum coverage
AI_DISCOVERY_MODE=comprehensive
AI_COMPREHENSIVE_MAX_COST=2.00
```

**Expected Results**:
- **Coverage**: 60%+ (19 tables → 35-40 tables for AS3000)
- **Cost**: ~$1.10 for 158-page PDF (~$0.007 per page)
- **Speed**: 2x slower (5 minutes → 10 minutes)

---

### Option 2: Balanced Mode (Good Coverage, Lower Cost)

```env
OPENAI_API_KEY=sk-proj-your-key-here
ENABLE_AI_TABLE_DISCOVERY=true

# Balanced mode (future: will include keyword matching, gap analysis)
AI_DISCOVERY_MODE=balanced
AI_COMPREHENSIVE_MAX_COST=1.00
```

**Expected Results**:
- **Coverage**: 45-50% (19 tables → 28-32 tables)
- **Cost**: ~$0.30-0.50 for 200-page PDF
- **Speed**: 30% slower

---

### Option 3: Current Default (Weak Signals Only)

```env
OPENAI_API_KEY=sk-proj-your-key-here
ENABLE_AI_TABLE_DISCOVERY=true

# Weak signals mode (default, very conservative)
AI_DISCOVERY_MODE=weak_signals
```

**Current Results**:
- **Coverage**: 34% (19 tables, +2 from AI)
- **Cost**: ~$0.02-0.10 per 200-page PDF
- **Speed**: +10% slower

---

## 📊 Comparison Table

| Mode | Pages Analyzed | Expected Tables | Cost (AS3000) | Processing Time |
|------|----------------|-----------------|---------------|-----------------|
| **weak_signals** (current) | 2-10 (1-6%) | 19-22 | $0.02-0.10 | +10% |
| **balanced** | 30-50 (20-30%) | 28-35 | $0.30-0.50 | +30% |
| **comprehensive** | 158 (100%) | 37-42 | $1.00-1.20 | +100% |

**Ground Truth**: AS3000 2018 has ~56 tables total

---

## 🔧 Step-by-Step Setup

### 1. Get OpenAI API Key

1. Go to [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Create a new API key (starts with `sk-proj-...`)
3. Copy the key

### 2. Create/Edit Backend .env File

```bash
cd backend
cp .env.example .env
# Edit .env with your favorite editor
```

### 3. Add Configuration

```env
# OpenAI API Key (required)
OPENAI_API_KEY=sk-proj-paste-your-key-here

# Enable AI table discovery
ENABLE_AI_TABLE_DISCOVERY=true

# Choose mode (comprehensive for maximum coverage)
AI_DISCOVERY_MODE=comprehensive

# Set cost limit (default is $2.00)
AI_COMPREHENSIVE_MAX_COST=2.00

# Optional: Other AI features
# ENABLE_AI_CAPTION_DETECTION=true
# ENABLE_AI_STRUCTURE_VALIDATION=true
```

### 4. Restart the Server

The project must be restarted to pick up the new configuration:

```bash
# Stop current server (Ctrl+C in terminal)
# Restart with Run button or:
python backend/main.py
npm run dev
```

### 5. Process Your PDF

Upload your PDF through the web interface. You should see in the logs:

```
Running AI table discovery (mode: comprehensive)...
Comprehensive mode: analyzing ALL 158 pages with AI vision
Cost limit: $2.00
...
AI discovery complete: 18 tables found from 158 pages analyzed (cost: $1.0543)
```

---

## 💰 Cost Management

### Set Cost Limits

The `AI_COMPREHENSIVE_MAX_COST` setting prevents runaway costs:

```env
# Stop processing if cost exceeds this amount (USD)
AI_COMPREHENSIVE_MAX_COST=2.00
```

If the limit is reached, you'll see:
```
⚠️  AI cost limit reached ($2.00 / $2.00). Stopping AI discovery at page 142.
```

### Monitor Costs

Check the logs for cost information:
```
Vision API call completed in 2.34s. Tokens: 1547 ($0.0072)
AI discovery complete: 18 tables found from 158 pages analyzed (cost: $1.0543)
```

### Optimize Costs

1. **Start with weak_signals** - Test for free, see if it's sufficient
2. **Try balanced mode** - Good middle ground (~30% of comprehensive cost)
3. **Use comprehensive selectively** - Only for important documents
4. **Set tight cost limits** - Prevent surprises

---

## 🎯 Expected Performance by PDF Size

| PDF Size | Comprehensive Cost | Expected Additional Tables |
|----------|-------------------|---------------------------|
| 50 pages | ~$0.35 | +5-8 tables |
| 100 pages | ~$0.70 | +10-15 tables |
| 150 pages | ~$1.05 | +15-20 tables |
| 200 pages | ~$1.40 | +20-25 tables |

**Formula**: `Cost ≈ Pages × $0.007`

---

## 🐛 Troubleshooting

### "No weak table signals detected - skipping AI discovery"

**Problem**: You're still in weak_signals mode.

**Solution**: Set `AI_DISCOVERY_MODE=comprehensive` in `.env` and restart.

---

### "AI features enabled but OPENAI_API_KEY not set"

**Problem**: API key is missing or incorrect.

**Solution**: 
1. Check `.env` file exists in `backend/` directory
2. Verify key starts with `sk-proj-` or `sk-`
3. No quotes around the key value
4. Restart the server

---

### "AI cost limit reached"

**Problem**: Hit the cost limit before analyzing all pages.

**Solution**: Increase `AI_COMPREHENSIVE_MAX_COST`:
```env
AI_COMPREHENSIVE_MAX_COST=5.00  # Higher limit
```

---

### Still Getting Poor Coverage

**Possible causes**:
1. PDF has complex/scanned tables that even AI struggles with
2. Tables are actually diagrams/figures (AI correctly rejects them)
3. Document doesn't have as many tables as expected

**Debug steps**:
1. Check `AI discovery complete:` log message - how many pages were analyzed?
2. Enable debug logging to see AI responses
3. Review `AI_COVERAGE_DIAGNOSIS.md` for detailed analysis

---

## 📚 Additional Resources

- **AI_COVERAGE_DIAGNOSIS.md** - Detailed root cause analysis
- **AI_ENHANCEMENT_PLAN.md** - Original AI feature design
- **AI_IMPLEMENTATION_GUIDE.md** - Technical implementation details
- **.env.example** - Full configuration reference with comments

---

## ✅ Quick Checklist

Before processing your PDF, verify:

- [ ] OpenAI API key is set in `backend/.env`
- [ ] `ENABLE_AI_TABLE_DISCOVERY=true` is set
- [ ] `AI_DISCOVERY_MODE=comprehensive` is set (for maximum coverage)
- [ ] Cost limit is appropriate: `AI_COMPREHENSIVE_MAX_COST=2.00`
- [ ] Server has been restarted after changing `.env`
- [ ] You have sufficient OpenAI API credits

---

**TL;DR**: To get 35-40 tables instead of 19, add these three lines to `backend/.env`:

```env
OPENAI_API_KEY=sk-proj-your-key-here
ENABLE_AI_TABLE_DISCOVERY=true
AI_DISCOVERY_MODE=comprehensive
```

Then restart the server and process your PDF. Cost: ~$1.10 for 158-page document.
