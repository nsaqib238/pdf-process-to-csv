# Iteration 2: Threshold Adjustment for Improved Coverage

## Problem

Analysis of the "LIST OF TABLES" from AS/NZS 3000:2018 revealed:
- **Expected tables:** 56
- **Extracted tables:** 18 with table numbers
- **Coverage:** 32% (18/56)
- **Missing:** 38 tables (68%)

## Root Cause

The Iteration 1 threshold of **0.55** was optimized for **precision** (eliminating false positives) but was too aggressive, causing valid tables to be rejected as "clause-shaped content."

### Missing Tables Analysis

- Section 3: 4/10 extracted (40%) - Missing 3.1, 3.3, 3.4, 3.6, 3.7, 3.8
- Section 4: 0/3 extracted (0%) - Missing all (4.1, 4.2, 4.3)
- Section 5: 0/2 extracted (0%) - Missing all (5.1, 5.2)
- Section 6: 0/3 extracted (0%) - Missing all (6.1, 6.2, 6.3)
- Section 8: 1/2 extracted (50%) - Missing 8.2
- Appendix B: 0/1 extracted (0%) - Missing B1
- Appendix C: 5/12 extracted (42%) - Missing 7 tables
- Appendix D: 4/15 extracted (27%) - Missing 11 tables
- Appendix H, I, K, N: 1/12 extracted (8%) - Missing 11 tables

## Solution: Iteration 2

**Relax the clause rejection threshold from 0.55 to 0.60**

```python
# backend/services/table_pipeline.py, line ~737

# Before (Iteration 1):
if clause_score >= 0.55:
    return True  # Reject as clause-shaped

# After (Iteration 2):
if clause_score >= 0.60:
    return True  # Reject as clause-shaped
```

## Rationale

### Threshold Scale
- **0.65** (P0 original) - Very conservative, some false positives slipped through
- **0.55** (Iteration 1) - Aggressive precision, eliminated most false positives but captured some valid tables
- **0.60** (Iteration 2) - **Balanced approach**, aiming for better recall without sacrificing too much precision
- **0.50** (too low) - Would allow too many false positives

### Why 0.60?

1. **Small adjustment** - Only 0.05 increase, reducing risk of allowing garbage tables back in
2. **Maintains 2-column prose detection** - Iteration 1's enhanced detection patterns still active
3. **Preserves sweep gating** - P0's single-column filtering still works
4. **Targeted impact** - Tables with scores 0.55-0.59 will now pass through

### Expected Tables to Capture

Tables likely scoring 0.55-0.59 (borderline cases):
- **Simple 2-column tables** without prose characteristics
- **Sizing/rating tables** (e.g., conductor sizes, temperature limits)
- **Selection guides** (e.g., protective device selection)
- **Specification tables** (e.g., cable colors, earth electrode specs)

## Expected Impact

### Optimistic Scenario
- **+5 to +10 additional tables** captured
- New total: ~28-33 tables
- Coverage: 50-59% (28-33/56)
- Risk: +2-3 false positives

### Realistic Scenario
- **+3 to +5 additional tables** captured
- New total: ~26-28 tables
- Coverage: 46-50% (26-28/56)
- Risk: +1-2 false positives

### Conservative Scenario
- **+1 to +3 additional tables** captured
- New total: ~24-26 tables
- Coverage: 43-46% (24-26/56)
- Risk: +0-1 false positives

## Trade-offs

| Metric | Before (0.55) | After (0.60) | Change |
|--------|---------------|--------------|--------|
| **Precision** | Very High (⬆️) | High | Slightly decreased |
| **Recall** | Low (⬇️) | Medium | **Increased** ✅ |
| **Coverage** | 32% | 43-50% (est) | **+11-18%** ✅ |
| **False Positives** | ~5 | ~6-8 (est) | +1-3 |

## Why Not More Aggressive?

### Why Not 0.65 or Higher?
- Would allow "Changes to AS/NZS 3000:2007..." back in (scored ~0.68)
- Would defeat the purpose of Iteration 1 improvements
- Too many false positives

### Why Not Lower Than 0.60?
- Many missing tables are likely **image-based** (cannot be extracted programmatically)
- Some are **text-based lists** formatted as prose, not tables
- Some may not exist or use different numbering schemes

## Remaining Missing Tables Reasons

Even after Iteration 2, some tables will remain missing due to:

### 1. Image-Based Tables (~20-30% of missing)
Tables rendered as images/diagrams cannot be extracted:
- Tables with special symbols or diagrams
- Tables with complex merged cell structures
- Scanned pages

**Examples:** Likely H1, H2, I1, I2 (protection degree tables with complex layouts)

### 2. Text-Based Lists (~30-40% of missing)
Some "tables" are actually formatted lists:
- Cable specification lists (3.1, 3.3, 3.4)
- Requirements lists (4.1, 4.2, 4.3)
- Sizing guides (5.1, 5.2)

**These look like prose to the pipeline, not tables.**

### 3. Non-Existent Tables (~10-20% of missing)
Not all numbers in a sequence may exist:
- Document may skip table numbers
- Alternative numbering schemes used

### 4. Low-Quality Tables (~10-20% of missing)
Tables with poor structure filtered by quality scoring:
- Very low fill ratios
- High noise ratios
- Structural defects

## Testing Plan

1. **Run Iteration 2** on full AS3000 2018.pdf
2. **Compare results:**
   - Count new tables extracted
   - Identify newly captured table numbers
   - Check for new false positives
3. **Validate quality:**
   - Manually inspect newly captured tables
   - Verify they are legitimate tables, not prose
4. **Fine-tune if needed:**
   - If too many false positives: revert to 0.575 or 0.58
   - If still missing many valid tables: investigate other causes (image-based, quality filters)

## Success Criteria

✅ **Minimum Success:**
- +3 additional valid tables (21/56 = 38% coverage)
- ≤2 additional false positives

✅ **Target Success:**
- +5 additional valid tables (23/56 = 41% coverage)
- ≤3 additional false positives

✅ **Stretch Success:**
- +8 additional valid tables (26/56 = 46% coverage)
- ≤4 additional false positives

## Rollback Plan

If Iteration 2 introduces too many false positives:

```python
# Revert to Iteration 1 threshold
if clause_score >= 0.55:
    return True

# Or try intermediate value
if clause_score >= 0.575:
    return True
```

## Next Steps if Still Insufficient Coverage

If Iteration 2 doesn't significantly improve coverage:

1. **Investigate image-based tables** - Add OCR fallback for diagram tables
2. **Adjust quality metrics** - Review scoring thresholds
3. **Enhance caption detection** - Support alternative caption formats
4. **Manual page analysis** - Check specific missing table pages to understand structure
5. **Accept trade-off** - Some tables may be fundamentally unextractable

## Files Modified

- `backend/services/table_pipeline.py` - Line ~737, clause rejection threshold

## Documentation

See also:
- `MISSING_TABLES_ANALYSIS.md` - Complete breakdown of missing tables
- `ITERATION_1_IMPROVEMENTS.md` - Previous threshold adjustment (0.65 → 0.55)
- `PDF_PIPELINE_UPGRADES.md` - P0-P4 upgrade details
