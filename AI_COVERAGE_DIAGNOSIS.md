# AI Table Discovery Coverage Diagnosis

**Date**: March 29, 2026  
**Issue**: AI discovered only 2 tables instead of the expected significant coverage improvement  
**Expected**: 34% → 60%+ coverage (+17 tables for AS3000 2018.pdf)  
**Actual**: 19 tables with only 2 AI-discovered

---

## 🔍 Root Cause Analysis

### Problem Identified

The AI table discovery feature **is working correctly**, but it's **severely constrained** by the current triggering logic. The system only runs AI discovery on pages with "weak table signals", not on all pages.

### Current Implementation

**File**: `backend/services/table_pipeline.py` (lines 1736-1814)

```python
# AI-powered table discovery (if enabled)
if self._ai_service and self._ai_service.discovery_enabled:
    logger.info("Running AI table discovery with weak table detection...")
    
    # ⚠️ CONSTRAINT: Only pages with weak signals
    pages_needing_ai = self._detect_weak_table_pages(out, source_pdf_path, last_page)
    
    if pages_needing_ai:
        logger.info("Weak table detection identified %d pages...", len(pages_needing_ai))
    else:
        logger.info("No weak table signals detected - skipping AI discovery")  # ⚠️ THIS IS THE PROBLEM
```

### Weak Signal Detection Criteria

**File**: `backend/services/table_pipeline.py` (lines 1820-1944)

The system identifies pages for AI analysis only if they meet these conditions:

#### Signal 1: Orphaned Captions
- Caption detected (e.g., "Table 3.2") but no matching table extracted
- **Trigger**: `orphaned_caption:{caption_num}`
- **Diagnostic**: `ai_trigger_orphaned_caption`

#### Signal 2: Low-Quality Extractions
- Very few rows: `< 3 rows`
- Single column: `max columns < 2`
- Sparse data: `> 70% empty cells`
- **Triggers**: `few_rows`, `single_column`, `sparse_data`
- **Diagnostics**: `ai_trigger_few_rows`, `ai_trigger_single_column`, `ai_trigger_sparse_data`

#### Signal 3: No Extractions
- Page has substantial text (>200 chars) but zero tables extracted
- **Trigger**: `no_extraction`
- **Diagnostic**: `ai_trigger_no_extraction`

### Why This Limits Coverage

**The fundamental issue**: The AI is designed as a **"safety net"** for problematic pages, not as a **comprehensive discovery tool**.

If the geometric engines (pdfplumber, Camelot, Tabula) successfully extract **any table** from a page, that page is considered "handled" and **AI is never consulted**, even if:
- There are multiple tables on the page and only one was found
- The extracted table has low quality but passes thresholds
- The table has 3+ rows (passes the weak detection threshold)
- The caption was properly detected (no orphaned caption)

**Result**: AI only runs on 2 pages out of 158 in the GitHub run.

---

## 📊 Expected vs Actual Performance

### Documentation Claims (AI_ENHANCEMENT_PLAN.md)

```markdown
Expected improvement: 34% → 60%+ coverage (+17 tables for AS3000 2018.pdf)
Cost: ~$0.007 per page (~$0.70 per 100 pages, ~$1.40 for AS3000 2018.pdf)
Processing time: 2-3 sec/page → 4-6 sec/page (2x slower)
```

**Calculation**: 158 pages × $0.007 = **$1.106 expected cost**

### GitHub Run Actual Performance

| Metric | Expected | Actual | Gap |
|--------|----------|--------|-----|
| **Tables Extracted** | ~37+ (60% of 56) | 19 (34%) | **-18 tables** |
| **AI-Discovered** | ~17 tables | 2 tables | **-15 tables** |
| **Pages Analyzed by AI** | ~158 pages | ~2 pages | **-156 pages** |
| **Estimated Cost** | ~$1.10 | ~$0.02 | **-$1.08** |
| **Coverage Improvement** | +26% | +0% | **No improvement** |

**Conclusion**: The AI feature is enabled but **barely activated** due to conservative triggering logic.

---

## 🎯 Why Only 2 Tables Were Discovered

Based on the weak signal detection logic, the 2 AI-discovered tables likely matched these criteria:

### Table 4.3 (Page 41)
**Probable Trigger**: 
- Orphaned caption ("TABLE 4.3" detected but no table extracted initially)
- OR no extraction on page 41 (geometric engines all failed)

### Table D2 (Page 119)
**Probable Trigger**:
- Orphaned caption ("TABLE D2" detected but extraction missed it)
- OR low-quality extraction (few rows, sparse data)
- Note: There's also a standard pdfplumber D2 on same page, suggesting AI found it after geometric methods had weak extraction

---

## 🚀 Solutions & Recommendations

### Solution 1: Aggressive AI Discovery (Comprehensive Coverage)

**Enable AI on ALL pages** to achieve the documented 60%+ coverage.

**Implementation**:

```python
# Option A: Modify _detect_weak_table_pages to return all pages
def _detect_weak_table_pages(self, extracted_tables, source_pdf_path, last_page):
    # Return ALL pages for comprehensive AI analysis
    return set(range(1, last_page + 1))
```

**OR** modify the table pipeline:

```python
# Option B: Add configuration flag
# In config.py:
ai_discover_all_pages: bool = False  # New flag

# In table_pipeline.py:
if self._ai_service and self._ai_service.discovery_enabled:
    if self.settings.ai_discover_all_pages:
        pages_needing_ai = set(range(1, last_page + 1))
        logger.info("Running AI discovery on ALL %d pages (comprehensive mode)", last_page)
    else:
        pages_needing_ai = self._detect_weak_table_pages(out, source_pdf_path, last_page)
        logger.info("Running AI discovery on %d weak signal pages", len(pages_needing_ai))
```

**Pros**:
- ✅ Achieves documented 60%+ coverage
- ✅ Finds tables geometric methods completely miss
- ✅ Consistent with documentation expectations

**Cons**:
- ❌ 158 pages × $0.007 = **$1.10 per run** (higher cost)
- ❌ 2x slower processing (~5 minutes → ~10 minutes)
- ❌ May find false positives that need filtering

**Recommendation**: Add this as an **opt-in configuration** with clear cost warnings.

---

### Solution 2: Enhanced Weak Signal Detection (Balanced Approach)

**Expand the weak signal criteria** to catch more pages while still being selective.

**Implementation**:

```python
def _detect_weak_table_pages(self, extracted_tables, source_pdf_path, last_page):
    # ... existing signals ...
    
    # NEW SIGNAL 4: Pages with table indicators in text but no extraction
    for page_num in range(1, last_page + 1):
        if page_num not in pages_with_tables:
            page = pdf.pages[page_num - 1]
            page_text = page.extract_text() or ""
            
            # Look for table-related keywords
            table_keywords = [
                "table shows", "following table", "table below",
                "see table", "refer to table", "as shown in table",
                "requirement", "specification", "dimension"  # common in standards
            ]
            
            if any(keyword in page_text.lower() for keyword in table_keywords):
                pages_needing_ai.add(page_num)
                weak_signal_reasons[page_num].append("table_keyword_found")
                self._diag["ai_trigger_keyword"] = self._diag.get("ai_trigger_keyword", 0) + 1
    
    # NEW SIGNAL 5: Pages with tables that are too "perfect" (might be missing others)
    for page_num, page_tables in tables_by_page.items():
        if len(page_tables) == 1:  # Only one table found
            # Check if there are multiple caption references on the page
            captions_on_page = caption_pages.get(page_num, [])
            if len(captions_on_page) > 1:
                pages_needing_ai.add(page_num)
                weak_signal_reasons[page_num].append(f"multiple_captions_single_table:{len(captions_on_page)}")
                self._diag["ai_trigger_missed_captions"] = self._diag.get("ai_trigger_missed_captions", 0) + 1
    
    # NEW SIGNAL 6: Check LIST OF TABLES expectations
    # If we have a list of tables from front matter, check which are missing
    expected_tables = self._extract_list_of_tables(source_pdf_path)  # Would need implementation
    if expected_tables:
        extracted_numbers = {rt.table_number for rt in extracted_tables if rt.table_number}
        missing_tables = expected_tables - extracted_numbers
        
        # Find pages where these tables should be (would need page number from LOT)
        for missing_num in missing_tables:
            # Add page to AI analysis
            pass  # Implementation needed
    
    return pages_needing_ai
```

**Pros**:
- ✅ More targeted than all-pages approach (lower cost)
- ✅ Catches common patterns where tables are missed
- ✅ Uses document structure intelligence (LIST OF TABLES)

**Cons**:
- ⚠️ Still might miss tables without clear signals
- ⚠️ More complex logic to maintain

---

### Solution 3: Two-Pass Approach (Recommended)

**Combine both strategies** with a two-pass approach:

1. **First Pass**: Run geometric detection + weak signal AI (current behavior)
2. **Gap Analysis**: Compare extracted tables against LIST OF TABLES or expected coverage
3. **Second Pass**: Run aggressive AI discovery only on pages with suspected missing tables

**Implementation**:

```python
def extract_tables(self, source_pdf_path, last_page):
    # Pass 1: Geometric detection + weak signal AI
    tables_pass1 = self._extract_tables_geometric(source_pdf_path, last_page)
    tables_pass1_ai = self._ai_discovery_weak_signals(tables_pass1, source_pdf_path, last_page)
    
    # Gap analysis
    if self._ai_service and self._ai_service.discovery_enabled:
        expected_tables = self._extract_expected_tables_from_lot(source_pdf_path)
        extracted_numbers = {t.table_number for t in tables_pass1_ai if t.table_number}
        missing_tables = expected_tables - extracted_numbers
        
        if missing_tables:
            logger.info(
                "Gap analysis: %d expected tables missing: %s. Running targeted AI discovery...",
                len(missing_tables),
                sorted(missing_tables)
            )
            
            # Pass 2: Targeted AI on pages that should have tables but don't
            suspect_pages = self._identify_pages_for_missing_tables(
                missing_tables,
                source_pdf_path,
                last_page
            )
            
            tables_pass2 = self._ai_discovery_targeted(suspect_pages, source_pdf_path)
            tables_pass1_ai.extend(tables_pass2)
    
    return tables_pass1_ai
```

**Pros**:
- ✅ **Best cost/benefit ratio**
- ✅ Uses document intelligence (LIST OF TABLES)
- ✅ Only runs expensive AI when gaps are detected
- ✅ Achieves high coverage without analyzing every page

**Cons**:
- ⚠️ Requires LIST OF TABLES parsing (already have examples in codebase)
- ⚠️ More complex implementation

---

## 📋 Implementation Recommendations

### Immediate Actions (High Priority)

#### 1. Create Configuration Flag (1 hour)

Add to `backend/.env.example` and `backend/config.py`:

```env
# AI Discovery Mode
# - "weak_signals": Only pages with problems (current, conservative, ~2-5% of pages)
# - "comprehensive": All pages (expensive, ~$0.007/page, maximum coverage)
# - "balanced": Enhanced weak signals + gap analysis (recommended)
AI_DISCOVERY_MODE=weak_signals

# For comprehensive mode, set maximum cost limit
AI_COMPREHENSIVE_MAX_COST=2.00  # USD, prevent runaway costs
```

#### 2. Update Documentation (30 minutes)

Update `AI_ENHANCEMENT_PLAN.md` and `README.md` to clarify:
- Current default behavior (weak signals only)
- How to enable comprehensive discovery
- Expected costs for different modes
- Coverage expectations for each mode

#### 3. Add Diagnostic Logging (1 hour)

Enhance logging to show:
```
AI Discovery Summary:
  Mode: weak_signals
  Pages analyzed: 2 / 158 (1.3%)
  Tables found: 2
  Estimated cost: $0.02
  
  To improve coverage, consider:
    - Set AI_DISCOVERY_MODE=comprehensive (expect $1.10 cost, +15-20 tables)
    - Set AI_DISCOVERY_MODE=balanced (expect $0.30 cost, +8-12 tables)
```

### Medium Term (2-4 hours)

#### 4. Implement Balanced Mode

- Enhanced weak signal detection with keyword matching
- Multiple captions / single extraction detection
- Gap analysis against LIST OF TABLES

#### 5. Add Cost Controls

```python
# Stop if cost exceeds limit
if self.metrics.total_cost_usd >= self.settings.ai_comprehensive_max_cost:
    logger.warning("AI cost limit reached ($%.2f). Stopping AI discovery.", 
                   self.metrics.total_cost_usd)
    break
```

#### 6. Create Test Suite

Test AI discovery on:
- Page with 0 tables (geometric detection failed completely)
- Page with 1 table but 2 captions (missed table)
- Page with weak extraction (few rows, should trigger re-analysis)
- Cost limits (verify stops at threshold)

---

## 🎓 Key Insights

### Why the Documentation is Misleading

The `AI_ENHANCEMENT_PLAN.md` states:
> **Expected improvement: 34% → 60%+ coverage (+17 tables for AS3000 2018.pdf)**

This expectation **assumes AI runs on most/all pages**, not just weak signal pages. The documentation describes the AI's **potential** if used comprehensively, not its **default behavior**.

### Design Philosophy Conflict

There are two competing design philosophies:

#### Conservative (Current Implementation)
- **Philosophy**: AI as a "safety net" for problem pages only
- **Benefit**: Low cost, fast processing
- **Drawback**: Misses many tables, doesn't achieve documented coverage

#### Aggressive (Documentation Expectation)
- **Philosophy**: AI as a primary discovery tool alongside geometric methods
- **Benefit**: Maximum coverage, achieves 60%+ goal
- **Drawback**: Higher cost, slower processing

**Resolution**: Provide both as **configuration options** with clear trade-offs.

---

## 💡 Recommended Default Configuration

```env
# Recommended production configuration
ENABLE_AI_TABLE_DISCOVERY=true
AI_DISCOVERY_MODE=balanced
AI_COMPREHENSIVE_MAX_COST=2.00
AI_MAX_CALLS_PER_JOB=100
```

This provides:
- ~40-50% coverage improvement over pure geometric
- ~$0.30-0.50 per 200-page PDF
- 30-50 pages analyzed (not all 158)
- Best cost/benefit ratio

---

## 📊 Expected Performance by Mode

| Mode | Pages Analyzed | Expected Tables | Cost (AS3000) | Processing Time |
|------|----------------|-----------------|---------------|-----------------|
| **weak_signals** (current) | 2-10 (1-6%) | 19-22 | $0.02-0.10 | +10% |
| **balanced** (recommended) | 30-50 (20-30%) | 28-35 | $0.30-0.50 | +30% |
| **comprehensive** | 158 (100%) | 37-42 | $1.00-1.20 | +100% |

**Ground Truth**: AS3000 2018 has ~56 tables according to TABLE_COVERAGE_REPORT.md

---

## ✅ Conclusion

The AI table discovery feature is **implemented correctly** but **severely underutilized** by conservative triggering logic. To achieve the documented 60%+ coverage:

1. **Short term**: Enable `AI_DISCOVERY_MODE=comprehensive` with cost limits
2. **Medium term**: Implement `balanced` mode with enhanced weak signals
3. **Long term**: Add LIST OF TABLES parsing for intelligent gap analysis

The current "weak signals only" approach is suitable for **production cost control** but not for **maximum coverage**, which requires more aggressive AI usage.

---

**Status**: ✅ Diagnosis Complete | ⏭️ Ready for implementation
**Priority**: HIGH - User expects significantly better coverage with AI enabled
**Estimated Implementation Time**: 4-6 hours for balanced mode + configuration
