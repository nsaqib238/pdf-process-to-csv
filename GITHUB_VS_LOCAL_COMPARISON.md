# GitHub vs Local Tables.json Comparison

## Summary

Detailed comparison between:
- **GitHub `tables.json`**: 19 tables (AI-enhanced, committed to repository)
- **Local Latest Run**: 21 tables (`outputs/9fe98a82-a4c1-4bb9-adc8-7b637abab406/tables.json`)

**Key Finding**: The local run found **2 MORE tables** than the GitHub AI-enhanced version, covering **6 additional pages** that GitHub missed, but missing **3 pages** that GitHub found.

---

## 📊 Quantitative Comparison

| Metric | GitHub (AI) | Local Latest | Difference |
|--------|-------------|--------------|------------|
| **Total Tables** | 19 | 21 | +2 local |
| **Pages Covered** | 18 pages | 21 pages | +3 local |
| **Tables with Numbers** | 17 | 16 | -1 local |
| **Tables without Numbers** | 2 | 5 | +3 local |
| **AI-Discovered** | 2 | Unknown | - |

---

## 🔍 Side-by-Side Table List

### Tables in BOTH Outputs (Shared: 13 tables)

| Table Number | Page | Status |
|--------------|------|--------|
| None | 15 | ✅ Both |
| C3 | 100 | ✅ Both |
| C10 | 114 | ✅ Both |
| C11 | 115 | ✅ Both |
| C12 | 116 | ✅ Both |
| D1 | 118 | ✅ Both |
| D2 | 119 | ✅ Both (GitHub has duplicate) |
| D3 | 120 | ✅ Both |
| D11 | 126 | ✅ Both |
| None | 133 | ✅ Both |
| E11 | 142 | ✅ Both |
| K1 | 149 | ✅ Both |
| E104 | 151 | ✅ Both |

### Tables ONLY in GitHub (6 tables)

| Table Number | Page | Notes |
|--------------|------|-------|
| **3.9** | 23 | ❌ Missing in local |
| **TABLE 4.3** | 41 | ❌ Missing in local (AI-discovered) |
| **TABLE 8.1** | 86 | ❌ Missing in local |
| **C1** | 88 | ❌ Missing in local |
| **TABLE C8** | 107 | ❌ Missing in local (local has [None] on page 107) |
| **TABLE D2** | 119 | ⚠️ Duplicate of D2 (AI + standard extraction) |

### Tables ONLY in Local (8 tables)

| Table Number | Page | Notes |
|--------------|------|-------|
| **None** | 31 | ❌ Missing in GitHub |
| **E8** | 86 | ❌ Missing in GitHub (GitHub has TABLE 8.1 on same page) |
| **C7** | 105 | ❌ Missing in GitHub |
| **None** | 107 | ❌ Missing in GitHub (GitHub has TABLE C8 on same page) |
| **D5** | 121 | ❌ Missing in GitHub |
| **D9** | 124 | ❌ Missing in GitHub |
| **E12** | 143 | ❌ Missing in GitHub |
| **None** | 146 | ❌ Missing in GitHub |

---

## 📍 Page Coverage Analysis

### GitHub Covers (18 pages)
```
15, 23, 41, 86, 88, 100, 107, 114, 115, 116, 118, 119, 120, 126, 133, 142, 149, 151
```

### Local Covers (21 pages)
```
15, 31, 86, 100, 105, 107, 114, 115, 116, 118, 119, 120, 121, 124, 126, 133, 142, 143, 146, 149, 151
```

### Unique to Local (+6 pages)
```
Pages: 31, 105, 121, 124, 143, 146
```
**Impact**: Local found 6 additional table-bearing pages

### Unique to GitHub (+3 pages)
```
Pages: 23, 41, 88
```
**Impact**: GitHub found 3 pages that local missed
- Page 41 was AI-discovered (TABLE 4.3)
- Page 23 has Table 3.9
- Page 88 has Table C1

---

## 🎯 Key Differences Explained

### Why Does Local Have More Tables?

1. **More Aggressive Detection**: Local run may have looser thresholds
2. **Different Configuration**: AI features may be configured differently
3. **Processing Parameters**: Page sweep, fusion triggers, or filtering settings may differ
4. **Run Timing**: Different versions of the pipeline code

### Why Does GitHub Miss Some Tables?

1. **Stricter Filtering**: GitHub may have stricter quality thresholds to reduce false positives
2. **AI Discovery Limitations**: AI found page 41 but missed pages 31, 105, 121, 124, 143, 146
3. **Caption Detection**: Tables without numbers harder to find (5 in local vs 2 in GitHub)
4. **Deduplication**: GitHub may have removed some tables deemed duplicates

### Why Does GitHub Find Tables Local Missed?

1. **AI Discovery**: TABLE 4.3 on page 41 was AI-discovered
2. **Better Caption Detection**: Found properly numbered tables (3.9, TABLE 8.1, C1, TABLE C8)
3. **Multi-Engine Success**: Different engine combinations succeeded on pages 23, 86, 88

---

## 🔬 Interesting Cases

### Case 1: Page 86 Discrepancy
- **GitHub**: Found "TABLE 8.1" 
- **Local**: Found "E8"
- **Analysis**: Different table detected, or same table with different caption parsing?

### Case 2: Page 107 Discrepancy
- **GitHub**: Found "TABLE C8" (camelot:stream)
- **Local**: Found "[None]" (uncaptioned table)
- **Analysis**: Same table region, but different caption detection success

### Case 3: Page 119 Duplicate (GitHub only)
- **Row 12**: TABLE D2 (ai_discovery+pdfplumber)
- **Row 13**: D2 (pdfplumber)
- **Analysis**: AI and geometric detection both found same table, deduplication failed

### Case 4: Missing Numbered Tables (Local)
Local missed several properly numbered tables that GitHub found:
- 3.9 (page 23)
- TABLE 4.3 (page 41) - AI-discovered
- TABLE 8.1 (page 86)
- C1 (page 88)
- TABLE C8 (page 107)

This suggests local may have **stricter rejection criteria** or **different engine priorities**.

---

## 🎓 Analysis Conclusions

### GitHub (AI-Enhanced) Strengths
✅ Better caption detection (17 numbered vs 16)
✅ AI successfully discovered TABLE 4.3
✅ Found important early tables (3.9, 4.3, 8.1, C1)
✅ Fewer uncaptioned tables (2 vs 5) - better quality signal

### GitHub (AI-Enhanced) Weaknesses
❌ Missed 6 pages that local found (31, 105, 121, 124, 143, 146)
❌ Duplicate table on page 119 (deduplication issue)
❌ Overall fewer tables (19 vs 21)

### Local Run Strengths
✅ More comprehensive coverage (21 tables vs 19)
✅ Found 6 additional table-bearing pages
✅ No duplicate tables detected
✅ Found tables D5, D9, E12 that GitHub missed

### Local Run Weaknesses
❌ Missed AI-discoverable table (TABLE 4.3)
❌ Missed important numbered tables (3.9, 8.1, C1, C8)
❌ More uncaptioned tables (5 vs 2) - lower quality?
❌ Missed 3 pages GitHub found (23, 41, 88)

---

## 🚀 Recommendations

### For Maximum Coverage
**Combine Both Approaches:**
- Unique to GitHub: 6 tables (pages 23, 41, 88)
- Unique to Local: 8 tables (pages 31, 105, 121, 124, 143, 146)
- Shared: 13 tables
- **Theoretical Maximum**: 27 tables (if deduplicated properly)

### Configuration Recommendations

1. **Investigate Settings**: Compare `.env` and config between runs
   - AI feature flags (ENABLE_AI_TABLE_DISCOVERY, etc.)
   - Fusion thresholds (TABLE_PIPELINE_FUSION_TRIGGER_SCORE)
   - Page sweep settings (TABLE_PIPELINE_PAGE_SWEEP_WHEN_EMPTY)
   - Quality thresholds

2. **Fix Deduplication**: Address TABLE D2 duplicate in GitHub output

3. **Caption Detection**: Understand why local has more uncaptioned tables

4. **Engine Priority**: Investigate why different engines succeeded in each run

### Testing Recommendations

Create a **ground truth comparison** against expected tables in AS3000 2018:
- Manual page-by-page review
- Document all expected tables with page numbers
- Compare both outputs against ground truth
- Identify true positives, false positives, false negatives

---

## 📊 Visualization Summary

```
GitHub AI:  ████████████████████ (19 tables, 18 pages)
Local Run:  ██████████████████████ (21 tables, 21 pages)
Combined:   ███████████████████████████ (27 unique tables, 24 pages)
```

**Overlap**: 13 tables (68% GitHub, 62% Local)
**Unique to GitHub**: 6 tables (32% GitHub)
**Unique to Local**: 8 tables (38% Local)

---

## 🎯 Next Steps

1. ✅ Document findings (this file)
2. ⏭️ Compare configuration settings between runs
3. ⏭️ Manual review of discrepancy pages (23, 31, 41, 86, 88, 105, 107, 121, 124, 143, 146)
4. ⏭️ Create ground truth table list for AS3000 2018
5. ⏭️ Run test with combined best settings from both approaches
6. ⏭️ Benchmark precision/recall against ground truth

---

**Date**: March 29, 2026
**Comparison**: GitHub (AI-enhanced) vs Local Latest Run
**Status**: ✅ Analysis Complete
