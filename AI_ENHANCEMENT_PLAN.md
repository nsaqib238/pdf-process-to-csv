# AI Enhancement Plan for Table Extraction Pipeline

**Date:** March 29, 2026  
**Current Coverage:** 19/56 tables (34%)  
**Target:** Significant improvement toward 100% coverage

---

## Executive Summary

This plan integrates AI/LLM capabilities into the existing deterministic pipeline to address the 66% gap (37 missing tables). The approach follows the P5 roadmap with **three complementary AI strategies**:

1. **AI-Assisted Table Discovery** - Find tables missed by geometric detection
2. **AI-Powered Caption Detection** - Handle non-standard caption formats
3. **AI-Based Structure Validation** - Fix malformed extractions and reject prose

---

## Strategy 1: AI-Assisted Table Discovery

### Problem
Current pipeline relies on geometric features (lines, spacing, captions) which miss:
- Tables embedded in clauses without clear captions
- Tables with unusual layouts (irregular grids, nested structures)
- Tables where text extraction fails but visual structure is clear

### Solution: Vision-Based Page Analysis

**Approach:** Use OpenAI Vision API (GPT-4 Vision) to analyze PDF page images and identify table regions.

**Implementation:**
```python
class AITableDiscovery:
    """Find tables missed by geometric detection using vision AI."""
    
    def discover_missing_tables(
        self, 
        pdf_path: str, 
        page_num: int,
        existing_tables: List[Table]
    ) -> List[Dict]:
        """
        Analyze page image to find tables not detected by pdfplumber/Camelot.
        
        Returns list of table regions with bboxes and metadata.
        """
        # 1. Render page to image (300 DPI)
        # 2. Call OpenAI Vision API with structured prompt
        # 3. Return detected table regions with confidence
```

**Prompt Strategy:**
```
You are analyzing a page from a technical standards document (AS/NZS 3000:2018).

TASK: Identify all tables on this page, including:
- Tables with clear gridlines
- Tables with minimal or no gridlines (spacing-based)
- Tables embedded in text sections
- Tables with non-standard captions

For each table, provide:
- Approximate bounding box (top, left, bottom, right as percentages of page)
- Table number if visible (e.g., "Table 3.2", "TABLE D12(A)")
- Brief description
- Confidence level (high/medium/low)

OUTPUT FORMAT (JSON):
{
  "tables": [
    {
      "bbox_percent": {"top": 15, "left": 10, "bottom": 45, "right": 90},
      "table_number": "3.8",
      "description": "Wire sizing requirements table",
      "confidence": "high",
      "caption_format": "standard"
    }
  ]
}

RULES:
- Do NOT include figures, diagrams, or images as tables
- Do NOT include running headers/footers
- Do NOT include clause text formatted as lists
- Include tables even without clear captions if grid structure is evident
```

**Triggering Conditions:**
- Run on pages where LIST OF TABLES indicates a table exists but nothing was extracted
- Optional: Run on all pages as validation pass (slower but comprehensive)

---

## Strategy 2: AI-Powered Caption Detection

### Problem
Current regex-based caption detection misses:
- "the following table shows..." (implicit caption)
- Tables referenced in preceding paragraphs
- Caption in margin/header instead of above table
- Multi-line captions with unusual punctuation

### Solution: LLM Text Analysis

**Approach:** Use OpenAI Chat API to analyze page text and identify table references.

**Implementation:**
```python
class AICaptionDetector:
    """Enhanced caption detection using LLM text understanding."""
    
    def find_table_references(
        self, 
        page_text: str,
        page_num: int
    ) -> List[TableReference]:
        """
        Analyze page text to find all table references including:
        - Explicit captions (Table 3.2)
        - Implicit references ("the following table", "as shown below")
        - Continuation markers ("Table 3.2 (continued)")
        
        Returns structured table reference metadata.
        """
```

**Prompt Strategy:**
```
You are analyzing text from page {page_num} of AS/NZS 3000:2018.

TASK: Find all references to tables, including:
1. Explicit captions: "Table 3.2", "TABLE D12(A)", etc.
2. Implicit references: "the following table", "as shown in the table below"
3. Continuation markers: "(continued)", "Table 3.2 cont."
4. Table references in body text: "refer to Table 3.8"

For each reference, provide:
- Table number (if explicit, otherwise null)
- Reference type: "explicit_caption", "implicit_reference", "continuation", "inline_reference"
- Location context: approximate position in text
- Continuation: true if this is a continuation of a previous table

OUTPUT FORMAT (JSON):
{
  "references": [
    {
      "table_number": "3.8",
      "type": "explicit_caption",
      "text_snippet": "Table 3.8—Maximum demand",
      "is_continuation": false,
      "confidence": "high"
    }
  ]
}

TEXT TO ANALYZE:
{page_text}
```

**Integration:**
- Run before geometric detection to identify expected tables
- Use results to guide caption anchor search with relaxed constraints
- Cross-reference with LIST OF TABLES expectations

---

## Strategy 3: AI-Based Structure Validation

### Problem
Current quality scoring rejects valid tables and accepts malformed ones:
- Complex multi-row headers misidentified as prose
- Valid sparse tables rejected for low fill ratio
- Clause fragments with table-like structure accepted

### Solution: Vision + Structure Analysis

**Approach:** For borderline cases, use AI to validate structure and correct errors.

**Implementation:**
```python
class AIStructureValidator:
    """Validate and repair table structures using vision AI."""
    
    def validate_table(
        self,
        table: Table,
        page_crop_image: Image,
        quality_components: _QualityComponents
    ) -> ValidationResult:
        """
        For tables with borderline quality scores, use AI to:
        1. Confirm this is actually a table (vs prose/clause)
        2. Validate column/row structure
        3. Suggest corrections for malformed extractions
        
        Returns validation decision and optional corrected structure.
        """
```

**Prompt Strategy:**
```
You are validating a table extraction from a technical standards document.

CONTEXT:
- Extracted table has {row_count} rows and {col_count} columns
- Quality score: {quality_score} (borderline)
- Concerns: {quality_issues}

IMAGE: [cropped table region]

CURRENT STRUCTURE (JSON):
{table_json}

TASK:
1. Is this ACTUALLY a table? (vs clause text, list, diagram)
2. If YES - is the structure correct?
   - Are columns properly detected?
   - Are headers correctly identified?
   - Are there merged cells or multi-row headers?
3. If structure needs correction, provide specific fixes

OUTPUT FORMAT (JSON):
{
  "is_table": true/false,
  "confidence": "high/medium/low",
  "reasoning": "Brief explanation",
  "structure_correct": true/false,
  "suggested_corrections": [
    {
      "issue": "Header row should span rows 0-1",
      "fix": {"header_rows": [[row0], [row1]]}
    }
  ]
}

RULES:
- Reject clause text even if formatted in columns
- Accept sparse tables if clear grid structure exists
- Do NOT modify cell content, only structure
```

**Triggering Conditions:**
- Quality score between 0.4-0.7 (borderline)
- Semantic hard fail detected
- Single-column with caption (potential list vs table)
- High noise ratio but table number present

---

## Architecture Integration

### Pipeline Flow with AI Enhancement

```
┌─────────────────────────────────────────────────────────────┐
│                     FOR EACH PAGE                            │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  PHASE 1: AI-Assisted Discovery (if enabled)                │
│  - Vision API analyzes page image                            │
│  - Returns expected table regions + numbers                  │
│  - Feeds into caption anchor search                          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  PHASE 2: Enhanced Caption Detection                        │
│  - AI text analysis for implicit references                  │
│  - Regex patterns (existing)                                 │
│  - Merge results for comprehensive anchor list               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  PHASE 3: Geometric Extraction (existing)                   │
│  - pdfplumber + Camelot + Tabula                            │
│  - Multi-engine fusion                                       │
│  - Quality scoring                                           │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  PHASE 4: AI Structure Validation (for borderline cases)   │
│  - Vision + structure analysis                               │
│  - Validate table vs prose                                   │
│  - Suggest structural corrections                            │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  PHASE 5: Final Output (existing)                           │
│  - Apply AI corrections                                      │
│  - Generate tables.json                                      │
│  - Log AI decisions in extraction_notes                      │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Phases

### Phase 1: Setup & Configuration (Week 1)
- [ ] Add OpenAI Python SDK to requirements
- [ ] Create AI service abstraction layer
- [ ] Add configuration flags:
  - `ENABLE_AI_TABLE_DISCOVERY` (default: false)
  - `ENABLE_AI_CAPTION_DETECTION` (default: false)
  - `ENABLE_AI_STRUCTURE_VALIDATION` (default: false)
  - `OPENAI_API_KEY` (required if any AI feature enabled)
  - `OPENAI_MODEL` (default: "gpt-4o")
  - `AI_MAX_CALLS_PER_JOB` (default: 100, cost control)

### Phase 2: AI Service Infrastructure (Week 1)
- [ ] Create `backend/services/ai_table_service.py`
- [ ] Implement retry logic with exponential backoff
- [ ] Add response validation and schema enforcement
- [ ] Implement cost tracking and logging
- [ ] Create fallback mechanisms for API failures

### Phase 3: AI Table Discovery (Week 2)
- [ ] Implement `AITableDiscovery` class
- [ ] Integrate with page processing loop
- [ ] Add PDF page to image rendering
- [ ] Create vision API prompt templates
- [ ] Test on known missing tables from LIST OF TABLES

### Phase 4: AI Caption Detection (Week 2)
- [ ] Implement `AICaptionDetector` class
- [ ] Integrate with caption anchor search
- [ ] Create text analysis prompt templates
- [ ] Test on pages with implicit table references
- [ ] Merge with existing regex-based detection

### Phase 5: AI Structure Validation (Week 3)
- [ ] Implement `AIStructureValidator` class
- [ ] Integrate into quality scoring pipeline
- [ ] Create validation prompt templates
- [ ] Test on borderline quality tables
- [ ] Implement structure correction logic

### Phase 6: Testing & Optimization (Week 4)
- [ ] Run full extraction on AS3000 2018.pdf with AI enabled
- [ ] Measure coverage improvement (target: 40/56+ tables)
- [ ] Analyze cost per PDF (API calls × token usage)
- [ ] Optimize prompts for token efficiency
- [ ] Create comprehensive documentation

---

## Expected Improvements

### Coverage Gains (Estimated)

| Strategy | Expected New Tables | Reasoning |
|----------|-------------------|-----------|
| **AI Discovery** | +8-12 tables | Finds tables with unusual layouts, missing captions |
| **AI Caption Detection** | +3-5 tables | Catches implicit references, non-standard formats |
| **AI Validation** | +2-3 tables | Rescues valid tables rejected by quality scoring |
| **TOTAL** | **+13-20 tables** | **Target: 32-39 of 56 (57-70% coverage)** |

### Quality Improvements
- **Fewer false positives:** AI validation rejects clause fragments more accurately
- **Better structure:** Multi-row headers correctly identified
- **Reduced manual review:** Higher confidence scores with AI validation

---

## Cost Analysis

### Per-PDF Processing Cost (Estimated)

**Assumptions:**
- PDF: 100 pages
- AI Discovery: 100 vision API calls (1 per page)
- AI Caption: 100 text API calls (1 per page)
- AI Validation: 20 vision API calls (borderline tables only)

**OpenAI Pricing (GPT-4o):**
- Vision input: ~$2.50 per 1M tokens (~400 tokens per image)
- Text input: ~$2.50 per 1M tokens
- Output: ~$10 per 1M tokens

**Estimated Cost per PDF:**
- Discovery: 100 calls × 400 tokens × $2.50/1M = **$0.10**
- Caption: 100 calls × 500 tokens × $2.50/1M = **$0.13**
- Validation: 20 calls × 600 tokens × $2.50/1M = **$0.03**
- Output tokens: 220 calls × 200 tokens × $10/1M = **$0.44**
- **TOTAL: ~$0.70 per PDF**

**Cost Control:**
- `AI_MAX_CALLS_PER_JOB` limit prevents runaway costs
- Selective triggering (only borderline cases for validation)
- Batch multiple pages per API call when possible
- Cache results for repeated processing

---

## Risk Mitigation

### Technical Risks
- **API Availability:** Implement retry logic + fallback to deterministic pipeline
- **Response Quality:** Validate all JSON responses, reject malformed output
- **Performance:** Make AI features optional, allow parallel API calls

### Operational Risks
- **Cost Overruns:** Implement hard limits, monitoring, and alerts
- **Privacy:** Document that page images are sent to OpenAI (data retention policy)
- **Reproducibility:** Log all AI decisions, model versions, and prompts

### Quality Risks
- **Hallucinations:** Validate AI output against geometric constraints
- **Inconsistency:** Use temperature=0, log all decisions for audit
- **Regressions:** Keep deterministic pipeline as baseline, AI is additive

---

## Configuration Example

```python
# backend/config.py additions

class Settings(BaseSettings):
    # ... existing settings ...
    
    # AI Enhancement (optional, default disabled)
    enable_ai_table_discovery: bool = False
    enable_ai_caption_detection: bool = False
    enable_ai_structure_validation: bool = False
    
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o"
    openai_max_retries: int = 3
    
    ai_max_calls_per_job: int = 100
    ai_discovery_confidence_threshold: float = 0.7
    ai_validation_quality_threshold: float = 0.6
    
    # Cost tracking
    ai_log_token_usage: bool = True
    ai_alert_cost_threshold: float = 5.0  # USD per job
```

---

## Success Metrics

### Primary Goal
- **Coverage:** Increase from 34% (19/56) to **60%+ (34/56)** on AS3000 2018.pdf

### Secondary Goals
- **Precision:** Maintain or improve (no new false positives)
- **Cost Efficiency:** < $1.00 per 100-page PDF
- **Performance:** < 2x processing time with AI enabled
- **Auditability:** 100% of AI decisions logged

### Measurement
```python
# Extraction diagnostics additions
{
  "ai_discovery_calls": 100,
  "ai_discovery_tables_found": 12,
  "ai_caption_calls": 100,
  "ai_caption_new_anchors": 5,
  "ai_validation_calls": 20,
  "ai_validation_accepted": 15,
  "ai_validation_rejected": 5,
  "ai_total_cost_usd": 0.68,
  "ai_total_tokens": 125000
}
```

---

## Next Steps

1. **Immediate:** Review and approve this plan
2. **Week 1:** Implement AI service infrastructure + configuration
3. **Week 2:** Implement discovery + caption detection
4. **Week 3:** Implement structure validation
5. **Week 4:** Full testing on AS3000 2018.pdf + documentation

**Decision Point:** Should we proceed with full implementation or create a proof-of-concept with one strategy first?
