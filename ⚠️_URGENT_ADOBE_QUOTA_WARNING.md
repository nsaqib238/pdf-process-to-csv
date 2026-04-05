# ⚠️ URGENT: Stop Testing with Adobe Enabled!

## Current Situation

**Adobe API Quota: 163/500 used (32.6% consumed)**

You're rapidly consuming Adobe API calls because:
1. You're still testing with `ENABLE_ADOBE_HYBRID=true` (Adobe enabled)
2. Large PDFs (600+ pages) are auto-split into 7 chunks = **7 API calls per upload**
3. Each test upload consumes 7 calls immediately

**Quota Usage Timeline:**
- Started at 125/500 calls
- Now at 163/500 calls
- **38 new calls** = ~5-6 more large PDF test uploads
- At this rate, you'll exhaust the 500/month quota in **2-3 more test sessions**

---

## 🚨 IMMEDIATE ACTION REQUIRED

### Stop Adobe Consumption NOW:

```bash
# 1. Pull latest fixes
git pull origin main

# 2. Edit backend/.env
ENABLE_ADOBE_HYBRID=false

# 3. Restart backend
# Stop current backend process and restart
```

### Verify Adobe is Disabled:

After restart, check logs for this message:
```
📊 STANDARD MODE: Modal with Tesseract OCR (Adobe disabled in config)
```

**NOT this:**
```
🔥 HYBRID MODE: Adobe OCR + Modal Structure
```

---

## Why This Happened

### The Math:

- **Small PDF (<100 pages)**: 1 Adobe API call
- **611-page PDF**: 7 chunks → **7 Adobe API calls**
- **1000-page PDF**: 11 chunks → **11 Adobe API calls**

### Your Testing Pattern:

From logs, you tested with:
- 3 failed attempts (different PDFs/errors) = 3 calls
- 1 large PDF (611 pages) with 7 chunks = 7 calls
- Multiple other test sessions = 153 more calls

**Total from this month**: 163 calls

---

## What Changed (Fixes Already Pushed)

### Fix 1: Parsing Bug (Commit 8983b9c)
**Problem**: Adobe SDK returned `bytes` instead of `dict`, causing `'bytes' object has no attribute 'get'` error.

**Fixed**: Added type checking to handle all Adobe response types (dict, None, bytes, string).

**Impact**: Adobe now works correctly when enabled, but still consumes quota per chunk.

### Fix 2: Quota Management (Commit d984be1)
**Problem**: No way to disable Adobe during testing to conserve quota.

**Added**:
- `ENABLE_ADOBE_HYBRID` config flag in `.env`
- When `false`: Uses Modal Tesseract OCR (zero Adobe calls)
- When `true`: Uses Adobe OCR (high quality, consumes quota)
- Comprehensive documentation in `ADOBE_API_QUOTA_MANAGEMENT.md`

---

## Testing Modes

### During Development/Testing (RECOMMENDED NOW):

```bash
# backend/.env
ENABLE_ADOBE_HYBRID=false
```

**Benefits:**
- ✅ Zero Adobe API calls
- ✅ Test as much as you want
- ✅ Still processes large PDFs (no limits)
- ❌ Lower OCR quality (Tesseract instead of Adobe)

### In Production (AFTER FIXES VERIFIED):

```bash
# backend/.env
ENABLE_ADOBE_HYBRID=true
```

**Benefits:**
- ✅ Best OCR quality (Adobe)
- ✅ High accuracy on complex fonts/scanned docs
- ❌ Consumes Adobe quota (500/month free)
- ❌ Large PDFs = multiple API calls

---

## Quota Monitoring

### Check Your Adobe Usage:

1. Go to: https://acrobatservices.adobe.com/dc-integration-creation-app-cdn/main.html
2. View "PDF Services API Usage Report"
3. Current period: 163/500 Document Transactions

### Conservative Usage Strategy:

**Remaining quota**: 337 calls (67.4%)

**Estimated capacity**:
- Small PDFs (<100 pages): 337 more documents
- Large PDFs (~600 pages): 48 more documents (337 ÷ 7)
- Mixed sizes: Depends on page counts

**Recommendation**: Keep Adobe disabled until production deployment.

---

## How to Test Safely

### Phase 1: Functional Testing (NOW)
```bash
ENABLE_ADOBE_HYBRID=false  # Use Modal Tesseract
```
- Test PDF upload flow
- Test table extraction
- Test clause extraction
- Test error handling
- Test large PDFs (600+ pages)

### Phase 2: Quality Verification (BEFORE PROD)
```bash
ENABLE_ADOBE_HYBRID=true  # Enable Adobe
```
- Test with **3-5 representative PDFs** only
- Compare OCR quality (Adobe vs Tesseract)
- Verify hybrid mode works correctly
- **Stop immediately after verification**

### Phase 3: Production (AFTER LAUNCH)
```bash
ENABLE_ADOBE_HYBRID=true  # Keep enabled for best quality
```
- Monitor quota daily
- Plan upgrade if exceeding 400 calls/month
- Consider pay-as-you-go plan: $0.05/document

---

## Adobe Pricing Options

### Current Plan: Free Tier
- **500 document transactions/month**
- **FREE**
- Good for: Testing, small projects

### Upgrade Options:

#### Pay-As-You-Go
- **$0.05 per document transaction**
- No monthly commitment
- Scales automatically
- **Example**: 163 documents = $8.15

#### Volume Plans
- Contact Adobe for enterprise pricing
- Better rates at high volume
- Dedicated support

---

## Key Takeaways

1. **Large PDFs consume multiple API calls** (1 per chunk)
2. **Testing with Adobe enabled is expensive** (quota-wise)
3. **Always disable Adobe during development** (`ENABLE_ADOBE_HYBRID=false`)
4. **Enable Adobe only for production** (best quality)
5. **Monitor quota regularly** to avoid surprises

---

## Next Steps

### RIGHT NOW:
1. ✅ Pull latest code: `git pull origin main`
2. ✅ Set `ENABLE_ADOBE_HYBRID=false` in `backend/.env`
3. ✅ Restart backend
4. ✅ Verify logs show "STANDARD MODE" (not "HYBRID MODE")

### BEFORE PRODUCTION:
1. Test with Adobe enabled (3-5 PDFs max)
2. Verify OCR quality meets requirements
3. Decide: Keep Adobe or use Tesseract?
4. If keeping Adobe: Plan quota monitoring

### IN PRODUCTION:
1. Enable Adobe for best quality
2. Monitor quota weekly
3. Upgrade to pay-as-you-go if needed
4. Consider caching/optimization strategies

---

## Questions?

Read `ADOBE_API_QUOTA_MANAGEMENT.md` for comprehensive documentation on:
- How API counting works
- Calculation examples
- Quality comparisons
- Troubleshooting guide
- Best practices

**Bottom line**: Disable Adobe NOW to stop quota consumption. Enable only when ready for production.
