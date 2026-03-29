# tables.json Output Reference

Complete documentation of the `tables.json` output format with real examples from AS3000 2018 extraction.

## Overview

The `tables.json` file contains an array of extracted table objects. Each table includes:
- Structured data (headers, rows, cells)
- Metadata (page location, table number, source method)
- Quality metrics and confidence scores
- Header reconstruction analysis
- Extraction diagnostics

## File Location

```bash
# CLI extraction (default)
<pdf_directory>/<pdf_stem>_tables_out/tables.json

# Example
input/AS3000 2018_tables_out/tables.json

# Web API extraction
outputs/<job_id>/tables.json
```

---

## Complete Table Object Structure

```json
{
  // ==========================================
  // CORE IDENTIFICATION
  // ==========================================
  "table_id": "table_d661a0ae",           // Unique ID for this extraction
  "table_number": "3.1",                   // Caption number (e.g., "3.1", "C7", "D11")
                                          // null if unnumbered
  "title": null,                          // Table title/caption text (usually null)
  "parent_clause_reference": null,        // Parent clause ID (null in tables-only mode)
  
  // ==========================================
  // PAGE LOCATION
  // ==========================================
  "page_start": 154,                      // First page (1-indexed)
  "page_end": 155,                        // Last page (same as start for single-page)
  "is_multipage": true,                   // Spans multiple pages?
  
  // ==========================================
  // TABLE DATA - HEADER ROWS
  // ==========================================
  "header_rows": [
    {
      "cells": [
        "Column 1",                        // Header cell text
        "Description_Unenclosed_I_I",
        "Description | On a surface..."
      ],
      "is_header": true
    }
  ],
  
  // ==========================================
  // TABLE DATA - DATA ROWS
  // ==========================================
  "data_rows": [
    {
      "cells": [
        "",                                // Cell content (empty string if blank)
        "In an enclosure",
        "On a surface (including cable trunking)"
      ],
      "is_header": false
    },
    {
      "cells": [
        "",
        "",
        "On a surface and partly surrounded by thermal insulation"
      ],
      "is_header": false
    }
    // ... more rows
  ],
  
  // ==========================================
  // FOOTER & NOTES
  // ==========================================
  "footer_notes": [],                     // Table footnotes (usually empty)
  
  // ==========================================
  // RAW FORMATS
  // ==========================================
  "raw_csv": "Stub,Description Unenclosed,...\r\n...",
                                          // CSV representation
  
  "normalized_text_representation": 
    "TABLE 3.1\nCOLUMNS: Stub | Description Unenclosed | ...\nROW 1: ...",
                                          // Human-readable text format
  
  // ==========================================
  // EXTRACTION METADATA
  // ==========================================
  "confidence": "low",                    // "high", "medium", or "low"
                                          // Based on unified_score:
                                          // high: >= 0.82
                                          // medium: >= 0.60
                                          // low: < 0.60
  
  "source_method": "pdfplumber",          // Extraction engine used
                                          // Options:
                                          // - "pdfplumber"
                                          // - "camelot:lattice"
                                          // - "camelot:stream"
                                          // - "tabula"
                                          // - "pdfplumber:caption_region+camelot_fusion"
                                          // - "ai_discovery+pdfplumber" (if AI enabled)
  
  "extraction_notes": [                   // Diagnostic information
    "fusion_win:camelot:lattice",         // Which engine won fusion
    "ai_validated:accepted",              // AI validation result (if enabled)
    "clause_shaped_rejected",             // Rejection reasons
    "sweep_gated_rejected"
  ],
  
  "table_key": "3.1:9c5572fb8babf028",    // Unique key: number + hash
  "continuation_of": null,                // ID of previous table if continuation
  
  // ==========================================
  // QUALITY METRICS
  // ==========================================
  "quality_metrics": {
    "fill_ratio": 0.4762,                 // % of non-empty cells (0-1)
    "col_count": 3,                       // Number of columns
    "data_row_count": 6,                  // Number of data rows
    "noise_ratio": 0.1,                   // % of noisy/junk content (0-1)
    "multiline_ratio": 0.2,               // % of multi-line cells (0-1)
    "diversity": 1.0,                     // Column content diversity (0-1)
    "placeholder_ratio": 0.5238,          // % of placeholder text (0-1)
    "garbage_cell_ratio": 0.0,            // % of garbage cells (0-1)
    "symbol_junk_ratio": 0.0,             // % of symbol junk (0-1)
    "ocr_mojibake_ratio": 0.0,            // % of OCR errors (0-1)
    "header_corrupt_ratio": 0.0,          // % of corrupted headers (0-1)
    "data_row_repeat_ratio": 0.1667,      // % of repeated rows (0-1)
    
    // P0 UPGRADE: Semantic validation
    "semantic_hard_fail": true,           // Failed clause-shaped detection?
    
    "unified_score": -0.3238,             // Overall quality score (-inf to 1.0)
                                          // >= 0.82: high confidence
                                          // >= 0.60: medium confidence
                                          // < 0.60: low confidence
    
    "penalty": 0.8,                       // Total quality penalty applied
    
    // P0 UPGRADE: Additional filters
    "one_column_value_list": false,       // Single column with values?
    "partial_fragment": false             // Incomplete table fragment?
  },
  
  // ==========================================
  // STRUCTURE FLAGS
  // ==========================================
  "has_headers": true,                    // Has header rows?
  "has_merged_cells": true,               // Contains merged cells?
  
  // ==========================================
  // HEADER RECONSTRUCTION (if enabled)
  // ==========================================
  "reconstructed_header_rows": [          // Cleaned/reconstructed headers
    {
      "cells": [
        "Stub",                            // Cleaned column names
        "Description Unenclosed",
        "Description | On a surface..."
      ],
      "is_header": true
    }
  ],
  
  "promoted_header_rows": [],             // Data rows promoted to headers (if any)
  
  "final_columns": [                      // Final column names (recommended)
    "Stub",
    "Description Unenclosed",
    "Description | On a surface (including cable tray or ladder) | ..."
  ],
  
  // ==========================================
  // HEADER ANALYSIS MODEL
  // ==========================================
  "header_model": {
    "table_type": "property",             // "matrix" or "property"
    "stub_column_index": 1,               // Index of stub column (0-based)
    "raw_header_row_count": 1,            // Original header rows
    "reconstructed_header_row_count": 1,  // After reconstruction
    "final_column_count": 3,              // Number of columns
    
    "header_tree": [                      // Hierarchical column structure
      {
        "name": "Stub",
        "children": []                    // No sub-columns
      },
      {
        "name": "Description Unenclosed",
        "children": []
      },
      {
        "name": "Description | On a surface...",
        "children": []
      }
    ],
    
    "row_debug": [                        // Detailed analysis of each row
      {
        "source": "header_rows",          // "header_rows" or "data_rows"
        "row_index": 0,
        "cells": ["Column 1", "Description Unenclosed I I", "..."],
        "analysis": {
          "score": 0.5262,                // Header-likeness score
          "text_ratio": 0.9524,           // % text content
          "numeric_ratio": 0.0476,        // % numeric content
          "header_hint_hits": 5,          // Count of header keywords
          "unit_hits": 2,                 // Count of unit symbols
          "category_hits": 0,             // Count of category words
          "multiline_ratio": 0.0,         // % multiline cells
          "junk_hits": 1                  // Count of junk indicators
        }
      },
      {
        "source": "data_rows",
        "row_index": 0,
        "cells": ["", "In an enclosure", "On a surface..."],
        "analysis": {
          "score": 0.41,
          "text_ratio": 1.0,
          "numeric_ratio": 0.0,
          "header_hint_hits": 1,
          "unit_hits": 1,
          "category_hits": 0,
          "multiline_ratio": 0.0,
          "junk_hits": 0
        },
        "max_header_similarity": 0.1818   // Similarity to known headers
      }
      // ... more rows
    ]
  }
}
```

---

## Real Examples

### Example 1: High Confidence Table (Camelot Fusion)

**Source:** Table 3.2 from AS3000 2018, page 6

```json
{
  "table_id": "table_6f13e801",
  "table_number": "3.2",
  "page_start": 6,
  "page_end": 6,
  "confidence": "medium",
  "source_method": "camelot:lattice",
  "extraction_notes": ["fusion_win:camelot:lattice"],
  
  "header_rows": [
    {
      "cells": [
        "> Type of cable insulation<1",
        "Operating temperature of conductor, •c | Normal use<2>",
        "Operating temperature of conductor, •c | Maximum permissiblel 7>",
        "Operating temperature of conductor, •c | Minimum ambient 13>"
      ],
      "is_header": true
    }
  ],
  
  "data_rows": [
    {
      "cells": [
        "Thermoplastic'4J V-75 HFl-75-TP, TPE-75 V-90 HFl-90-TP, TP-90 V-90HT",
        "75 75 75 75 75",
        "75 75 90 90 105",
        "0 - 20 0 - 20 0"
      ],
      "is_header": false
    },
    {
      "cells": [
        "Elastomeric R-EP-90 R-CPE-90, R-HF-90, R-CSP-90 R-HF- 110, R-E-110 R-S-150",
        "90 90 110 150",
        "90 90 110 150",
        "- 40 - 20 • - 50"
      ],
      "is_header": false
    }
  ],
  
  "quality_metrics": {
    "fill_ratio": 1.0,
    "col_count": 4,
    "data_row_count": 5,
    "unified_score": 0.345,
    "semantic_hard_fail": false
  },
  
  "final_columns": [
    "> Type of cable insulation<1",
    "Operating temperature of conductor, •c | Normal use<2>",
    "Operating temperature of conductor, •c | Maximum permissiblel 7>",
    "Operating temperature of conductor, •c | Minimum ambient 13>"
  ]
}
```

### Example 2: Low Confidence Multi-Page Table

**Source:** Table 3.1 from AS3000 2018, pages 154-155

```json
{
  "table_id": "table_d661a0ae",
  "table_number": "3.1",
  "page_start": 154,
  "page_end": 155,
  "is_multipage": true,
  "confidence": "low",
  "source_method": "pdfplumber",
  
  "quality_metrics": {
    "fill_ratio": 0.4762,
    "col_count": 3,
    "data_row_count": 6,
    "unified_score": -0.3238,
    "semantic_hard_fail": true
  }
}
```

---

## Quality Metrics Interpretation

### Confidence Levels

| Confidence | Unified Score | Meaning |
|-----------|---------------|---------|
| **high** | ≥ 0.82 | Excellent quality, reliable extraction |
| **medium** | 0.60 - 0.81 | Good quality, may have minor issues |
| **low** | < 0.60 | Poor quality, verify manually |

### Key Metrics to Check

**Fill Ratio** (`fill_ratio`)
- **> 0.8**: Well-populated table
- **0.5 - 0.8**: Sparse table (may be valid for some formats)
- **< 0.5**: Very sparse, possibly corrupt

**Semantic Hard Fail** (`semantic_hard_fail`)
- **false**: Passed clause-shaped detection (likely a real table)
- **true**: Failed validation (may be prose/normative text, not a table)

**Unified Score** (`unified_score`)
- **> 0.8**: High-quality extraction
- **0.6 - 0.8**: Acceptable quality
- **< 0.6**: Low quality, review extraction

---

## Extraction Methods

### source_method Values

| Method | Description | When Used |
|--------|-------------|-----------|
| `pdfplumber` | Primary geometric detection | Default for most tables |
| `camelot:lattice` | Grid-based extraction | Tables with clear borders |
| `camelot:stream` | Text-position based | Borderless tables |
| `tabula` | Java-based extraction | Complex layouts |
| `pdfplumber:caption_region+camelot_fusion` | Multi-engine fusion | Low pdfplumber score (<0.82) |
| `ai_discovery+pdfplumber` | AI-discovered region + extraction | AI enhancement enabled |

### extraction_notes Values

Common diagnostic notes:

- `fusion_win:camelot:lattice` - Camelot lattice won fusion battle
- `fusion_win:tabula` - Tabula won fusion battle
- `pdfplumber_first_pass_empty` - First pass found nothing, used loose tolerances
- `from_page_sweep` - Found during page sweep (when pdfplumber found 0 tables)
- `ai_validated:accepted` - AI validated structure (if AI enabled)
- `ai_validated:rejected` - AI rejected as prose (if AI enabled)
- `ai_discovered` - AI found this table region (if AI enabled)
- `clause_shaped_rejected` - Rejected by clause-likeness detector (P0 upgrade)
- `sweep_gated_rejected` - Rejected by sweep gating (single column prose)

---

## Header Reconstruction

When `ENABLE_HEADER_RECONSTRUCTION=true` (default), tables include additional header analysis:

### Key Fields

**`final_columns`** (Most Important)
- **Use this for column names** in your application
- Cleaned, reconstructed column headers
- Example: `["Stub", "Description Unenclosed", "Operating temperature | Normal use"]`

**`reconstructed_header_rows`**
- Cleaned header rows with merged cells preserved
- Better quality than raw `header_rows`

**`header_model.table_type`**
- `"matrix"`: Data matrix (typical table)
- `"property"`: Property-value pairs

**`header_model.stub_column_index`**
- Index of the leftmost label column (0-based)
- Example: 0 = first column, 1 = second column

**`header_model.row_debug`**
- Detailed analysis showing why each row was classified as header or data
- Useful for debugging extraction issues

---

## AI Enhancement Fields (Optional)

When AI features are enabled (`ENABLE_AI_TABLE_DISCOVERY=true`, etc.), additional metadata appears:

### AI-Discovered Tables

```json
{
  "source_method": "ai_discovery+pdfplumber",
  "extraction_notes": [
    "ai_discovered",
    "ai_confidence:high"
  ]
}
```

### AI-Validated Tables

```json
{
  "extraction_notes": [
    "ai_validated:accepted",
    "ai_structure_correct:true"
  ]
}
```

### AI-Rejected Tables

Tables rejected by AI validation are **not** included in the output.
Check logs for:
```
INFO: AI rejected table as prose: ...
```

---

## Common Patterns

### Unnumbered Tables

```json
{
  "table_number": null,
  "extraction_notes": ["unnumbered_table"]
}
```

**Note:** If `OMIT_UNNUMBERED_TABLE_FRAGMENTS=true`, low-quality unnumbered tables are excluded.

### Continuation Tables

```json
{
  "table_number": "3.4",
  "continuation_of": "table_abc123",
  "page_start": 47,
  "extraction_notes": ["continuation_merged"]
}
```

When `TABLE_PIPELINE_MERGE_ADJACENT_UNNUMBERED_CONTINUATION=true`, continuations are merged into the parent table.

### Failed Extractions

Tables that fail quality checks are rejected and **not** included in `tables.json`. Check logs for rejection counts:

```
INFO: Table pipeline complete: 24 tables extracted.
Upgrade metrics: clause_shaped_rejected=75, sweep_gated_rejected=0, schematic_rejected=3
```

---

## Using tables.json in Your Application

### Recommended Workflow

1. **Load the JSON**
   ```python
   import json
   with open('tables.json') as f:
       tables = json.load(f)
   ```

2. **Filter by confidence**
   ```python
   high_confidence = [t for t in tables if t['confidence'] == 'high']
   ```

3. **Use final_columns for headers**
   ```python
   for table in tables:
       columns = table['final_columns']
       # Use these as your column names
   ```

4. **Extract data rows**
   ```python
   for table in tables:
       for row in table['data_rows']:
           cells = row['cells']
           # Process cell data
   ```

5. **Check quality metrics**
   ```python
   for table in tables:
       metrics = table['quality_metrics']
       if metrics['unified_score'] < 0.6:
           print(f"Low quality: Table {table['table_number']}")
   ```

---

## Performance Metrics (AS3000 2018.pdf)

### Without AI Enhancement
- **Tables extracted:** 19/56 (34% coverage)
- **Processing time:** ~2-3 sec/page
- **Cost:** $0
- **Output file size:** ~350KB

### With AI Enhancement (Expected)
- **Tables extracted:** 32-39/56 (57-70% coverage)
- **Processing time:** ~4-6 sec/page
- **Cost:** ~$1.40 per 200-page PDF
- **Output file size:** ~600KB

---

## Troubleshooting

### Empty tables.json (`[]`)

**Causes:**
- No tables found in PDF
- All tables rejected by quality filters
- Incorrect PDF or processing error

**Solutions:**
1. Check logs for rejection counts
2. Try disabling filters: `OMIT_UNNUMBERED_TABLE_FRAGMENTS=false`
3. Lower quality threshold: `TABLE_PIPELINE_FUSION_TRIGGER_SCORE=0.6`
4. Enable AI discovery: `ENABLE_AI_TABLE_DISCOVERY=true`

### Low confidence tables

**Causes:**
- Complex table layouts
- Merged cells
- Scanned/image-based PDFs
- Non-standard formatting

**Solutions:**
1. Enable Camelot/Tabula fusion: `ENABLE_TABLE_CAMELOT_TABULA=true`
2. Enable header reconstruction: `ENABLE_HEADER_RECONSTRUCTION=true`
3. Enable AI validation: `ENABLE_AI_STRUCTURE_VALIDATION=true`

### Missing table numbers

**Causes:**
- Non-standard caption format
- Caption far from table
- No caption present

**Solutions:**
1. Increase caption search depth: `TABLE_PIPELINE_CAPTION_ANCHOR_MAX_DEPTH_PT=700`
2. Enable AI caption detection: `ENABLE_AI_CAPTION_DETECTION=true`

---

## Version History

- **Version 2.0** - Added AI enhancement fields
- **Version 1.3** - Improved OCR and caption detection
- **Version 1.2** - Relaxed quality thresholds
- **Version 1.1** - Added clause rejection and sweep gating
- **Version 1.0** - Initial P0-P4 upgrades with header reconstruction

---

## See Also

- `README.md` - Installation and usage guide
- `AI_ENHANCEMENT_PLAN.md` - AI feature architecture
- `TABLE_COVERAGE_REPORT.md` - Coverage analysis
- `PIPELINE_ARCHITECTURE.md` - Pipeline technical details
