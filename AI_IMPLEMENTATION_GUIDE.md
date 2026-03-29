# AI Table Enhancement - Implementation Guide

**Status:** Infrastructure Complete, Ready for Integration Testing  
**Date:** March 29, 2026

---

## What Has Been Implemented

### ✅ Core Infrastructure (Completed)

1. **AI Service Layer** (`backend/services/ai_table_service.py`)
   - Complete OpenAI API integration with retry logic
   - Cost tracking and token usage monitoring
   - Three main strategies implemented:
     - `discover_tables()` - Vision-based table discovery
     - `detect_captions()` - Text-based caption detection
     - `validate_structure()` - Vision-based structure validation

2. **Configuration System** (`backend/config.py`)
   - All AI feature flags with safe defaults (disabled)
   - OpenAI API configuration (model, retries, timeouts)
   - Cost control settings (max calls, alert thresholds)

3. **Dependencies** (`backend/requirements.txt`)
   - OpenAI Python SDK added (`openai>=1.12.0`)
   - Already installed in environment

4. **Environment Configuration** (`backend/.env.example`)
   - Complete documentation for AI features
   - Example configuration values
   - Cost estimates and usage guidance

5. **Comprehensive Documentation**
   - `AI_ENHANCEMENT_PLAN.md` - Full architecture and strategy
   - `AI_IMPLEMENTATION_GUIDE.md` (this file) - Implementation steps

---

## How to Enable AI Features

### Step 1: Get OpenAI API Key

1. Visit https://platform.openai.com/api-keys
2. Create a new API key
3. Copy the key (starts with `sk-proj-...`)

### Step 2: Configure Environment

Create or edit `backend/.env`:

```bash
# Required for AI features
OPENAI_API_KEY=sk-proj-your-actual-api-key-here

# Enable individual features (default: false)
ENABLE_AI_TABLE_DISCOVERY=true
ENABLE_AI_CAPTION_DETECTION=true
ENABLE_AI_STRUCTURE_VALIDATION=true

# Optional: Customize settings
OPENAI_MODEL=gpt-4o
AI_MAX_CALLS_PER_JOB=100
AI_ALERT_COST_THRESHOLD=5.0
```

### Step 3: Test AI Service

```python
# backend/test_ai_service.py
from services.ai_table_service import get_ai_service
from PIL import Image

# Test initialization
ai_service = get_ai_service()
print(f"Discovery enabled: {ai_service.discovery_enabled}")
print(f"Caption enabled: {ai_service.caption_enabled}")
print(f"Validation enabled: {ai_service.validation_enabled}")

# Test discovery (requires image)
# image = Image.open("test_page.png")
# regions = ai_service.discover_tables(image, page_num=1)
# print(f"Discovered {len(regions)} tables")

# Check metrics
metrics = ai_service.get_metrics()
print(f"Cost so far: ${metrics['ai_total_cost_usd']}")
```

---

## Integration Points in Pipeline

### Integration Point 1: AI Table Discovery

**Location:** `table_pipeline.py` → `_extract_raw_tables_pdfplumber()` method (line 1535)

**When to call:** After caption anchor pass, before regular pdfplumber extraction

**Purpose:** Find tables that geometric detection misses

**Implementation:**

```python
def _extract_raw_tables_pdfplumber(self, source_pdf_path: str) -> List[_RawTable]:
    import pdfplumber
    from services.ai_table_service import get_ai_service
    
    ai_service = get_ai_service()
    out: List[_RawTable] = []
    
    # ... existing setup code ...
    
    with pdfplumber.open(source_pdf_path) as pdf:
        # ... existing caption anchor pass ...
        
        # NEW: AI Discovery Pass (before geometric extraction)
        if ai_service.discovery_enabled:
            for page_num in range(1, last_page + 1):
                page = pdf.pages[page_num - 1]
                
                # Render page to image
                page_image = page.to_image(resolution=150).original
                
                # Get existing table bboxes to avoid duplicates
                existing_bboxes = [rt.bbox for rt in out if rt.page_start == page_num]
                
                # Discover tables with AI
                discovered = ai_service.discover_tables(
                    page_image=page_image,
                    page_num=page_num,
                    existing_table_bboxes=existing_bboxes
                )
                
                # Convert AI discoveries to _RawTable format
                for region in discovered:
                    # Convert percentage bbox to page coordinates
                    bbox = self._percent_bbox_to_absolute(
                        region.bbox_percent,
                        float(page.width),
                        float(page.height)
                    )
                    
                    # Extract table from discovered region
                    ai_raw_table = self._extract_table_from_ai_region(
                        page=page,
                        page_num=page_num,
                        bbox=bbox,
                        table_number=region.table_number,
                        description=region.description
                    )
                    
                    if ai_raw_table and len(ai_raw_table.rows) >= 2:
                        out.append(ai_raw_table)
        
        # Continue with existing geometric extraction...
```

**Helper methods to add:**

```python
def _percent_bbox_to_absolute(
    self,
    bbox_percent: Dict[str, float],
    page_width: float,
    page_height: float
) -> Tuple[float, float, float, float]:
    """Convert percentage-based bbox to absolute coordinates."""
    x0 = (bbox_percent["left"] / 100) * page_width
    y0 = (bbox_percent["top"] / 100) * page_height
    x1 = (bbox_percent["right"] / 100) * page_width
    y1 = (bbox_percent["bottom"] / 100) * page_height
    return (x0, y0, x1, y1)

def _extract_table_from_ai_region(
    self,
    page: Any,
    page_num: int,
    bbox: Tuple[float, float, float, float],
    table_number: Optional[str],
    description: str
) -> Optional[_RawTable]:
    """Extract table from AI-discovered region."""
    try:
        # Crop to region and try extraction
        crop = page.crop(bbox)
        tables = crop.find_tables() or []
        
        if tables:
            # Use the best matching table
            t = tables[0]
            rows = t.extract() or []
            norm_rows = self._normalize_rows(rows)
            
            if len(norm_rows) >= 2:
                return _RawTable(
                    page_start=page_num,
                    page_end=page_num,
                    bbox=bbox,
                    rows=norm_rows,
                    table_number=table_number,
                    title=description,
                    source_method="ai_discovery+pdfplumber",
                    continuation_caption=False
                )
    except Exception as e:
        logger.debug(f"Failed to extract AI-discovered table: {e}")
    
    return None
```

### Integration Point 2: AI Caption Detection

**Location:** `table_pipeline.py` → `_discover_caption_anchors_from_page_words()` method (line 1159)

**When to call:** Alongside word-based caption detection

**Purpose:** Find implicit table references and non-standard captions

**Implementation:**

```python
def _discover_caption_anchors_from_page_words(
    self, page_words: List[dict], page_width: float, page_height: float, page_text: str, page_num: int
) -> List[_CaptionAnchor]:
    from services.ai_table_service import get_ai_service
    
    if not page_words:
        return []
    
    # Existing word-based detection
    lines = self._cluster_words_into_lines(page_words, y_tol=3.6)
    out: List[_CaptionAnchor] = []
    
    # ... existing logic for word-based caption detection ...
    
    # NEW: AI Caption Detection
    ai_service = get_ai_service()
    if ai_service.caption_enabled:
        ai_references = ai_service.detect_captions(page_text, page_num)
        
        for ref in ai_references:
            # Skip inline references (only want captions)
            if ref.reference_type == "inline_reference":
                continue
            
            # For implicit references without bbox, estimate location
            if ref.table_number:
                # Try to find approximate bbox from text snippet
                bbox = self._estimate_caption_bbox_from_text(
                    page_words, ref.text_snippet, page_width, page_height
                )
                
                if bbox:
                    out.append(
                        _CaptionAnchor(
                            table_number=ref.table_number,
                            title=None,
                            continuation=ref.is_continuation,
                            line_bbox=bbox
                        )
                    )
    
    out.sort(key=lambda a: a.line_bbox[1])
    return out
```

### Integration Point 3: AI Structure Validation

**Location:** `table_pipeline.py` → `_extract_best_tiered()` method (line 1041)

**When to call:** After quality scoring, for borderline cases

**Purpose:** Validate structure and reject prose disguised as tables

**Implementation:**

```python
def _extract_best_tiered(
    self, source_pdf_path: str, anchor: _RawTable, clauses: List[Any]
) -> Tuple[Table, _RawTable, List[str]]:
    from services.ai_table_service import get_ai_service
    
    notes: List[str] = []
    best_rt = anchor
    best_table = self._to_table_model(anchor, clauses)
    best_q = self._quality_components(best_table)
    
    # ... existing fusion logic ...
    # ... existing OCR logic ...
    
    # NEW: AI Structure Validation (for borderline cases)
    ai_service = get_ai_service()
    if ai_service.validation_enabled:
        quality_score = best_q.score
        
        # Only validate borderline cases (0.4-0.7 range)
        if 0.4 <= quality_score <= 0.7:
            # Render table region to image
            import pdfplumber
            with pdfplumber.open(source_pdf_path) as pdf:
                page = pdf.pages[best_rt.page_start - 1]
                crop = page.crop(best_rt.bbox)
                crop_image = crop.to_image(resolution=200).original
            
            # Get quality issues for context
            quality_issues = []
            if best_q.semantic_hard_fail:
                quality_issues.append("semantic_hard_fail")
            if best_q.noise_ratio > 0.15:
                quality_issues.append(f"high_noise_ratio:{best_q.noise_ratio:.2f}")
            if best_q.fill_ratio < 0.25:
                quality_issues.append(f"low_fill_ratio:{best_q.fill_ratio:.2f}")
            
            # Convert table to JSON for AI
            table_json = {
                "table_number": best_table.table_number,
                "header_rows": [{"cells": hr.cells} for hr in (best_table.header_rows or [])],
                "data_rows": [{"cells": dr.cells} for dr in (best_table.data_rows or [])[:5]],  # First 5 rows
            }
            
            # Validate with AI
            validation = ai_service.validate_structure(
                table_json=table_json,
                page_crop_image=crop_image,
                quality_score=quality_score,
                quality_issues=quality_issues
            )
            
            if validation:
                if not validation.is_table:
                    # AI rejected as non-table
                    notes.append(f"ai_rejected:{validation.reasoning}")
                    # Mark for omission by lowering quality score dramatically
                    best_q = best_q._replace(semantic_hard_fail=True, score=-1.0)
                elif not validation.structure_correct and validation.suggested_corrections:
                    # AI suggests structural corrections
                    notes.append(f"ai_structure_corrections:{len(validation.suggested_corrections)}")
                    # TODO: Apply suggested corrections
                else:
                    # AI confirmed table is acceptable
                    notes.append("ai_validated:accepted")
    
    return best_table, best_rt, notes
```

---

## Adding AI Metrics to Diagnostics

**Location:** `table_pipeline.py` → `extract_tables()` method (line 1005-1038)

**Update logging to include AI metrics:**

```python
# In extract_tables() method, after existing diagnostic logging:

# Get AI metrics if service was used
from services.ai_table_service import get_ai_service
ai_service = get_ai_service()
ai_metrics = ai_service.get_metrics()

if ai_metrics.get("ai_discovery_calls", 0) > 0 or ai_metrics.get("ai_validation_calls", 0) > 0:
    logger.info(
        "AI Enhancement metrics: discovery_calls=%s tables_found=%s caption_calls=%s "
        "validation_calls=%s validated_accepted=%s validated_rejected=%s "
        "total_cost_usd=%.4f total_tokens=%s errors=%s",
        ai_metrics["ai_discovery_calls"],
        ai_metrics["ai_discovery_tables_found"],
        ai_metrics["ai_caption_calls"],
        ai_metrics["ai_validation_calls"],
        ai_metrics["ai_validation_accepted"],
        ai_metrics["ai_validation_rejected"],
        ai_metrics["ai_total_cost_usd"],
        ai_metrics["ai_total_tokens"],
        ai_metrics["ai_errors"]
    )

# Reset metrics for next job
ai_service.reset_metrics()
```

---

## Testing Strategy

### Phase 1: Unit Tests (AI Service Only)

```bash
cd backend
python -c "
from services.ai_table_service import get_ai_service
ai = get_ai_service()
print(f'Service initialized: {ai.client is not None}')
print(f'Discovery enabled: {ai.discovery_enabled}')
print(f'Caption enabled: {ai.caption_enabled}')
print(f'Validation enabled: {ai.validation_enabled}')
"
```

### Phase 2: Integration Test (Single Page)

1. Enable AI features in `.env`
2. Process a single page known to have missing tables
3. Check for AI-discovered tables in output
4. Monitor cost metrics

```bash
cd backend
# Set ENABLE_AI_TABLE_DISCOVERY=true in .env
python run_local_tables.py "../Tables AS3000 2018.pdf" --max-pages 1 --out-dir ../output/ai_test
```

### Phase 3: Full Document Test

1. Process entire AS3000 2018.pdf with AI enabled
2. Compare coverage: current 19/56 → target 30+/56
3. Analyze cost per PDF
4. Review AI decisions in extraction_notes

```bash
cd backend
python run_local_tables.py "../Tables AS3000 2018.pdf" --out-dir ../output/ai_full_test
```

---

## Expected Results

### Coverage Improvement

| Strategy | Expected Gain | Confidence |
|----------|--------------|------------|
| AI Discovery | +8-12 tables | High |
| AI Caption Detection | +3-5 tables | Medium |
| AI Validation | +2-3 tables | Medium |
| **Total** | **+13-20 tables** | **Target: 32-39/56 (57-70%)** |

### Cost Estimate

- **Per Page:** ~$0.007 (with all AI features enabled)
- **Per 100-page PDF:** ~$0.70
- **AS3000 2018.pdf (~200 pages):** ~$1.40

### Performance Impact

- **Without AI:** ~2-3 seconds per page
- **With AI enabled:** ~4-6 seconds per page (2x slower)
- **Worth it?** Yes, for significant coverage improvement

---

## Rollback Plan

If AI integration causes issues:

1. **Disable AI features** in `.env`:
   ```bash
   ENABLE_AI_TABLE_DISCOVERY=false
   ENABLE_AI_CAPTION_DETECTION=false
   ENABLE_AI_STRUCTURE_VALIDATION=false
   ```

2. **Pipeline reverts to deterministic behavior** automatically (all AI calls are gated by feature flags)

3. **No code changes needed** - infrastructure is designed to fail gracefully

---

## Next Steps

1. ✅ Infrastructure complete
2. ⏳ Add integration points (see above sections)
3. ⏳ Unit test AI service
4. ⏳ Integration test single page
5. ⏳ Full document test
6. ⏳ Analyze results and optimize
7. ⏳ Update README with AI features

---

## Support & Troubleshooting

### Common Issues

**Issue:** "OpenAI SDK not installed"
```bash
cd backend
pip install openai
```

**Issue:** "AI features enabled but OPENAI_API_KEY not set"
- Add `OPENAI_API_KEY=sk-proj-...` to `backend/.env`

**Issue:** "AI cost threshold reached"
- Increase `AI_ALERT_COST_THRESHOLD` in `.env` or reduce `AI_MAX_CALLS_PER_JOB`

**Issue:** "Vision API call failed"
- Check API key validity
- Check OpenAI API status: https://status.openai.com
- Review error logs for specific failure reason

### Debug Mode

Enable detailed AI logging:

```python
# backend/services/ai_table_service.py
# Change logging level
logger.setLevel(logging.DEBUG)
```

---

## Conclusion

The AI enhancement infrastructure is **complete and ready for integration testing**. All three strategies (discovery, caption detection, validation) are implemented with proper error handling, cost tracking, and feature flags.

**To proceed:**
1. Get OpenAI API key
2. Enable features in `.env`
3. Follow integration points above
4. Test on single page first
5. Expand to full document

**Expected outcome:** Significant coverage improvement (34% → 60%+) with acceptable cost (~$1.50 per PDF) and performance impact (2x slower but worth it for quality improvement).
