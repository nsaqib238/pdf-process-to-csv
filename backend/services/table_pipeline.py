"""
Dedicated table extraction pipeline: pdfplumber primary, optional Camelot/Tabula fusion,
image OCR recovery, unified quality scoring (see TABLE_PIPELINE_PLAN.md).
"""
import csv
import hashlib
import logging
import re
import uuid
from dataclasses import dataclass
from io import StringIO
from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple

from models.table import ConfidenceLevel, Table, TableRow

logger = logging.getLogger(__name__)

try:
    from services.ai_table_service import get_ai_service
    _ai_service_available = True
except ImportError:
    _ai_service_available = False
    logger.warning("AI table service not available - AI enhancement disabled")


def _fusion_enabled() -> bool:
    try:
        from config import settings

        return bool(getattr(settings, "enable_table_camelot_tabula", False))
    except Exception:
        return False


def _omit_fragments_enabled() -> bool:
    try:
        from config import settings

        return bool(getattr(settings, "omit_unnumbered_table_fragments", False))
    except Exception:
        return False


def _table_pipeline_max_pages() -> Optional[int]:
    try:
        from config import settings

        v = getattr(settings, "table_pipeline_max_pages", None)
        if v is None:
            return None
        n = int(v)
        return n if n > 0 else None
    except Exception:
        return None


def _pdfplumber_table_settings() -> Optional[Dict[str, Any]]:
    try:
        from config import settings

        return {
            "snap_x_tolerance": int(getattr(settings, "table_snap_x_tolerance", 5)),
            "snap_y_tolerance": int(getattr(settings, "table_snap_y_tolerance", 5)),
            "intersection_tolerance": int(
                getattr(settings, "table_intersection_tolerance", 5)
            ),
            "join_x_tolerance": int(getattr(settings, "table_join_x_tolerance", 5)),
            # Text-based detection for borderless tables (Table 3.x series)
            "vertical_strategy": "lines_strict",  # Start with lines
            "horizontal_strategy": "lines_strict",
            "text_x_tolerance": 3,  # Tolerance for text column alignment
            "text_y_tolerance": 3,  # Tolerance for text row alignment
        }
    except Exception:
        return None


def _pdfplumber_loose_table_settings() -> Optional[Dict[str, Any]]:
    """Second-pass pdfplumber tolerances when the primary pass finds no tables on a page."""
    try:
        from config import settings

        if not getattr(settings, "table_pipeline_pdfplumber_loose_second_pass", True):
            return None
        base = _pdfplumber_table_settings()
        if not base:
            return None
        return {
            "snap_x_tolerance": int(base["snap_x_tolerance"]) + 5,
            "snap_y_tolerance": int(base["snap_y_tolerance"]) + 4,
            "intersection_tolerance": int(base["intersection_tolerance"]) + 4,
            "join_x_tolerance": int(base["join_x_tolerance"]) + 5,
            # More aggressive text-based detection in loose pass
            "vertical_strategy": "text",  # Use text edges for columns
            "horizontal_strategy": "text",  # Use text edges for rows
            "text_x_tolerance": 5,
            "text_y_tolerance": 5,
            "min_words_vertical": 3,  # Minimum words to infer a vertical line
            "min_words_horizontal": 1,  # Minimum words to infer a horizontal line
        }
    except Exception:
        return None


def _page_sweep_when_empty_enabled() -> bool:
    try:
        from config import settings

        return bool(getattr(settings, "table_pipeline_page_sweep_when_empty", True))
    except Exception:
        return False


def _page_sweep_max_per_page() -> int:
    try:
        from config import settings

        return max(1, int(getattr(settings, "table_pipeline_page_sweep_max_per_page", 8)))
    except Exception:
        return 8


def _caption_anchor_pass_enabled() -> bool:
    try:
        from config import settings

        return bool(getattr(settings, "table_pipeline_caption_anchor_pass", True))
    except Exception:
        return True


def _caption_anchor_max_depth_pt() -> float:
    try:
        from config import settings

        return float(getattr(settings, "table_pipeline_caption_anchor_max_depth_pt", 520.0))
    except Exception:
        return 520.0


def _caption_anchor_max_gap_pt() -> float:
    try:
        from config import settings

        return float(getattr(settings, "table_pipeline_caption_anchor_max_gap_pt", 300.0))
    except Exception:
        return 300.0


def _merge_adjacent_unnumbered_continuation_enabled() -> bool:
    try:
        from config import settings

        return bool(
            getattr(settings, "table_pipeline_merge_adjacent_unnumbered_continuation", True)
        )
    except Exception:
        return True


def _caption_region_multi_engine_enabled() -> bool:
    try:
        from config import settings

        return bool(getattr(settings, "table_pipeline_caption_region_multi_engine", True))
    except Exception:
        return True


def _caption_region_expand_when_empty() -> bool:
    try:
        from config import settings

        return bool(getattr(settings, "table_pipeline_caption_region_expand_when_empty", True))
    except Exception:
        return True


# Legacy fallback if settings are unavailable (prefer table_pipeline_fusion_trigger_score).
TIER2_QUALITY_THRESHOLD = 0.48
# Minimum vertical overlap (fraction of smaller height) to associate fusion extract with anchor bbox.
FUSION_BBOX_OVERLAP_MIN = 0.12

# Tabula/Camelot/pandas often emit these as non-empty strings; treat as empty.
_PLACEHOLDER_CELL_LOWER = frozenset(
    {"nan", "none", "null", "nat", "<na>", "#n/a", "n/a", "na"}
)

_camelot_module: Any = None
_camelot_import_error: Optional[str] = None


def _get_camelot_module() -> Any:
    """Import Camelot once; cache failure so we do not retry per page/table."""
    global _camelot_module, _camelot_import_error
    if _camelot_import_error is not None:
        return None
    if _camelot_module is not None:
        return _camelot_module
    try:
        import camelot

        _camelot_module = camelot
        return camelot
    except Exception as e:
        _camelot_import_error = str(e)
        logger.warning("Camelot import failed; lattice/stream fusion skipped: %s", e)
        return None


@dataclass
class _RawTable:
    page_start: int
    page_end: int
    bbox: Tuple[float, float, float, float]
    rows: List[List[str]]
    table_number: Optional[str]
    title: Optional[str]
    source_method: str
    continuation_caption: bool = False


@dataclass
class _CaptionAnchor:
    """A 'TABLE …' line from pdfplumber words (geometry), not clause extraction."""

    table_number: str
    title: Optional[str]
    continuation: bool
    line_bbox: Tuple[float, float, float, float]  # x0, top, x1, bottom

    @property
    def caption_bottom(self) -> float:
        return self.line_bbox[3]


@dataclass
class _QualityComponents:
    fill_ratio: float
    col_count: int
    row_count: int
    noise_ratio: float
    multiline_ratio: float
    diversity: float
    repeated_header_rows: int
    penalty: float
    score: float
    one_column_value_list: bool
    partial_fragment: bool
    placeholder_ratio: float
    garbage_cell_ratio: float
    symbol_junk_ratio: float
    ocr_mojibake_ratio: float
    header_corrupt_ratio: float
    data_row_repeat_ratio: float
    semantic_hard_fail: bool


def _fusion_should_run(q: _QualityComponents) -> bool:
    """When True, run Camelot/Tabula for this anchor (if fusion deps enabled)."""
    if q.semantic_hard_fail:
        return True
    try:
        from config import settings

        if bool(getattr(settings, "table_pipeline_always_try_fusion", False)):
            return True
        thr = float(getattr(settings, "table_pipeline_fusion_trigger_score", 0.82))
        return q.score < thr
    except Exception:
        return q.score < TIER2_QUALITY_THRESHOLD


def _normalize_numeric_table_id(digit_segment: str) -> str:
    """
    Normalize '3 , 1', '3. 1', '3,1', '104 , 101' into '3.1', '104.101'.
    """
    s = digit_segment.strip()
    parts = [p for p in re.split(r"\s*[.,]\s*", s) if p]
    if parts and all(p.isdigit() for p in parts):
        return ".".join(parts)
    return re.sub(r"\s+", "", s.replace(",", "."))


def _parse_table_number_from_text(
    text: str, *, anchor: str = "anywhere"
) -> Optional[Tuple[str, int, int]]:
    """
    Find first AS/NZS-style table caption (Table + id).

    Supports:
    - Appendix: Table B1, Table C12, Table D12(A), Table D12 ( a )
    - Numeric: Table 3.1, Table 3, 1, Table 3. 1, Table 104.101, Table 41
    - Alternative formats: TABLE 3.1, Table: 3.1, Table— 3.1, Table – 3.1

    P1: Enhanced appendix pattern handling with better spacing tolerance.
    Iteration 3: Added support for uppercase TABLE, punctuation (: — –), extra spacing.

    anchor:
    - "anywhere": first match in text (captions, running headers with text before "Table …").
    - "line_start": match only at the start of the line (after leading whitespace). Use this
      when scanning table cells so footnotes like "see Table 3.1" do not become table_number.

    Returns (canonical_id, match_start, match_end) for the 'Table … id' span, or None.
    """
    if not text or not text.strip():
        return None

    if anchor == "line_start":
        s = text.lstrip()
        if not s:
            return None
        offset = len(text) - len(s)

        # Iteration 3: Enhanced patterns to support TABLE (uppercase), punctuation (: — –)
        # Match: Table D12(A), TABLE D12(A), Table: D12 (A), Table— D 12 ( A )
        m = re.match(
            r"(?i)(TABLE?\s*[:—–]?\s*[A-Za-z]\s*\d+\s*\(\s*[A-Za-z0-9]+\s*\))",
            s,
        )
        if m:
            mc = re.match(
                r"(?i)TABLE?\s*[:—–]?\s*([A-Za-z])\s*(\d+)\s*\(\s*([A-Za-z0-9]+)\s*\)",
                m.group(1),
            )
            if mc:
                canon = f"{mc.group(1).upper()}{mc.group(2)}({mc.group(3).upper()})"
                g1s, g1e = m.span(1)
                return canon, offset + g1s, offset + g1e

        # Iteration 3: Appendix letter + digits with uppercase/punctuation support
        # Match: Table B1, TABLE C12, Table: B 1, Table— C12
        m = re.match(r"(?i)(TABLE?\s*[:—–]?\s*[A-Za-z]\s*\d+)\b", s)
        if m:
            mc = re.match(r"(?i)TABLE?\s*[:—–]?\s*([A-Za-z])\s*(\d+)", m.group(1))
            if mc:
                canon = f"{mc.group(1).upper()}{mc.group(2)}"
                g1s, g1e = m.span(1)
                return canon, offset + g1s, offset + g1e

        # Iteration 3: Numeric tables with uppercase/punctuation
        # Match: Table 3.1, TABLE 3.1, Table: 3.1, Table— 3, 1
        m = re.match(r"(?i)(TABLE?\s*[:—–]?\s*(\d+(?:\s*[.,]\s*\d+)+))\b", s)
        if m:
            canon = _normalize_numeric_table_id(m.group(2))
            g1s, g1e = m.span(1)
            return canon, offset + g1s, offset + g1e

        # Iteration 3: Plain integer with uppercase/punctuation
        # Match: Table 41, TABLE 41, Table: 41
        m = re.match(r"(?i)(TABLE?\s*[:—–]?\s*(\d+))\b", s)
        if m:
            g1s, g1e = m.span(1)
            return m.group(2), offset + g1s, offset + g1e

        return None

    # Iteration 3: Enhanced anywhere patterns with uppercase/punctuation support
    # Matches: Table D12(A), TABLE D 12 ( A ), Table: B1(a), Table— D12(A)
    m = re.search(
        r"(?i)\b(TABLE?\s*[:—–]?\s*[A-Za-z]\s*\d+\s*\(\s*[A-Za-z0-9]+\s*\))",
        text,
    )
    if m:
        mc = re.match(
            r"(?i)TABLE?\s*[:—–]?\s*([A-Za-z])\s*(\d+)\s*\(\s*([A-Za-z0-9]+)\s*\)",
            m.group(1),
        )
        if mc:
            canon = f"{mc.group(1).upper()}{mc.group(2)}({mc.group(3).upper()})"
            return canon, m.start(1), m.end(1)

    # Iteration 3: Appendix letter + digits with uppercase/punctuation
    # Matches: Table C1, TABLE B12, Table: C 1, Table— B12
    m = re.search(r"(?i)\b(TABLE?\s*[:—–]?\s*[A-Za-z]\s*\d+)\b", text)
    if m:
        mc = re.match(r"(?i)TABLE?\s*[:—–]?\s*([A-Za-z])\s*(\d+)", m.group(1))
        if mc:
            canon = f"{mc.group(1).upper()}{mc.group(2)}"
            return canon, m.start(1), m.end(1)

    # Iteration 3: Numeric with comma/dot/spacing and uppercase/punctuation
    # Matches: Table 3.1, TABLE 3.1, Table: 3, 1, Table— 3.1
    m = re.search(r"(?i)\b(TABLE?\s*[:—–]?\s*(\d+(?:\s*[.,]\s*\d+)+))\b", text)
    if m:
        canon = _normalize_numeric_table_id(m.group(2))
        return canon, m.start(1), m.end(1)

    # Iteration 3: Plain integer with uppercase/punctuation
    # Matches: Table 41, TABLE 41, Table: 41, Table— 41
    m = re.search(r"(?i)\b(TABLE?\s*[:—–]?\s*(\d+))\b", text)
    if m:
        return m.group(2), m.start(1), m.end(1)

    return None


class TablePipeline:
    """End-to-end table workflow for tables.json generation."""
    CONTINUED_PATTERN = re.compile(r"\bcontinued\b", re.IGNORECASE)
    NOISY_TITLE_PATTERN = re.compile(r"^[\s\.,;:()\-]+$")
    NOISE_TOKEN_PATTERN = re.compile(r"(\?\!|~|[•■□◦·]|[^\w\s\-\.,:/()%])")
    UNIT_TOKEN_PATTERN = re.compile(
        r"^(mm2?|mm²|%|a|v|w|kw|c|degc|hz|ohm|kva|mv|na|°c|°f)$", re.IGNORECASE
    )
    NUMERIC_UNIT_PATTERN = re.compile(
        r"^[\d.,]+\s*(mm|m|cm|%|°c|°f|a|v|w|kw|hz|va|kva)?$", re.IGNORECASE
    )
    CLAUSE_LEAD_PATTERN = re.compile(r"^\d+(?:\.\d+){1,5}\s+")
    TITLE_PROSE_CUT_PATTERN = re.compile(
        r"\b(shall|must not|must|in accordance with|the following|provided that)\b",
        re.IGNORECASE,
    )
    OCR_GARBAGE_ROW_PATTERN = re.compile(r"^[\W_]{3,}$")
    SINGLE_OCR_ARTIFACT_PATTERN = re.compile(r"^[^\w]{1,6}$")
    # Digit runs glued to stray letters (Tabula/OCR): "2120t", "2 120t", "sizet"
    OCR_DIGIT_MOJIBAKE_PATTERN = re.compile(
        r"(?:\d{3,}[a-z](?![a-z]{2})|\b\d{1,2}\s+\d{2,}t\b|sizet\b|conductort\b|of\s+active\s+sizet)",
        re.IGNORECASE,
    )
    # Appendix schematic / switch-diagram tables mis-read as grids (e.g. "S 32 S 28", "Cl)", "1/)").
    _SCHEMATIC_S_REF_PATTERN = re.compile(r"\bs\s+\d{1,4}\b", re.IGNORECASE)
    _SCHEMATIC_WEIRD_SYM_PATTERN = re.compile(
        r"cl\)|lt\)|\b1/\)|\bcr\)\b|\.x\.\.|i\.\.n\.\.|i\.\.\.n\.\.\.|\bin\s+n\s+x\b",
        re.IGNORECASE,
    )
    _SCHEMATIC_DOLLAR_NUM_PATTERN = re.compile(r"\$\s*\d+")

    def __init__(self) -> None:
        self._diag: Dict[str, int] = {}
        self._fusion_by_page: Dict[int, List[_RawTable]] = {}
        
        # Initialize AI service if available
        self._ai_service = None
        if _ai_service_available:
            try:
                self._ai_service = get_ai_service()
                logger.info("AI table service initialized (discovery=%s, caption=%s, validation=%s)",
                           self._ai_service.discovery_enabled,
                           self._ai_service.caption_enabled,
                           self._ai_service.validation_enabled)
            except Exception as e:
                logger.warning("Failed to initialize AI service: %s", e)

    def _normalize_scalar_to_str(self, value: Any) -> str:
        if value is None:
            return ""
        try:
            import pandas as pd

            if pd.isna(value):
                return ""
        except Exception:
            pass
        if isinstance(value, float) and value != value:
            return ""
        try:
            if hasattr(value, "item"):
                inner = value.item()
                if isinstance(inner, float) and inner != inner:
                    return ""
                value = inner
        except Exception:
            pass
        s = str(value).strip()
        if not s:
            return ""
        low = s.lower()
        if low in _PLACEHOLDER_CELL_LOWER:
            return ""
        return s

    def _is_placeholder_text(self, text: str) -> bool:
        low = (text or "").strip().lower()
        return not low or low in _PLACEHOLDER_CELL_LOWER

    def _cell_is_garbage(self, cell: str) -> bool:
        t = (cell or "").strip()
        if not t or self._is_placeholder_text(t):
            return False
        if len(t) < 2:
            return False
        if len(t) == 2 and t.isalpha() and t.isupper():
            return False
        digits = sum(1 for c in t if c.isdigit())
        alnum = sum(1 for c in t if c.isalnum())
        if digits >= len(t) * 0.55:
            return False
        return (alnum / len(t)) < 0.2

    def _cell_symbol_junk(self, cell: str) -> bool:
        """True when punctuation/symbols dominate (OCR junk, broken tokens)."""
        t = (cell or "").strip()
        if not t or self._is_placeholder_text(t):
            return False
        if len(t) <= 12 and self._cell_is_garbage(t):
            return True
        alnum = sum(1 for c in t if c.isalnum())
        space = sum(1 for c in t if c.isspace())
        ratio = alnum / len(t)
        if len(t) >= 3 and ratio < 0.22:
            return True
        punct = len(t) - alnum - space
        if len(t) >= 4 and punct / len(t) > 0.45:
            return True
        return False

    def _cell_ocr_digit_mojibake(self, cell: str) -> bool:
        t = (cell or "").strip()
        if len(t) < 4 or self._is_placeholder_text(t):
            return False
        return bool(self.OCR_DIGIT_MOJIBAKE_PATTERN.search(t))

    def _fusion_output_acceptable(
        self, table: Table, q: _QualityComponents, relax_for_hard_baseline: bool = False
    ) -> bool:
        if q.semantic_hard_fail:
            return False
        if relax_for_hard_baseline:
            # Iteration 3: Relaxed thresholds for hard baseline recovery
            if q.placeholder_ratio > 0.28:  # Was 0.24
                return False
            if q.garbage_cell_ratio > 0.25:  # Was 0.22
                return False
            if q.symbol_junk_ratio > 0.25:  # Was 0.22
                return False
            if q.ocr_mojibake_ratio > 0.10:  # Was 0.08
                return False
            if q.header_corrupt_ratio > 0.50:  # Was 0.45
                return False
            if q.col_count >= 2 and q.fill_ratio >= 0.24:  # Was 0.28
                return True
            return q.score > -0.40  # Was -0.35
        # Iteration 3: Relaxed standard thresholds
        if q.placeholder_ratio > 0.22:  # Was 0.18
            return False
        if q.garbage_cell_ratio > 0.17:  # Was 0.14
            return False
        if q.symbol_junk_ratio > 0.17:  # Was 0.14
            return False
        if q.ocr_mojibake_ratio > 0.055:  # Was 0.045
            return False
        if q.header_corrupt_ratio > 0.32:  # Was 0.28
            return False
        if q.col_count >= 5 and q.fill_ratio < 0.15:  # Was 0.18
            return False
        if q.fill_ratio < 0.10 and q.col_count >= 3:  # Was 0.12
            return False
        return True

    def _fusion_beats_baseline(
        self, frt: _RawTable, cq: _QualityComponents, bq: _QualityComponents
    ) -> bool:
        """Tabula/Camelot must improve semantics, not only structural fill."""
        if cq.semantic_hard_fail:
            return False
        if bq.semantic_hard_fail:
            if cq.score >= -0.02:
                return True
            return cq.score > bq.score + 0.06
        method = frt.source_method or ""
        if method == "tabula":
            margin = 0.09
            if cq.score < bq.score + margin:
                return False
            if cq.garbage_cell_ratio > bq.garbage_cell_ratio + 0.012:
                return False
            if cq.placeholder_ratio > bq.placeholder_ratio + 0.02:
                return False
            if cq.symbol_junk_ratio > bq.symbol_junk_ratio + 0.035:
                return False
            if cq.header_corrupt_ratio > bq.header_corrupt_ratio + 0.05:
                return False
            if cq.data_row_repeat_ratio > bq.data_row_repeat_ratio + 0.08 and cq.col_count <= 3:
                return False
            if cq.ocr_mojibake_ratio > bq.ocr_mojibake_ratio + 0.012:
                return False
            return True
        if method.startswith("camelot"):
            margin = 0.05
            if cq.score < bq.score + margin:
                return False
            if cq.garbage_cell_ratio > bq.garbage_cell_ratio + 0.03:
                return False
            if cq.symbol_junk_ratio > bq.symbol_junk_ratio + 0.05:
                return False
            return True
        return cq.score > bq.score + 0.02

    def _table_blob_for_heuristics(self, table: Table, max_data_rows: int = 3) -> str:
        parts: List[str] = []
        for hr in table.header_rows or []:
            parts.extend(hr.cells or [])
        for dr in (table.data_rows or [])[:max_data_rows]:
            parts.extend(dr.cells or [])
        return " ".join((c or "") for c in parts)

    def _looks_like_schematic_or_diagram_table(self, table: Table) -> bool:
        blob = self._table_blob_for_heuristics(table)
        if len(blob) < 100:
            return False
        bl = blob.lower()
        s_refs = len(self._SCHEMATIC_S_REF_PATTERN.findall(bl))
        weird = len(self._SCHEMATIC_WEIRD_SYM_PATTERN.findall(bl))
        dollars = len(self._SCHEMATIC_DOLLAR_NUM_PATTERN.findall(blob))
        if weird >= 14:
            return True
        if s_refs >= 30 and weird >= 7:
            return True
        if s_refs >= 34 and dollars >= 10:
            return True
        return False

    def _clause_likeness_score(self, table: Table) -> float:
        """
        Calculate how clause-like (prose-like) a table is.
        Returns 0.0 (definitely table) to 1.0 (definitely clause/prose).
        
        P0 implementation: Detect prose/clause fragments that shouldn't be in tables.json.
        Iteration 1: Enhanced detection for 2-column change lists and TOC entries.
        """
        headers = table.header_rows or []
        data = table.data_rows or []
        
        if not headers and not data:
            return 0.0
        
        col_count = len(headers[0].cells) if headers else (len(data[0].cells) if data else 0)
        
        # Strong indicator: single column
        if col_count <= 1:
            clause_score = 0.5
        elif col_count == 2:
            # 2-column content gets moderate starting score (may be change list)
            clause_score = 0.2
        else:
            clause_score = 0.0
        
        # Collect all text for analysis
        all_text = []
        first_cell_text = ""
        
        if headers:
            for hr in headers:
                for idx, cell in enumerate(hr.cells):
                    text = (cell or "").strip()
                    if text:
                        all_text.append(text)
                        if idx == 0 and not first_cell_text:
                            first_cell_text = text
        
        if data:
            for idx, dr in enumerate(data):
                for cell_idx, cell in enumerate(dr.cells):
                    text = (cell or "").strip()
                    if text:
                        all_text.append(text)
                        if idx == 0 and cell_idx == 0 and not first_cell_text:
                            first_cell_text = text
        
        if not all_text:
            return 0.0
        
        full_text = " ".join(all_text)
        
        # Check for very long first cell (typical in clause fragments)
        if first_cell_text and len(first_cell_text) > 80:
            clause_score += 0.25
        
        # Check for clause numbering patterns (1.2.3, 3.8.1, etc.)
        clause_number_pattern = re.compile(r'\b\d+(?:\.\d+){1,5}\b')
        clause_numbers = clause_number_pattern.findall(full_text)
        if len(clause_numbers) >= 2:
            clause_score += 0.2
        
        # Check for normative language (shall, must, may, etc.)
        normative_words = re.compile(
            r'\b(shall|must not|must|should|may|in accordance with|'
            r'provided that|unless|where|however|the following|'
            r'requirements?|specification|compliance)\b',
            re.IGNORECASE
        )
        normative_matches = normative_words.findall(full_text)
        if len(normative_matches) >= 3:
            clause_score += 0.3
        elif len(normative_matches) >= 1:
            clause_score += 0.15
        
        # Check for list markers (a), (b), (i), (ii)
        list_marker_pattern = re.compile(r'\([a-z]\)|\([ivxIVX]+\)')
        list_markers = list_marker_pattern.findall(full_text)
        if len(list_markers) >= 2:
            clause_score += 0.2
        
        # Check for prose flow indicators (long sentences, connective words)
        sentences = re.split(r'[.;]', full_text)
        long_sentences = sum(1 for s in sentences if len(s.strip()) > 100)
        if long_sentences >= 2:
            clause_score += 0.2
        
        # Check average cell length (tables have shorter cells)
        avg_cell_length = sum(len(t) for t in all_text) / len(all_text)
        if avg_cell_length > 60:
            clause_score += 0.15
        
        # Check for standard section headers that appear in clause text
        section_pattern = re.compile(
            r'\b(section|clause|appendix|note|exception|general|scope|'
            r'definitions?|references?|changes to|amendments?|revisions?)\b',
            re.IGNORECASE
        )
        section_matches = section_pattern.findall(full_text)
        if len(section_matches) >= 2:
            clause_score += 0.15
        
        # Iteration 1: Detect change/amendment list patterns
        change_pattern = re.compile(
            r'\b(changes? to|amendments? to|revisions? to|modifications? to|'
            r'updates? to|alterations?|replaced with|clarified|expanded|added|revised|removed)\b',
            re.IGNORECASE
        )
        change_matches = change_pattern.findall(full_text)
        if len(change_matches) >= 3:
            clause_score += 0.3
        
        # Iteration 1: Detect table of contents patterns
        toc_pattern = re.compile(r'\b\d+\.\d+.*?\.\.+\s*\d+$', re.MULTILINE)
        toc_matches = toc_pattern.findall(full_text)
        if len(toc_matches) >= 2:
            clause_score += 0.4  # Strong indicator of TOC
        
        # Check for lack of tabular structure indicators
        # Real tables often have: units, numeric data, short labels
        numeric_cells = sum(1 for t in all_text if re.search(r'\d', t))
        if numeric_cells < len(all_text) * 0.2:  # Less than 20% cells have numbers
            clause_score += 0.1
        
        # Check column balance (clauses often have unbalanced columns)
        if col_count > 1 and data:
            first_col_lens = []
            other_col_lens = []
            first_col_empty = 0
            for dr in data:
                if dr.cells:
                    first_text = (dr.cells[0] or "").strip()
                    first_col_lens.append(len(first_text))
                    if not first_text or len(first_text) < 3:
                        first_col_empty += 1
                    for cell in dr.cells[1:]:
                        other_col_lens.append(len((cell or "").strip()))
            
            # Iteration 1: Many empty/short first column cells suggests ragged list
            if len(first_col_lens) > 0 and first_col_empty / len(first_col_lens) > 0.3:
                clause_score += 0.2
            
            if first_col_lens and other_col_lens:
                avg_first = sum(first_col_lens) / len(first_col_lens)
                avg_other = sum(other_col_lens) / len(other_col_lens) if other_col_lens else 0
                if avg_first > avg_other * 3:  # First column much longer
                    clause_score += 0.15
                # Iteration 1: Check if 2nd column is consistently prose-length
                if col_count == 2 and avg_other > 50:  # Long prose in 2nd column
                    clause_score += 0.2
        
        return min(1.0, clause_score)

    def _is_clause_shaped_content(self, table: Table) -> bool:
        """
        P0: Determine if a table is actually clause/prose content.
        Returns True if content should be rejected as not-a-table.
        """
        clause_score = self._clause_likeness_score(table)
        
        # Get quality metrics
        m = table.quality_metrics or {}
        col_count = int(m.get("col_count", 0))
        
        # Iteration 2: Relaxed threshold from 0.55 to 0.60 to improve recall (capture more valid tables)
        if clause_score >= 0.60:
            logger.debug(
                f"Table {table.table_id} rejected as clause-shaped content "
                f"(clause_score={clause_score:.2f}, cols={col_count})"
            )
            return True
        
        # For single-column content, be more aggressive
        if col_count == 1 and clause_score >= 0.5:
            logger.debug(
                f"Single-column table {table.table_id} rejected as clause-shaped "
                f"(clause_score={clause_score:.2f})"
            )
            return True
        
        # Iteration 1: For 2-column content with high score, also reject
        if col_count == 2 and clause_score >= 0.5:
            logger.debug(
                f"2-column table {table.table_id} rejected as clause-shaped list "
                f"(clause_score={clause_score:.2f})"
            )
            return True
        
        return False

    def _compute_tabular_score(self, rows: List[List[str]]) -> float:
        """
        P0: Score how tabular (structured/grid-like) content is.
        Returns 0.0 (not tabular) to 1.0 (very tabular).
        
        Used for sweep gating to filter ragged text blocks.
        """
        if not rows or len(rows) < 2:
            return 0.0
        
        col_count = max(len(r) for r in rows)
        if col_count <= 1:
            return 0.0
        
        score = 0.0
        
        # Column consistency: do rows have similar column counts?
        col_counts = [len(r) for r in rows]
        consistent_col_count = sum(1 for c in col_counts if c == col_count)
        col_consistency = consistent_col_count / len(rows)
        score += col_consistency * 0.3
        
        # Cell length uniformity: tabular data has more uniform cell lengths
        all_cells = [cell for row in rows for cell in row]
        cell_lens = [len((c or "").strip()) for c in all_cells if (c or "").strip()]
        if cell_lens:
            avg_len = sum(cell_lens) / len(cell_lens)
            # Prefer shorter, uniform cells
            if avg_len < 40:
                score += 0.2
            # Check variance
            variance = sum((l - avg_len) ** 2 for l in cell_lens) / len(cell_lens)
            std_dev = variance ** 0.5
            if std_dev < avg_len * 0.8:  # Low variance relative to mean
                score += 0.15
        
        # Numeric/symbolic content: tables often have numbers, units, symbols
        numeric_pattern = re.compile(r'\d')
        symbol_pattern = re.compile(r'[%°×±≤≥]')
        cells_with_numbers = sum(1 for c in all_cells if numeric_pattern.search(c or ""))
        cells_with_symbols = sum(1 for c in all_cells if symbol_pattern.search(c or ""))
        
        if all_cells:
            numeric_ratio = cells_with_numbers / len(all_cells)
            symbol_ratio = cells_with_symbols / len(all_cells)
            score += min(0.25, numeric_ratio * 0.5 + symbol_ratio * 0.5)
        
        # Alignment indicators: delimiters, colons, dashes
        delimiter_pattern = re.compile(r'[:|—–-]')
        cells_with_delimiters = sum(1 for c in all_cells if delimiter_pattern.search(c or ""))
        if all_cells:
            delimiter_ratio = cells_with_delimiters / len(all_cells)
            score += min(0.1, delimiter_ratio * 0.3)
        
        return min(1.0, score)

    def _sweep_result_acceptable(self, rt: _RawTable, page_words: List[dict]) -> bool:
        """
        P0: Gate sweep results before adding them to output.
        Requires minimum column count (>=2) OR explicit caption anchor OR high tabular score.
        
        This prevents ragged text blocks (clause text) from being added as single-column tables.
        """
        if not rt.rows:
            return False
        
        col_count = max(len(r) for r in rt.rows) if rt.rows else 0
        
        # Multi-column content is generally acceptable
        if col_count >= 2:
            return True
        
        # Single-column requires either:
        # 1. Explicit caption anchor (table_number present)
        if rt.table_number:
            return True
        
        # 2. High tabular score (structured/grid-like despite single column)
        tabular_score = self._compute_tabular_score(rt.rows)
        if tabular_score >= 0.5:
            logger.debug(
                f"Sweep single-column accepted: tabular_score={tabular_score:.2f}"
            )
            return True
        
        # Otherwise reject
        logger.debug(
            f"Sweep result rejected: cols={col_count}, "
            f"table_number={rt.table_number}, tabular_score={tabular_score:.2f}"
        )
        return False

    def _should_drop_defective_table(self, table: Table) -> bool:
        """Always remove structurally useless outputs (not gated by omit_unnumbered_table_fragments)."""
        data = table.data_rows or []
        headers = table.header_rows or []
        if not data:
            return True
        if self._looks_like_schematic_or_diagram_table(table):
            return True
        # P0: Reject clause-shaped content
        if self._is_clause_shaped_content(table):
            return True
        m = table.quality_metrics or {}
        dr = int(m.get("data_row_count", len(data)))
        cols = int(m.get("col_count", 0))
        if not cols and headers:
            cols = len(headers[0].cells)
        sc = float(m.get("unified_score", 0.0))
        nr = float(m.get("noise_ratio", 0.0))
        hard = bool(m.get("semantic_hard_fail"))
        if table.table_number and dr == 1:
            if hard:
                return True
            if sc < -0.45:
                return True
            if cols <= 1 and sc < 0.12 and nr > 0.42:
                return True
            if cols >= 2 and sc < -0.12 and (hard or nr > 0.28):
                return True
        return False

    def _should_omit_emitted_table(self, table: Table) -> bool:
        if not _omit_fragments_enabled():
            return False
        if table.table_number:
            return False
        m = table.quality_metrics or {}
        sc = float(m.get("unified_score", 1.0))
        cols = int(m.get("col_count", 0))
        dr = int(m.get("data_row_count", 0))
        nr = float(m.get("noise_ratio", 0))
        sj = float(m.get("symbol_junk_ratio", 0))
        ocr_m = float(m.get("ocr_mojibake_ratio", 0))
        notes = table.extraction_notes or []
        tabula_fusion = any("fusion_win:tabula" in (n or "") for n in notes)

        # Iteration 3: Relaxed thresholds for unnumbered fragments
        if m.get("semantic_hard_fail") and sc < 0.32:  # Was 0.38
            return True
        if sc < 0.08:  # Was 0.1
            return True
        if sc < 0.22 and cols <= 3:  # Was 0.26
            return True
        if sc < 0.18 and cols <= 4 and float(m.get("garbage_cell_ratio", 0)) > 0.09:  # Was 0.22
            return True
        # Tiny noisy header + almost no body (e.g. page-160 style)
        if cols <= 2 and dr <= 1 and nr > 0.48:  # Was 0.42
            return True
        if cols <= 2 and dr <= 2 and sc < 0.42 and nr > 0.38:  # Was 0.48 and 0.35
            return True
        # Narrow but long grids are often real (lookup / numeric tables); only omit extreme junk.
        if tabula_fusion and cols <= 2 and dr >= 28 and sc < 0.24:  # Was 0.28
            return True
        if cols <= 2 and dr >= 24 and sc < 0.52:  # Was 0.58
            return True
        if cols <= 2 and sj > 0.022 and sc < 0.78:  # Was 0.018 and 0.82
            return True
        if ocr_m > 0.05:  # Was 0.04
            return True
        if cols <= 3 and dr <= 2 and sc < 0.45 and nr > 0.42:  # Was 0.5 and 0.38
            return True
        # Unnumbered 1-row / near-empty grids: almost always PDF noise or mis-split fragments
        if not table.table_number and dr == 0:
            return True
        if not table.table_number and dr == 1 and cols <= 8:
            if sc < 0.68 or nr > 0.18 or cols <= 6 or ocr_m > 0.022:  # Was 0.74, 0.15, and 0.018
                return True
        return False

    def process(self, source_pdf_path: str, clauses: Optional[List[Any]] = None) -> List[Table]:
        self._fusion_by_page = {}
        # P4: Enhanced diagnostic tracking
        self._diag = {
            "header_rows_detected": 0,
            "duplicate_headers_removed": 0,
            "confidence_penalties_applied": 0,
            "image_recovery_attempted": 0,
            "image_recovery_applied": 0,
            "fusion_attempted": 0,
            "fusion_applied": 0,
            "same_page_merges": 0,
            "noise_rows_dropped": 0,
            "dedup_collapsed": 0,
            "tables_omitted": 0,
            "defective_table_drops": 0,
            "pdfplumber_loose_pass_pages": 0,
            "page_sweep_raw_added": 0,
            "caption_anchor_labeled": 0,
            "caption_anchor_grids_added": 0,
            "continuation_body_merges": 0,
            "caption_multi_engine_picks": 0,
            "caption_multi_engine_expand_retries": 0,
            # P4: New upgrade diagnostics
            "clause_shaped_rejected": 0,
            "sweep_gated_rejected": 0,
            "schematic_rejected": 0,
        }
        clauses = clauses or []
        raw_tables = self._extract_raw_tables_pdfplumber(source_pdf_path)
        raw_tables = [self._filter_noise_rows_raw(rt) for rt in raw_tables]
        raw_tables = self._merge_same_page_fragments(raw_tables)
        merged = self._merge_continuations(raw_tables)

        tables: List[Table] = []
        for rt in merged:
            table, best_raw, notes = self._extract_best_tiered(source_pdf_path, rt, clauses)
            table = self._attach_metadata(table, best_raw, notes)
            if self._should_drop_defective_table(table):
                self._diag["defective_table_drops"] += 1
                self._diag["tables_omitted"] += 1
                # P4: Track specific rejection reasons
                if self._is_clause_shaped_content(table):
                    self._diag["clause_shaped_rejected"] += 1
                    if not table.extraction_notes:
                        table.extraction_notes = []
                    clause_score = self._clause_likeness_score(table)
                    table.extraction_notes.append(
                        f"rejected:clause_shaped(score={clause_score:.2f})"
                    )
                elif self._looks_like_schematic_or_diagram_table(table):
                    self._diag["schematic_rejected"] += 1
                continue
            if self._should_omit_emitted_table(table):
                self._diag["tables_omitted"] += 1
                continue
            tables.append(table)

        tables = self._dedupe_by_table_key(tables)

        # P4: Enhanced diagnostic logging
        logger.info(
            f"Table pipeline complete: {len(tables)} tables extracted. "
            f"Upgrade metrics: clause_shaped_rejected={self._diag.get('clause_shaped_rejected', 0)}, "
            f"sweep_gated_rejected={self._diag.get('sweep_gated_rejected', 0)}, "
            f"schematic_rejected={self._diag.get('schematic_rejected', 0)}"
        )
        logger.info(
            "TablePipeline diagnostics: header_rows_detected=%s duplicate_headers_removed=%s "
            "confidence_penalties_applied=%s image_recovery_attempted=%s image_recovery_applied=%s "
            "fusion_attempted=%s fusion_applied=%s same_page_merges=%s noise_rows_dropped=%s dedup_collapsed=%s "
            "tables_omitted=%s defective_table_drops=%s pdfplumber_loose_pass_pages=%s "
            "page_sweep_raw_added=%s caption_anchor_labeled=%s caption_anchor_grids_added=%s "
            "continuation_body_merges=%s caption_multi_engine_picks=%s "
            "caption_multi_engine_expand_retries=%s",
            self._diag["header_rows_detected"],
            self._diag["duplicate_headers_removed"],
            self._diag["confidence_penalties_applied"],
            self._diag["image_recovery_attempted"],
            self._diag["image_recovery_applied"],
            self._diag["fusion_attempted"],
            self._diag["fusion_applied"],
            self._diag["same_page_merges"],
            self._diag["noise_rows_dropped"],
            self._diag["dedup_collapsed"],
            self._diag["tables_omitted"],
            self._diag["defective_table_drops"],
            self._diag["pdfplumber_loose_pass_pages"],
            self._diag["page_sweep_raw_added"],
            self._diag["caption_anchor_labeled"],
            self._diag["caption_anchor_grids_added"],
            self._diag["continuation_body_merges"],
            self._diag["caption_multi_engine_picks"],
            self._diag["caption_multi_engine_expand_retries"],
        )
        
        # AI metrics reporting (if AI service is available)
        if self._ai_service:
            ai_metrics = self._ai_service.get_metrics()
            total_calls = (
                ai_metrics.get("ai_discovery_calls", 0) +
                ai_metrics.get("ai_caption_calls", 0) +
                ai_metrics.get("ai_validation_calls", 0)
            )
            logger.info(
                "AI Enhancement metrics: discovery_tables=%s total_calls=%s (discovery=%s, caption=%s, validation=%s) "
                "total_tokens=%s estimated_cost=$%.4f",
                self._diag.get("ai_discovery_tables", 0),
                total_calls,
                ai_metrics.get("ai_discovery_calls", 0),
                ai_metrics.get("ai_caption_calls", 0),
                ai_metrics.get("ai_validation_calls", 0),
                ai_metrics.get("ai_total_tokens", 0),
                ai_metrics.get("ai_total_cost_usd", 0.0)
            )
        
        return tables

    def _extract_best_tiered(
        self, source_pdf_path: str, anchor: _RawTable, clauses: List[Any]
    ) -> Tuple[Table, _RawTable, List[str]]:
        notes: List[str] = []
        best_rt = anchor
        best_table = self._to_table_model(anchor, clauses)
        best_q = self._quality_components(best_table)
        pdfplumber_q = best_q

        if _fusion_enabled() and _fusion_should_run(best_q):
            self._diag["fusion_attempted"] += 1
            fusion_rts = self._fusion_raw_tables(source_pdf_path, anchor)
            fusion_candidates: List[Tuple[_RawTable, Table, _QualityComponents]] = []
            for frt in fusion_rts:
                cand = self._to_table_model(frt, clauses)
                cq = self._quality_components(cand)
                if not self._fusion_output_acceptable(
                    cand, cq, relax_for_hard_baseline=pdfplumber_q.semantic_hard_fail
                ):
                    continue
                if not self._fusion_beats_baseline(frt, cq, pdfplumber_q):
                    continue
                fusion_candidates.append((frt, cand, cq))
            if fusion_candidates:
                frt, cand, cq = max(fusion_candidates, key=lambda x: x[2].score)
                best_rt, best_table, best_q = frt, cand, cq
                self._diag["fusion_applied"] += 1
                notes.append(f"fusion_win:{frt.source_method}")

        if self._should_trigger_image_recovery(best_rt, best_table, best_q):
            self._diag["image_recovery_attempted"] += 1
            recovered = self._recover_table_from_image(source_pdf_path, best_rt)
            if recovered:
                recovered = self._filter_noise_rows_raw(recovered)
                if len(recovered.rows) >= 2 and not self._raw_matrix_mostly_noise(recovered.rows):
                    rec_table = self._to_table_model(recovered, clauses)
                    rq = self._quality_components(rec_table)
                    if self._ocr_candidate_acceptable(rec_table, rq) and self._is_structurally_better(
                        rec_table, rq, best_table, best_q
                    ):
                        best_table = rec_table
                        best_rt = recovered
                        notes.append("image_ocr_applied")
                        self._diag["image_recovery_applied"] += 1
                else:
                    notes.append("image_ocr_rejected_noise")

        # AI-powered structure validation (if enabled)
        if self._ai_service and self._ai_service.validation_enabled:
            # Only validate borderline tables (low-medium confidence)
            if best_q.score < 0.6 or best_q.semantic_hard_fail:
                try:
                    # Convert page to image and crop to table region
                    import pdfplumber
                    with pdfplumber.open(source_pdf_path) as pdf:
                        page = pdf.pages[best_rt.page_start - 1]
                        page_image = page.to_image(resolution=150).original
                    
                    # Crop to table region
                    x0, y0, x1, y1 = best_rt.bbox
                    scale = 150 / 72  # Resolution scale factor
                    crop_box = (
                        int(x0 * scale),
                        int(y0 * scale),
                        int(x1 * scale),
                        int(y1 * scale)
                    )
                    page_crop_image = page_image.crop(crop_box)
                    
                    # Convert best_table to table_json format
                    table_json = best_table.model_dump()
                    
                    # Build quality issues list
                    quality_issues = []
                    if best_q.semantic_hard_fail:
                        quality_issues.append("semantic_hard_fail")
                    if best_q.noise_ratio > 0.3:
                        quality_issues.append(f"high_noise_ratio:{best_q.noise_ratio:.2f}")
                    if best_q.fill_ratio < 0.4:
                        quality_issues.append(f"low_fill_ratio:{best_q.fill_ratio:.2f}")
                    if best_q.garbage_cell_ratio > 0.2:
                        quality_issues.append(f"garbage_cells:{best_q.garbage_cell_ratio:.2f}")
                    if not quality_issues:
                        quality_issues.append("borderline_quality_score")
                    
                    # Call AI validation with correct parameters
                    validation_result = self._ai_service.validate_structure(
                        table_json=table_json,
                        page_crop_image=page_crop_image,
                        quality_score=best_q.score,
                        quality_issues=quality_issues
                    )
                    
                    if validation_result and not validation_result.is_table:
                        # AI rejected this table - mark for omission
                        notes.append(f"ai_validation_rejected:{validation_result.reasoning}")
                        best_q = best_q._replace(semantic_hard_fail=True)
                        logger.info("AI validation rejected table on page %s: %s", best_rt.page_start, validation_result.reasoning)
                    elif validation_result and validation_result.is_table:
                        # AI validated the table
                        notes.append("ai_validation_passed")
                        if not validation_result.structure_correct:
                            notes.append(f"ai_suggested_corrections:{len(validation_result.suggested_corrections)}")
                        logger.debug("AI validation passed for table on page %s", best_rt.page_start)
                except Exception as e:
                    logger.warning("AI validation failed on page %s: %s", best_rt.page_start, e)

        return best_table, best_rt, notes

    def _attach_metadata(self, table: Table, raw: _RawTable, notes: List[str]) -> Table:
        q = self._quality_components(table)
        if q.penalty > 0.02:
            self._diag["confidence_penalties_applied"] += 1
        metrics = {
            "fill_ratio": round(q.fill_ratio, 4),
            "col_count": q.col_count,
            "data_row_count": q.row_count,
            "noise_ratio": round(q.noise_ratio, 4),
            "multiline_ratio": round(q.multiline_ratio, 4),
            "diversity": round(q.diversity, 4),
            "placeholder_ratio": round(q.placeholder_ratio, 4),
            "garbage_cell_ratio": round(q.garbage_cell_ratio, 4),
            "symbol_junk_ratio": round(q.symbol_junk_ratio, 4),
            "ocr_mojibake_ratio": round(q.ocr_mojibake_ratio, 4),
            "header_corrupt_ratio": round(q.header_corrupt_ratio, 4),
            "data_row_repeat_ratio": round(q.data_row_repeat_ratio, 4),
            "semantic_hard_fail": q.semantic_hard_fail,
            "unified_score": round(q.score, 4),
            "penalty": round(q.penalty, 4),
            "one_column_value_list": q.one_column_value_list,
            "partial_fragment": q.partial_fragment,
        }
        tkey = self._compute_table_key(table)
        conf = self._confidence_from_components(q, table)
        return table.model_copy(
            update={
                "source_method": raw.source_method,
                "extraction_notes": notes,
                "table_key": tkey,
                "continuation_of": None,
                "quality_metrics": metrics,
                "confidence": conf,
            }
        )

    def _compute_table_key(self, table: Table) -> str:
        parts = [
            (table.table_number or "na").strip().lower(),
        ]
        # Unnumbered tables on different pages were over-collapsing; keep page in the key.
        if not table.table_number:
            parts.append(f"p{table.page_start}")
        parts.append(
            "|".join(c.strip().lower() for c in (table.header_rows[0].cells if table.header_rows else [])),
        )
        if table.data_rows:
            fr = "|".join(c.strip().lower() for c in table.data_rows[0].cells[:8])
            parts.append(fr[:200])
        h = hashlib.sha256("::".join(parts).encode("utf-8", errors="ignore")).hexdigest()[:16]
        return f"{table.table_number or 'na'}:{h}"

    def _dedupe_by_table_key(self, tables: List[Table]) -> List[Table]:
        by_key: Dict[str, Table] = {}
        for t in tables:
            k = t.table_key or t.table_id
            existing = by_key.get(k)
            if not existing:
                by_key[k] = t
                continue
            s_new = (t.quality_metrics or {}).get("unified_score", 0.0)
            s_old = (existing.quality_metrics or {}).get("unified_score", 0.0)
            self._diag["dedup_collapsed"] += 1
            if s_new > s_old + 0.01:
                by_key[k] = t
        return list(by_key.values())

    # --- caption anchor: TABLE line from words + grid in band below (pipeline-only) ---

    def _discover_caption_anchors_from_page_words(
        self, page_words: List[dict], page_width: float, page_height: float
    ) -> List[_CaptionAnchor]:
        if not page_words:
            return []
        lines = self._cluster_words_into_lines(page_words, y_tol=3.6)
        out: List[_CaptionAnchor] = []
        for ln in lines:
            if not ln:
                continue
            x0 = min(float(w.get("x0", 0.0)) for w in ln)
            x1 = max(float(w.get("x1", 0.0)) for w in ln)
            top = min(float(w.get("top", 0.0)) for w in ln)
            bottom = max(float(w.get("bottom", 0.0)) for w in ln)
            if x1 <= x0 or bottom <= top:
                continue
            text = " ".join(
                (w.get("text") or "").strip()
                for w in sorted(ln, key=lambda w: float(w.get("x0", 0.0)))
            )
            text = re.sub(r"\s+", " ", text).strip()
            if not text:
                continue
            parsed = _parse_table_number_from_text(text, anchor="line_start")
            if not parsed:
                continue
            raw_num, _span_s, span_e = parsed
            continuation_line = bool(self.CONTINUED_PATTERN.search(text))
            title_part = text[span_e:].strip()
            title = self._sanitize_table_title(title_part)
            out.append(
                _CaptionAnchor(
                    table_number=raw_num,
                    title=title,
                    continuation=continuation_line,
                    line_bbox=(x0, top, x1, bottom),
                )
            )
        out.sort(key=lambda a: a.line_bbox[1])
        
        # AI-powered caption detection (DISABLED - calls every page, not cost-effective)
        # Only AI Discovery is enabled which uses weak table detection to filter pages
        # if self._ai_service and self._ai_service.caption_enabled:
        #     ... (code removed to prevent calling AI on every page)
        
        out.sort(key=lambda a: a.line_bbox[1])
        return out

    def _caption_grid_qualifies(
        self, norm_rows: List[List[str]], anchor: Optional[_CaptionAnchor] = None
    ) -> bool:
        if len(norm_rows) < 2:
            return False
        mc = max(len(r) for r in norm_rows)
        if mc >= 2:
            return not self._raw_matrix_mostly_noise(norm_rows)
        if anchor and anchor.table_number and mc >= 1 and len(norm_rows) >= 5:
            return not self._raw_matrix_mostly_noise(norm_rows)
        return False

    def _bbox_overlaps_any_same_page(
        self,
        items: List[_RawTable],
        page_num: int,
        bbox: Tuple[float, float, float, float],
        thresh: float,
    ) -> bool:
        for rt in items:
            if rt.page_start != page_num:
                continue
            if self._bbox_iou(bbox, rt.bbox) >= thresh:
                return True
        return False

    def _anchor_search_region_bbox(
        self, page: Any, anchor: _CaptionAnchor, extend_to_bottom: bool = False
    ) -> Tuple[float, float, float, float]:
        y0 = anchor.caption_bottom + 2.5
        if extend_to_bottom:
            y1 = float(page.height)
        else:
            y1 = min(float(page.height), y0 + _caption_anchor_max_depth_pt())
        return (0.0, y0, float(page.width), y1)

    def _pdfplumber_raw_tables_for_caption_region(
        self,
        page: Any,
        page_num: int,
        region: Tuple[float, float, float, float],
        anchor: _CaptionAnchor,
        tbl_settings: Optional[Dict[str, Any]],
        loose_settings: Optional[Dict[str, Any]],
    ) -> List[_RawTable]:
        x0, y0, x1, y1 = region
        if y1 - y0 < 28.0:
            return []
        try:
            rgn = page.crop((x0, y0, x1, y1))
        except Exception:
            return []
        found: List[Any] = []
        if tbl_settings:
            found = rgn.find_tables(table_settings=tbl_settings) or []
        else:
            found = rgn.find_tables() or []
        if not found and loose_settings:
            found = rgn.find_tables(table_settings=loose_settings) or []
        out: List[_RawTable] = []
        for t in found:
            rows = t.extract() or []
            norm_rows = self._normalize_rows(rows)
            if not self._caption_grid_qualifies(norm_rows, anchor):
                continue
            out.append(
                _RawTable(
                    page_start=page_num,
                    page_end=page_num,
                    bbox=t.bbox,
                    rows=norm_rows,
                    table_number=None,
                    title=None,
                    source_method="pdfplumber:caption_region",
                    continuation_caption=False,
                )
            )
        return out

    def _camelot_raw_tables_for_caption_region(
        self,
        source_pdf_path: str,
        page_num: int,
        page_height: float,
        region: Tuple[float, float, float, float],
        anchor: _CaptionAnchor,
    ) -> List[_RawTable]:
        camelot = _get_camelot_module()
        if camelot is None:
            return []
        x0, y0, x1, y1 = region
        top_pdf = page_height - y0
        bottom_pdf = page_height - y1
        area_str = f"{x0},{top_pdf},{x1},{bottom_pdf}"
        out: List[_RawTable] = []
        for flavor in ("lattice", "stream"):
            try:
                tl = camelot.read_pdf(
                    source_pdf_path,
                    pages=str(page_num),
                    flavor=flavor,
                    table_areas=[area_str],
                )
            except Exception as e:
                logger.debug("Camelot caption_region %s page %s: %s", flavor, page_num, e)
                continue
            for idx in range(len(tl)):
                t = tl[idx]
                try:
                    df = t.df
                    rows = [
                        [self._normalize_scalar_to_str(x) for x in row]
                        for row in df.values.tolist()
                    ]
                except Exception:
                    continue
                norm_rows = self._normalize_rows(rows)  # type: ignore[arg-type]
                if not self._caption_grid_qualifies(norm_rows, anchor):
                    continue
                bbox_pdf = self._camelot_bbox_to_pdfplumber(t, page_num, source_pdf_path)
                bb = bbox_pdf if bbox_pdf else (x0, y0, x1, y1)
                out.append(
                    _RawTable(
                        page_start=page_num,
                        page_end=page_num,
                        bbox=bb,
                        rows=norm_rows,
                        table_number=None,
                        title=None,
                        source_method=f"camelot:caption_region:{flavor}",
                        continuation_caption=False,
                    )
                )
        return out

    def _tabula_raw_tables_for_caption_region(
        self,
        source_pdf_path: str,
        page_num: int,
        region: Tuple[float, float, float, float],
        anchor: _CaptionAnchor,
    ) -> List[_RawTable]:
        try:
            import tabula
        except Exception as e:
            logger.debug("tabula-py caption_region: %s", e)
            return []
        x0, y0, x1, y1 = region
        area = [y0, x0, y1, x1]
        out: List[_RawTable] = []
        for lattice in (False, True):
            try:
                dfs = tabula.read_pdf(
                    source_pdf_path,
                    pages=page_num,
                    area=area,
                    multiple_tables=True,
                    guess=not lattice,
                    lattice=lattice,
                )
            except Exception as e:
                logger.debug("Tabula caption_region lattice=%s page %s: %s", lattice, page_num, e)
                continue
            chunks: List[Any] = []
            if dfs is None:
                continue
            if not isinstance(dfs, list):
                chunks = [dfs]
            else:
                chunks = dfs
            for df in chunks:
                try:
                    rows = [
                        [self._normalize_scalar_to_str(x) for x in row]
                        for row in df.values.tolist()
                    ]
                except Exception:
                    continue
                norm_rows = self._normalize_rows(rows)  # type: ignore[arg-type]
                if not self._caption_grid_qualifies(norm_rows, anchor):
                    continue
                out.append(
                    _RawTable(
                        page_start=page_num,
                        page_end=page_num,
                        bbox=(x0, y0, x1, y1),
                        rows=norm_rows,
                        table_number=None,
                        title=None,
                        source_method="tabula:caption_region",
                        continuation_caption=False,
                    )
                )
        return out

    def _pick_best_raw_for_caption(
        self, candidates: List[_RawTable], clauses: List[Any]
    ) -> Optional[_RawTable]:
        best_rt: Optional[_RawTable] = None
        best_sc = -999.0
        for rt in candidates:
            try:
                tbl = self._to_table_model(rt, clauses)
                q = self._quality_components(tbl)
            except Exception:
                continue
            if q.score > best_sc:
                best_sc = q.score
                best_rt = rt
        return best_rt

    def _caption_first_multi_engine_for_page(
        self,
        source_pdf_path: str,
        page: Any,
        page_num: int,
        page_words: List[dict],
        out: List[_RawTable],
        tbl_settings: Optional[Dict[str, Any]],
        loose_settings: Optional[Dict[str, Any]],
        clauses: List[Any],
    ) -> None:
        if not _caption_anchor_pass_enabled():
            return
        anchors = self._discover_caption_anchors_from_page_words(
            page_words, float(page.width), float(page.height)
        )
        if not anchors:
            return
        ph = float(page.height)
        for anchor in self._anchors_topmost_per_number(anchors):
            reg0 = self._anchor_search_region_bbox(page, anchor, False)
            if any(
                rt.page_start == page_num
                and rt.table_number == anchor.table_number
                and self._bbox_iou(reg0, rt.bbox) > 0.55
                for rt in out
            ):
                continue

            def collect(ext_bottom: bool) -> List[_RawTable]:
                reg = self._anchor_search_region_bbox(page, anchor, ext_bottom)
                cands: List[_RawTable] = []
                cands.extend(
                    self._pdfplumber_raw_tables_for_caption_region(
                        page, page_num, reg, anchor, tbl_settings, loose_settings
                    )
                )
                if _caption_region_multi_engine_enabled():
                    cands.extend(
                        self._camelot_raw_tables_for_caption_region(
                            source_pdf_path, page_num, ph, reg, anchor
                        )
                    )
                    cands.extend(
                        self._tabula_raw_tables_for_caption_region(
                            source_pdf_path, page_num, reg, anchor
                        )
                    )
                return cands

            candidates = collect(False)
            if not candidates and _caption_region_expand_when_empty():
                candidates = collect(True)
                if candidates:
                    self._diag["caption_multi_engine_expand_retries"] += 1
            if not candidates:
                continue
            best = self._pick_best_raw_for_caption(candidates, clauses)
            if best is None:
                continue
            best = self._filter_noise_rows_raw(best)
            if not self._caption_grid_qualifies(best.rows, anchor):
                continue
            if self._bbox_overlaps_any_same_page(out, page_num, best.bbox, 0.82):
                continue
            best.table_number = anchor.table_number
            if anchor.title and not (best.title or "").strip():
                best.title = anchor.title
            best.continuation_caption = anchor.continuation
            out.append(best)
            self._diag["caption_multi_engine_picks"] += 1
            self._diag["caption_anchor_grids_added"] += 1

    def _caption_label_unnumbered_on_page(
        self,
        page_num: int,
        page_words: List[dict],
        page_width: float,
        page_height: float,
        out: List[_RawTable],
    ) -> None:
        anchors = self._discover_caption_anchors_from_page_words(
            page_words, page_width, page_height
        )
        if not anchors:
            return
        for rt in out:
            if rt.page_start != page_num or rt.table_number:
                continue
            pick = self._best_caption_anchor_above_table(anchors, rt.bbox)
            if pick is None:
                continue
            rt.table_number = pick.table_number
            if pick.title and not (rt.title or "").strip():
                rt.title = pick.title
            if pick.continuation:
                rt.continuation_caption = True
            self._diag["caption_anchor_labeled"] += 1

    def _best_caption_anchor_above_table(
        self, anchors: List[_CaptionAnchor], table_bbox: Tuple[float, float, float, float]
    ) -> Optional[_CaptionAnchor]:
        _tx0, ty0, _tx1, _ty1 = table_bbox
        max_gap = _caption_anchor_max_gap_pt()
        best: Optional[_CaptionAnchor] = None
        best_gap = 1e9
        for a in anchors:
            gap = ty0 - a.caption_bottom
            if gap < -4.0 or gap > max_gap:
                continue
            if gap < best_gap:
                best_gap = gap
                best = a
        return best

    def _anchors_topmost_per_number(self, anchors: List[_CaptionAnchor]) -> List[_CaptionAnchor]:
        by_num: Dict[str, _CaptionAnchor] = {}
        for a in sorted(anchors, key=lambda x: x.line_bbox[1]):
            if a.table_number not in by_num:
                by_num[a.table_number] = a
        return list(by_num.values())

    # --- pdfplumber extraction ---

    def _extract_raw_tables_pdfplumber(self, source_pdf_path: str) -> List[_RawTable]:
        import pdfplumber

        out: List[_RawTable] = []
        max_pages = _table_pipeline_max_pages()
        tbl_settings = _pdfplumber_table_settings()
        loose_settings = _pdfplumber_loose_table_settings()
        pages_with_pdfplumber_hit: set[int] = set()

        with pdfplumber.open(source_pdf_path) as pdf:
            n_pages = len(pdf.pages)
            last_page = n_pages if max_pages is None else min(n_pages, max_pages)
            empty_clauses: List[Any] = []

            if _caption_anchor_pass_enabled():
                for page_num in range(1, last_page + 1):
                    page = pdf.pages[page_num - 1]
                    wds = page.extract_words() or []
                    self._caption_first_multi_engine_for_page(
                        source_pdf_path,
                        page,
                        page_num,
                        wds,
                        out,
                        tbl_settings,
                        loose_settings,
                        empty_clauses,
                    )

            for page_num in range(1, last_page + 1):
                page = pdf.pages[page_num - 1]
                page_words = page.extract_words() or []
                tables_found = page.find_tables(table_settings=tbl_settings) or []
                used_loose = False
                if not tables_found and loose_settings:
                    tables_found = page.find_tables(table_settings=loose_settings) or []
                    used_loose = bool(tables_found)
                    if used_loose:
                        self._diag["pdfplumber_loose_pass_pages"] += 1

                for t in tables_found:
                    if self._bbox_overlaps_any_same_page(out, page_num, t.bbox, 0.78):
                        continue
                    rows = t.extract() or []
                    norm_rows = self._normalize_rows(rows)
                    if not norm_rows:
                        continue
                    table_number, title, cont_cap = self._infer_caption(page_words, t.bbox)
                    if not table_number:
                        table_number = self._infer_table_number_from_rows(norm_rows)
                    src = "pdfplumber:loose" if used_loose else "pdfplumber"
                    out.append(
                        _RawTable(
                            page_start=page_num,
                            page_end=page_num,
                            bbox=t.bbox,
                            rows=norm_rows,
                            table_number=table_number,
                            title=title,
                            source_method=src,
                            continuation_caption=cont_cap,
                        )
                    )
                    pages_with_pdfplumber_hit.add(page_num)

            if _caption_anchor_pass_enabled():
                for page_num in range(1, last_page + 1):
                    page = pdf.pages[page_num - 1]
                    wds = page.extract_words() or []
                    self._caption_label_unnumbered_on_page(
                        page_num,
                        wds,
                        float(page.width),
                        float(page.height),
                        out,
                    )

            if _page_sweep_when_empty_enabled() and _fusion_enabled():
                busy_pages = pages_with_pdfplumber_hit | {rt.page_start for rt in out}
                for page_num in range(1, last_page + 1):
                    if page_num in busy_pages:
                        continue
                    page = pdf.pages[page_num - 1]
                    page_words = page.extract_words() or []
                    full_bbox = (0.0, 0.0, float(page.width), float(page.height))
                    swept: List[_RawTable] = []
                    swept.extend(self._camelot_sweep_page(source_pdf_path, page_num, page_words))
                    swept.extend(
                        self._tabula_sweep_page(
                            source_pdf_path, page_num, page_words, full_bbox
                        )
                    )
                    swept = self._dedupe_raw_tables_iou(swept)
                    max_k = _page_sweep_max_per_page()
                    if len(swept) > max_k:
                        swept.sort(
                            key=lambda rt: sum(len(c) for c in rt.rows)
                            * max(1, len(rt.rows[0]) if rt.rows else 1),
                            reverse=True,
                        )
                        swept = swept[:max_k]
                    for rt in swept:
                        filtered = self._filter_noise_rows_raw(rt)
                        if len(filtered.rows) < 2:
                            continue
                        # P0 sweep gating: require min columns or caption anchor
                        if not self._sweep_result_acceptable(filtered, page_words):
                            continue
                        out.append(filtered)
                        self._diag["page_sweep_raw_added"] += 1

        # AI-powered table discovery (if enabled)
        if self._ai_service and self._ai_service.discovery_enabled:
            # Get AI discovery mode from settings
            try:
                from config import settings
                ai_mode = getattr(settings, "ai_discovery_mode", "weak_signals").lower()
            except Exception:
                ai_mode = "weak_signals"
            
            logger.info("Running AI table discovery (mode: %s)...", ai_mode)
            ai_discovered_count = 0
            
            # Determine pages to analyze based on mode
            if ai_mode == "comprehensive":
                # Analyze ALL pages
                pages_needing_ai = set(range(1, last_page + 1))
                logger.info(
                    "Comprehensive mode: analyzing ALL %d pages with AI vision",
                    len(pages_needing_ai)
                )
                try:
                    from config import settings
                    max_cost = float(getattr(settings, "ai_comprehensive_max_cost", 2.0))
                except Exception:
                    max_cost = 2.0
                logger.info("Cost limit: $%.2f", max_cost)
            
            elif ai_mode == "balanced":
                # Enhanced weak signals (future: add keyword matching, gap analysis)
                # For now, same as weak_signals but could be expanded
                pages_needing_ai = self._detect_weak_table_pages(out, source_pdf_path, last_page)
                logger.info(
                    "Balanced mode: analyzing %d pages with weak signals (expandable)",
                    len(pages_needing_ai)
                )
            
            else:  # "weak_signals" (default)
                # Only pages with detected problems
                pages_needing_ai = self._detect_weak_table_pages(out, source_pdf_path, last_page)
                if pages_needing_ai:
                    logger.info(
                        "Weak signals mode: %d pages need AI analysis: %s",
                        len(pages_needing_ai),
                        sorted(list(pages_needing_ai))[:10]  # Show first 10
                    )
                else:
                    logger.info("Weak signals mode: No weak table signals detected - skipping AI discovery")
            
            with pdfplumber.open(source_pdf_path) as pdf:
                for page_num in sorted(pages_needing_ai):
                    # Check cost limit for comprehensive mode
                    if ai_mode == "comprehensive":
                        current_cost = getattr(self._ai_service.metrics, 'total_cost_usd', 0.0)
                        try:
                            from config import settings
                            max_cost = float(getattr(settings, "ai_comprehensive_max_cost", 2.0))
                        except Exception:
                            max_cost = 2.0
                        if current_cost >= max_cost:
                            logger.warning(
                                "AI cost limit reached ($%.2f / $%.2f). Stopping AI discovery at page %d.",
                                current_cost, max_cost, page_num
                            )
                            break
                    
                    page = pdf.pages[page_num - 1]
                    
                    # Get existing table bboxes on this page to avoid duplicates
                    existing_bboxes = [rt.bbox for rt in out if rt.page_start == page_num]
                    
                    # Convert page to image for AI vision
                    try:
                        page_image = page.to_image(resolution=150).original
                    except Exception as e:
                        logger.debug("Failed to convert page %s to image: %s", page_num, e)
                        continue
                    
                    # Call AI discovery
                    try:
                        ai_regions = self._ai_service.discover_tables(
                            page_image=page_image,
                            page_num=page_num,
                            existing_table_bboxes=existing_bboxes
                        )
                    except Exception as e:
                        logger.warning("AI discovery failed on page %s: %s", page_num, e)
                        continue
                    
                    # Extract tables from AI-discovered regions
                    for region in ai_regions:
                        # Convert percentage bbox to absolute coordinates
                        bbox = self._percent_bbox_to_absolute(
                            region.bbox_percent,
                            float(page.width),
                            float(page.height)
                        )
                        
                        # Extract table from this region using pdfplumber
                        try:
                            crop = page.crop(bbox)
                            tables_found = crop.find_tables(table_settings=tbl_settings) or []
                            
                            if tables_found:
                                for t in tables_found:
                                    rows = t.extract() or []
                                    norm_rows = self._normalize_rows(rows)
                                    if not norm_rows or len(norm_rows) < 2:
                                        continue
                                    
                                    out.append(_RawTable(
                                        page_start=page_num,
                                        page_end=page_num,
                                        bbox=bbox,
                                        rows=norm_rows,
                                        table_number=region.table_number,
                                        title=region.description,
                                        source_method="ai_discovery+pdfplumber",
                                        continuation_caption=False
                                    ))
                                    ai_discovered_count += 1
                                    self._diag["ai_discovery_tables"] = ai_discovered_count
                        except Exception as e:
                            logger.debug("AI region extraction failed page %s: %s", page_num, e)
            
            # Log final summary
            final_cost = getattr(self._ai_service.metrics, 'total_cost_usd', 0.0)
            logger.info(
                "AI discovery complete: %d tables found from %d pages analyzed (cost: $%.4f)",
                ai_discovered_count, len(pages_needing_ai), final_cost
            )
            
            # Provide recommendations based on mode and results
            if ai_mode == "weak_signals" and ai_discovered_count < 5:
                logger.info(
                    "💡 Tip: For better coverage, try AI_DISCOVERY_MODE=comprehensive "
                    "(~$%.2f for %d pages, expect +15-20 tables)",
                    last_page * 0.007, last_page
                )

        if not out:
            logger.warning("No tables extracted by pdfplumber (incl. loose pass / page sweep)")
        return out

    def _detect_weak_table_pages(
        self,
        extracted_tables: List[_RawTable],
        source_pdf_path: str,
        last_page: int
    ) -> Set[int]:
        """
        Detect pages with weak table signals that need AI analysis.
        
        Weak signals include:
        1. Caption detected but no matching table extracted
        2. Low-quality extractions (few rows, low quality score)
        3. Pages where all engines failed (pdfplumber, camelot, tabula all returned nothing)
        4. Tables marked with semantic_hard_fail that need validation
        
        Returns:
            Set of page numbers (1-indexed) that need AI analysis
        """
        pages_needing_ai: Set[int] = set()
        weak_signal_reasons: Dict[int, List[str]] = {}
        
        # Build index of extracted tables by page
        tables_by_page: Dict[int, List[_RawTable]] = {}
        for rt in extracted_tables:
            if rt.page_start not in tables_by_page:
                tables_by_page[rt.page_start] = []
            tables_by_page[rt.page_start].append(rt)
        
        # Collect caption anchors to detect orphaned captions
        caption_pages: Dict[int, List[str]] = {}
        try:
            import pdfplumber
            with pdfplumber.open(source_pdf_path) as pdf:
                for page_num in range(1, min(last_page + 1, len(pdf.pages) + 1)):
                    page = pdf.pages[page_num - 1]
                    page_words = page.extract_words() or []
                    if page_words:
                        anchors = self._discover_caption_anchors_from_page_words(
                            page_words,
                            float(page.width),
                            float(page.height)
                        )
                        if anchors:
                            caption_pages[page_num] = [a.table_number for a in anchors]
        except Exception as e:
            logger.debug("Failed to extract caption anchors for weak detection: %s", e)
        
        # Signal 1: Caption detected but no matching table extracted
        for page_num, caption_numbers in caption_pages.items():
            page_tables = tables_by_page.get(page_num, [])
            extracted_numbers = {rt.table_number for rt in page_tables if rt.table_number}
            
            for caption_num in caption_numbers:
                if caption_num not in extracted_numbers:
                    pages_needing_ai.add(page_num)
                    if page_num not in weak_signal_reasons:
                        weak_signal_reasons[page_num] = []
                    weak_signal_reasons[page_num].append(f"orphaned_caption:{caption_num}")
                    self._diag["ai_trigger_orphaned_caption"] = self._diag.get("ai_trigger_orphaned_caption", 0) + 1
        
        # Signal 2: Low-quality extractions (weak tables)
        for page_num, page_tables in tables_by_page.items():
            for rt in page_tables:
                # Check for weak signals
                is_weak = False
                reason = None
                
                # Very few rows
                if len(rt.rows) < 3:
                    is_weak = True
                    reason = f"few_rows:{len(rt.rows)}"
                    self._diag["ai_trigger_few_rows"] = self._diag.get("ai_trigger_few_rows", 0) + 1
                
                # Very few columns (likely a list, not a table)
                elif rt.rows and max(len(row) for row in rt.rows) < 2:
                    is_weak = True
                    reason = "single_column"
                    self._diag["ai_trigger_single_column"] = self._diag.get("ai_trigger_single_column", 0) + 1
                
                # Mostly empty cells (sparse data)
                elif rt.rows:
                    total_cells = sum(len(row) for row in rt.rows)
                    empty_cells = sum(1 for row in rt.rows for cell in row if not cell.strip())
                    if total_cells > 0 and (empty_cells / total_cells) > 0.7:
                        is_weak = True
                        reason = f"sparse_data:{empty_cells}/{total_cells}"
                        self._diag["ai_trigger_sparse_data"] = self._diag.get("ai_trigger_sparse_data", 0) + 1
                
                if is_weak:
                    pages_needing_ai.add(page_num)
                    if page_num not in weak_signal_reasons:
                        weak_signal_reasons[page_num] = []
                    weak_signal_reasons[page_num].append(reason)
        
        # Signal 3: Pages with no extractions (all engines failed)
        pages_with_tables = set(tables_by_page.keys())
        for page_num in range(1, last_page + 1):
            if page_num not in pages_with_tables:
                # Check if page has text (not just blank page)
                try:
                    import pdfplumber
                    with pdfplumber.open(source_pdf_path) as pdf:
                        if page_num <= len(pdf.pages):
                            page = pdf.pages[page_num - 1]
                            page_text = page.extract_text() or ""
                            # Only flag pages with substantial text content
                            if len(page_text.strip()) > 200:
                                pages_needing_ai.add(page_num)
                                if page_num not in weak_signal_reasons:
                                    weak_signal_reasons[page_num] = []
                                weak_signal_reasons[page_num].append("no_extraction")
                                self._diag["ai_trigger_no_extraction"] = self._diag.get("ai_trigger_no_extraction", 0) + 1
                except Exception:
                    pass
        
        # Log weak signals detected
        if weak_signal_reasons:
            for page_num in sorted(weak_signal_reasons.keys())[:10]:  # Log first 10
                logger.debug(
                    "Weak table signals on page %s: %s",
                    page_num,
                    ", ".join(weak_signal_reasons[page_num])
                )
        
        return pages_needing_ai
    
    @staticmethod
    def _percent_bbox_to_absolute(
        bbox_percent,  # Can be Tuple or Dict from AI service
        page_width: float,
        page_height: float
    ) -> Tuple[float, float, float, float]:
        """
        Convert percentage-based bbox (0-100) to absolute pixel coordinates.
        
        Args:
            bbox_percent: Either a tuple (x0, y0, x1, y1) or dict {"top", "left", "bottom", "right"}
            page_width: Page width in points
            page_height: Page height in points
        
        Returns:
            Tuple of (x0, y0, x1, y1) in absolute coordinates
        """
        # Handle dict format from AI service
        if isinstance(bbox_percent, dict):
            x0_pct = float(bbox_percent.get("left", 0))
            y0_pct = float(bbox_percent.get("top", 0))
            x1_pct = float(bbox_percent.get("right", 100))
            y1_pct = float(bbox_percent.get("bottom", 100))
        else:
            # Handle tuple format
            x0_pct, y0_pct, x1_pct, y1_pct = bbox_percent
            x0_pct = float(x0_pct)
            y0_pct = float(y0_pct)
            x1_pct = float(x1_pct)
            y1_pct = float(y1_pct)
        
        return (
            (x0_pct / 100.0) * page_width,
            (y0_pct / 100.0) * page_height,
            (x1_pct / 100.0) * page_width,
            (y1_pct / 100.0) * page_height
        )

    @staticmethod
    def _bbox_iou(
        a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]
    ) -> float:
        ax0, ay0, ax1, ay1 = a
        bx0, by0, bx1, by1 = b
        ix0, iy0 = max(ax0, bx0), max(ay0, by0)
        ix1, iy1 = min(ax1, bx1), min(ay1, by1)
        iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
        inter = iw * ih
        if inter <= 0:
            return 0.0
        aa = max(0.1, (ax1 - ax0) * (ay1 - ay0))
        ba = max(0.1, (bx1 - bx0) * (by1 - by0))
        union = aa + ba - inter
        return inter / union if union > 0 else 0.0

    def _dedupe_raw_tables_iou(
        self, items: List[_RawTable], iou_threshold: float = 0.82
    ) -> List[_RawTable]:
        if len(items) <= 1:
            return items

        def _score(rt: _RawTable) -> int:
            return sum(len(r) for r in rt.rows) * max(1, len(rt.rows[0]) if rt.rows else 1)

        items = sorted(items, key=_score, reverse=True)
        kept: List[_RawTable] = []
        for t in items:
            if any(self._bbox_iou(t.bbox, k.bbox) >= iou_threshold for k in kept):
                continue
            kept.append(t)
        return kept

    def _camelot_sweep_page(
        self, source_pdf_path: str, page: int, page_words: List[dict]
    ) -> List[_RawTable]:
        """Camelot lattice+stream for a whole page (no pdfplumber anchor)."""
        camelot = _get_camelot_module()
        if camelot is None:
            return []
        out: List[_RawTable] = []
        for flavor in ("lattice", "stream"):
            try:
                tl = camelot.read_pdf(source_pdf_path, pages=str(page), flavor=flavor)
            except Exception as e:
                logger.debug("Camelot sweep %s page %s failed: %s", flavor, page, e)
                continue
            for idx in range(len(tl)):
                t = tl[idx]
                try:
                    df = t.df
                    rows = [
                        [self._normalize_scalar_to_str(x) for x in row]
                        for row in df.values.tolist()
                    ]
                except Exception:
                    continue
                norm_rows = self._normalize_rows(rows)  # type: ignore[arg-type]
                if len(norm_rows) < 2:
                    continue
                bbox_pdf = self._camelot_bbox_to_pdfplumber(t, page, source_pdf_path)
                bb = bbox_pdf if bbox_pdf else (0.0, 0.0, 1.0, 1.0)
                table_number, title, cont_cap = self._infer_caption(page_words, bb)
                if not table_number:
                    table_number = self._infer_table_number_from_rows(norm_rows)
                out.append(
                    _RawTable(
                        page_start=page,
                        page_end=page,
                        bbox=bb,
                        rows=norm_rows,
                        table_number=table_number,
                        title=title,
                        source_method=f"camelot:sweep:{flavor}",
                        continuation_caption=cont_cap,
                    )
                )
        return out

    def _tabula_sweep_page(
        self,
        source_pdf_path: str,
        page: int,
        page_words: List[dict],
        full_bbox: Tuple[float, float, float, float],
    ) -> List[_RawTable]:
        """Tabula lattice+stream for a whole page when pdfplumber found nothing."""
        try:
            import tabula
        except Exception as e:
            logger.debug("tabula-py unavailable for sweep: %s", e)
            return []
        out: List[_RawTable] = []
        dfs_list: List[Any] = []
        try:
            dfs_stream = tabula.read_pdf(
                source_pdf_path,
                pages=page,
                multiple_tables=True,
                guess=True,
                lattice=False,
            )
        except Exception as e:
            logger.debug("Tabula sweep stream page %s failed: %s", page, e)
            dfs_stream = []
        try:
            dfs_lattice = tabula.read_pdf(
                source_pdf_path,
                pages=page,
                multiple_tables=True,
                guess=False,
                lattice=True,
            )
        except Exception as e:
            logger.debug("Tabula sweep lattice page %s failed: %s", page, e)
            dfs_lattice = []
        for chunk in (dfs_stream, dfs_lattice):
            if chunk is None:
                continue
            if not isinstance(chunk, list):
                dfs_list.append(chunk)
            else:
                dfs_list.extend(chunk)
        row_matrices: List[List[List[str]]] = []
        for df in dfs_list:
            try:
                rows = [
                    [self._normalize_scalar_to_str(x) for x in row]
                    for row in df.values.tolist()
                ]
            except Exception:
                continue
            norm_rows = self._normalize_rows(rows)  # type: ignore[arg-type]
            if len(norm_rows) < 2:
                continue
            row_matrices.append(norm_rows)

        _fx0, _fy0, fx1, fy1 = full_bbox
        page_h = max(1.0, fy1)
        band = max(40.0, page_h / max(len(row_matrices) * 2, 1))
        for i, norm_rows in enumerate(row_matrices):
            y0 = min(page_h - band * 1.5, float(i) * band * 1.2)
            bb = (0.0, y0, fx1, min(y0 + band * 2.5, page_h))
            table_number, title, cont_cap = self._infer_caption(page_words, bb)
            if not table_number:
                table_number = self._infer_table_number_from_rows(norm_rows)
            out.append(
                _RawTable(
                    page_start=page,
                    page_end=page,
                    bbox=bb,
                    rows=norm_rows,
                    table_number=table_number,
                    title=title,
                    source_method="tabula:sweep",
                    continuation_caption=cont_cap,
                )
            )
        return out

    # --- Camelot / Tabula fusion (optional deps) ---

    def _fusion_raw_tables(self, source_pdf_path: str, anchor: _RawTable) -> List[_RawTable]:
        page = anchor.page_start
        if page in self._fusion_by_page:
            return self._filter_fusion_by_anchor(self._fusion_by_page[page], anchor)
        collected: List[_RawTable] = []
        collected.extend(self._camelot_page_tables(source_pdf_path, page, anchor))
        collected.extend(self._tabula_page_tables(source_pdf_path, page, anchor))
        self._fusion_by_page[page] = collected
        return self._filter_fusion_by_anchor(collected, anchor)

    def _filter_fusion_by_anchor(self, fusion_list: List[_RawTable], anchor: _RawTable) -> List[_RawTable]:
        if not fusion_list:
            return []
        out = [
            f
            for f in fusion_list
            if f.source_method == "tabula" or self._bbox_overlap_ok(anchor.bbox, f.bbox)
        ]
        return out if out else list(fusion_list)

    def _camelot_page_tables(
        self, source_pdf_path: str, page: int, anchor: _RawTable
    ) -> List[_RawTable]:
        camelot = _get_camelot_module()
        if camelot is None:
            return []
        out: List[_RawTable] = []
        for flavor in ("lattice", "stream"):
            try:
                tl = camelot.read_pdf(source_pdf_path, pages=str(page), flavor=flavor)
            except Exception as e:
                logger.debug("Camelot %s page %s failed: %s", flavor, page, e)
                continue
            for idx in range(len(tl)):
                t = tl[idx]
                try:
                    df = t.df
                    rows = [[self._normalize_scalar_to_str(x) for x in row] for row in df.values.tolist()]
                except Exception:
                    continue
                norm_rows = self._normalize_rows(rows)  # type: ignore[arg-type]
                if len(norm_rows) < 2:
                    continue
                bbox_pdf = self._camelot_bbox_to_pdfplumber(t, page, source_pdf_path)
                if bbox_pdf and not self._bbox_overlap_ok(anchor.bbox, bbox_pdf):
                    continue
                bb = bbox_pdf or anchor.bbox
                out.append(
                    _RawTable(
                        page_start=page,
                        page_end=page,
                        bbox=bb,
                        rows=norm_rows,
                        table_number=anchor.table_number,
                        title=anchor.title,
                        source_method=f"camelot:{flavor}",
                        continuation_caption=anchor.continuation_caption,
                    )
                )
        return out

    def _camelot_bbox_to_pdfplumber(self, camelot_table: Any, page: int, path: str) -> Optional[Tuple[float, float, float, float]]:
        bbox = getattr(camelot_table, "_bbox", None) or getattr(camelot_table, "bbox", None)
        if not bbox or len(bbox) != 4:
            return None
        x1, y1, x2, y2 = bbox
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                h = pdf.pages[page - 1].height
        except Exception:
            return (x1, y1, x2, y2)
        top = h - y2
        bottom = h - y1
        return (x1, top, x2, bottom)

    def _tabula_page_tables(
        self, source_pdf_path: str, page: int, anchor: _RawTable
    ) -> List[_RawTable]:
        try:
            import tabula
        except Exception as e:
            logger.debug("tabula-py unavailable: %s", e)
            return []
        out: List[_RawTable] = []
        try:
            dfs_stream = tabula.read_pdf(
                source_pdf_path,
                pages=page,
                multiple_tables=True,
                guess=True,
                lattice=False,
            )
        except Exception as e:
            logger.debug("Tabula stream page %s failed: %s", page, e)
            dfs_stream = []
        try:
            dfs_lattice = tabula.read_pdf(
                source_pdf_path,
                pages=page,
                multiple_tables=True,
                guess=False,
                lattice=True,
            )
        except Exception as e:
            logger.debug("Tabula lattice page %s failed: %s", page, e)
            dfs_lattice = []
        dfs_list: List[Any] = []
        for chunk in (dfs_stream, dfs_lattice):
            if chunk is None:
                continue
            if not isinstance(chunk, list):
                dfs_list.append(chunk)
            else:
                dfs_list.extend(chunk)
        if not dfs_list:
            return []
        for df in dfs_list:
            try:
                rows = [[self._normalize_scalar_to_str(x) for x in row] for row in df.values.tolist()]
            except Exception:
                continue
            norm_rows = self._normalize_rows(rows)  # type: ignore[arg-type]
            if len(norm_rows) < 2:
                continue
            out.append(
                _RawTable(
                    page_start=page,
                    page_end=page,
                    bbox=anchor.bbox,
                    rows=norm_rows,
                    table_number=anchor.table_number,
                    title=anchor.title,
                    source_method="tabula",
                    continuation_caption=anchor.continuation_caption,
                )
            )
        return out

    def _bbox_overlap_ok(
        self, a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]
    ) -> bool:
        ax0, ay0, ax1, ay1 = a
        bx0, by0, bx1, by1 = b
        ix0, iy0 = max(ax0, bx0), max(ay0, by0)
        ix1, iy1 = min(ax1, bx1), min(ay1, by1)
        iw, ih = max(0, ix1 - ix0), max(0, iy1 - iy0)
        if iw <= 0 or ih <= 0:
            return False
        inter = iw * ih
        ha, hb = max(0.1, ay1 - ay0), max(0.1, by1 - by0)
        wa, wb = max(0.1, ax1 - ax0), max(0.1, bx1 - bx0)
        overlap_y = ih / min(ha, hb)
        overlap_x = iw / min(wa, wb)
        return overlap_y >= FUSION_BBOX_OVERLAP_MIN and overlap_x >= FUSION_BBOX_OVERLAP_MIN * 0.5

    # --- same-page fragment merge ---

    def _merge_same_page_fragments(self, raw_tables: List[_RawTable]) -> List[_RawTable]:
        if not raw_tables:
            return []
        by_page: Dict[int, List[_RawTable]] = {}
        for t in raw_tables:
            by_page.setdefault(t.page_start, []).append(t)
        merged_all: List[_RawTable] = []
        for page in sorted(by_page.keys()):
            items = sorted(by_page[page], key=lambda x: (x.bbox[1], x.bbox[0]))
            stack: List[_RawTable] = []
            for t in items:
                if not stack:
                    stack.append(t)
                    continue
                prev = stack[-1]
                if self._should_merge_same_page(prev, t):
                    stack[-1] = self._merge_two_raw(prev, t)
                    self._diag["same_page_merges"] += 1
                else:
                    stack.append(t)
            merged_all.extend(stack)
        return sorted(merged_all, key=lambda x: (x.page_start, x.bbox[1], x.bbox[0]))

    def _should_merge_same_page(self, a: _RawTable, b: _RawTable) -> bool:
        if a.page_start != b.page_start or a.page_end != b.page_end:
            return False
        ax0, ay0, ax1, ay1 = a.bbox
        bx0, by0, bx1, by1 = b.bbox
        vertical_gap = by0 - ay1
        if vertical_gap < 0 or vertical_gap > 52:
            return False
        iw = max(0, min(ax1, bx1) - max(ax0, bx0))
        wa = max(0.1, ax1 - ax0)
        wb = max(0.1, bx1 - bx0)
        if iw / min(wa, wb) < 0.45:
            return False
        ca = max(len(r) for r in a.rows) if a.rows else 0
        cb = max(len(r) for r in b.rows) if b.rows else 0
        if ca and cb and abs(ca - cb) > 3:
            return False
        if a.table_number and b.table_number and a.table_number != b.table_number:
            return False
        return True

    def _merge_two_raw(self, a: _RawTable, b: _RawTable) -> _RawTable:
        rows = list(a.rows) + list(b.rows)
        rows = self._normalize_rows(rows)  # type: ignore[arg-type]
        x0 = min(a.bbox[0], b.bbox[0])
        y0 = min(a.bbox[1], b.bbox[1])
        x1 = max(a.bbox[2], b.bbox[2])
        y1 = max(a.bbox[3], b.bbox[3])
        num = a.table_number or b.table_number
        title = a.title or b.title
        return _RawTable(
            page_start=a.page_start,
            page_end=a.page_end,
            bbox=(x0, y0, x1, y1),
            rows=rows,
            table_number=num,
            title=title,
            source_method=a.source_method,
            continuation_caption=a.continuation_caption or b.continuation_caption,
        )

    # --- noise filtering ---

    def _filter_noise_rows_raw(self, rt: _RawTable) -> _RawTable:
        kept = [r for r in rt.rows if not self._row_is_noise_artifact(r)]
        dropped = len(rt.rows) - len(kept)
        if dropped:
            self._diag["noise_rows_dropped"] += dropped
        if len(kept) < 2:
            return rt
        return _RawTable(
            page_start=rt.page_start,
            page_end=rt.page_end,
            bbox=rt.bbox,
            rows=kept,
            table_number=rt.table_number,
            title=rt.title,
            source_method=rt.source_method,
            continuation_caption=rt.continuation_caption,
        )

    def _row_is_noise_artifact(self, row: List[str]) -> bool:
        cells = [(c or "").strip() for c in row]
        if not any(cells):
            return True
        joined = " ".join(cells).strip()
        if len(joined) <= 2:
            return True
        if self.OCR_GARBAGE_ROW_PATTERN.match(joined):
            return True
        alnum = sum(1 for ch in joined if ch.isalnum())
        if len(joined) >= 6 and alnum / len(joined) < 0.25:
            return True
        if len(cells) == 1 and self.SINGLE_OCR_ARTIFACT_PATTERN.match(cells[0]):
            return True
        return False

    def _raw_matrix_mostly_noise(self, rows: List[List[str]]) -> bool:
        if not rows:
            return True
        noise = sum(1 for r in rows if self._row_is_noise_artifact(r))
        return noise / len(rows) > 0.45

    def _ocr_candidate_acceptable(self, table: Table, q: _QualityComponents) -> bool:
        if q.noise_ratio > 0.35:
            return False
        if q.placeholder_ratio > 0.2:
            return False
        if q.garbage_cell_ratio > 0.25:
            return False
        if q.one_column_value_list and q.row_count > 6:
            return False
        return True

    # --- caption / title (tight anchoring) ---

    def _cluster_words_into_lines(self, words: List[dict], y_tol: float = 3.5) -> List[List[dict]]:
        if not words:
            return []
        sorted_w = sorted(words, key=lambda w: (w.get("top", 0), w.get("x0", 0)))
        lines: List[List[dict]] = []
        for w in sorted_w:
            placed = False
            for ln in lines:
                ref = ln[0]
                if abs(w.get("top", 0) - ref.get("top", 0)) <= y_tol:
                    ln.append(w)
                    placed = True
                    break
            if not placed:
                lines.append([w])
        for ln in lines:
            ln.sort(key=lambda w: w.get("x0", 0))
        return lines

    def _infer_caption(
        self, page_words: List[dict], bbox: Tuple[float, float, float, float]
    ) -> Tuple[Optional[str], Optional[str], bool]:
        """
        P1: Improved caption detection with wider search and better appendix handling.
        """
        x0, y0, x1, _y1 = bbox
        
        # P1: Wider vertical search window (increased from 72 to 100)
        # P1: Expanded horizontal tolerance (increased from 28 to 40)
        tight = [
            w
            for w in page_words
            if (w.get("bottom", 0) <= y0 + 14)
            and (y0 - w.get("top", 0) <= 100)  # P1: wider vertical window
            and (w.get("x1", 0) >= x0 - 40)    # P1: wider horizontal tolerance
            and (w.get("x0", 0) <= x1 + 40)
        ]
        
        # P1: If no caption found strictly above, try lateral/overlapping search
        if not tight:
            lateral = [
                w
                for w in page_words
                if (abs(w.get("top", 0) - y0) <= 20)  # Near same vertical level
                and (w.get("x0", 0) <= x0 + 80)       # Left or slightly overlapping
            ]
            if lateral:
                tight = lateral
        
        if not tight:
            return None, None, False
        
        lines = self._cluster_words_into_lines(tight, y_tol=4.0)
        lines.sort(key=lambda ln: -max(w.get("bottom", 0) for w in ln))

        for ln in lines:
            text = " ".join((w.get("text") or "").strip() for w in ln).strip()
            text = re.sub(r"\s+", " ", text)
            if not text:
                continue
            
            # P1: Tolerate short leading noise before "Table"
            # Remove up to 15 chars of prefix if "Table" appears after it
            table_match = re.search(r"\bTable\b", text, re.IGNORECASE)
            if table_match and table_match.start() > 0 and table_match.start() <= 15:
                text = text[table_match.start():]
            
            parsed = _parse_table_number_from_text(text)
            if not parsed:
                continue
            raw_num, _span_s, span_e = parsed
            continuation_line = bool(self.CONTINUED_PATTERN.search(text))
            title_part = text[span_e:].strip()
            title = self._sanitize_table_title(title_part)
            return raw_num, title, continuation_line
        return None, None, False

    def _sanitize_table_title(self, title_part: str) -> Optional[str]:
        if not title_part:
            return None
        raw_tp = title_part.strip()
        if self.CONTINUED_PATTERN.search(raw_tp) and len(raw_tp) < 44:
            remainder = re.sub(r"(?i)\bcontinued\b", "", raw_tp)
            remainder = re.sub(r"^[\s.,;:()\-]+|[\s.,;:()\-]+$", "", remainder).strip()
            if not remainder:
                return None
        t = self.CLAUSE_LEAD_PATTERN.sub("", title_part).strip()
        t = re.sub(r"\s+", " ", t)
        cut = self.TITLE_PROSE_CUT_PATTERN.search(t)
        if cut:
            t = t[: cut.start()].strip()
        words = t.split()
        if len(words) > 18:
            t = " ".join(words[:18]).rstrip(",;:")
        if len(t) > 120:
            t = t[:120].rsplit(" ", 1)[0]
        if not t or self.NOISY_TITLE_PATTERN.match(t):
            return None
        return t

    def _infer_table_number_from_rows(self, rows: List[List[str]]) -> Optional[str]:
        """Infer table id only from cells that *begin* with a Table caption (strict).

        Joining the first rows into one string and matching anywhere picked up cross-references
        (e.g. 'see Table 4.2') and polluted table_number / parent_clause heuristics.
        """
        if not rows:
            return None
        for row in rows[:2]:
            for cell in row:
                s = (cell or "").strip()
                if not s or len(s) > 500:
                    continue
                parsed = _parse_table_number_from_text(s, anchor="line_start")
                if parsed:
                    return parsed[0]
        return None

    def _normalize_rows(self, rows: List[List[Optional[str]]]) -> List[List[str]]:
        cleaned: List[List[str]] = []
        max_cols = 0
        for row in rows:
            cells = [self._normalize_scalar_to_str(c) for c in (row or [])]
            if not any(cells):
                continue
            cleaned.append(cells)
            max_cols = max(max_cols, len(cells))
        if not cleaned:
            return []
        rect: List[List[str]] = []
        for row in cleaned:
            if len(row) < max_cols:
                row = row + [""] * (max_cols - len(row))
            rect.append(row)
        rect = self._expand_merged_cells(rect)
        return rect

    def _expand_merged_cells(self, rows: List[List[str]]) -> List[List[str]]:
        if not rows:
            return rows
        for r in range(len(rows)):
            last = ""
            for c in range(len(rows[r])):
                val = rows[r][c].strip()
                if val:
                    last = val
                elif last and r < 4:
                    rows[r][c] = last
        for c in range(len(rows[0])):
            last = ""
            for r in range(len(rows)):
                val = rows[r][c].strip()
                if val:
                    last = val
                elif last and r > 0 and r < 5:
                    rows[r][c] = last
        return rows

    def _is_header_like(self, row: List[str]) -> bool:
        non_empty = [c for c in row if c.strip()]
        if not non_empty:
            return False
        numeric_like = sum(
            1 for c in non_empty if re.search(r"\d", c) and not re.search(r"[a-zA-Z]", c)
        )
        alpha_like = sum(1 for c in non_empty if re.search(r"[a-zA-Z]", c))
        return alpha_like >= max(1, len(non_empty) // 2) and numeric_like <= max(1, len(non_empty) // 2)

    def _is_numeric_header_band_row(self, row: List[str]) -> bool:
        """Second header tier of standards tables: mostly units, ranges, or bare numbers."""
        non_empty = [c.strip() for c in row if c.strip()]
        if len(non_empty) < 2:
            return False
        numericish = 0
        for c in non_empty:
            if self.NUMERIC_UNIT_PATTERN.match(c):
                numericish += 1
                continue
            if re.match(r"^[\d.,]+\s*$", c) or re.match(r"^[\d.,]+\s*[%°]$", c):
                numericish += 1
                continue
            if len(c) <= 6 and re.match(r"^[\d.,\-–/]+$", c):
                numericish += 1
        return numericish >= max(2, int(len(non_empty) * 0.45))

    def _is_stack_header_row(self, rows: List[List[str]], idx: int, header_depth: int) -> bool:
        if idx <= 0 or idx >= len(rows) or header_depth <= 0:
            return False
        ref = rows[0]
        row = rows[idx]
        nonempty_cols = [i for i, c in enumerate(ref) if c.strip()]
        if not nonempty_cols:
            return False
        non_empty = [i for i, c in enumerate(row) if c.strip()]
        if not non_empty:
            return False
        aligned = sum(
            1
            for i in non_empty
            if i in nonempty_cols or any(abs(i - j) <= 1 for j in nonempty_cols)
        )
        if aligned < max(1, len(non_empty) // 2):
            return False
        if self._is_numeric_header_band_row(row) and aligned >= max(1, int(len(non_empty) * 0.4)):
            return True
        for i in non_empty:
            s = row[i].strip()
            if not (
                self.UNIT_TOKEN_PATTERN.match(s)
                or self.NUMERIC_UNIT_PATTERN.match(s)
                or len(s) <= 28
                or self._is_header_like(row)
            ):
                return False
        return True

    def _scrub_standards_glyph_only_cell(self, cell: str) -> str:
        """Remove cells that are only drawing/hidden-font glyphs (common in AS/NZS PDFs)."""
        c = re.sub(r"\s+", " ", (cell or "").strip())
        if not c:
            return ""
        if re.fullmatch(r"[\s~I_yfl•·|/\\\-]+", c, re.I):
            return ""
        if re.fullmatch(r"I{1,4}", c, re.I):
            return ""
        return c

    def _clean_header_cell(self, cell: str) -> str:
        c = re.sub(r"\s+", " ", (cell or "").strip())
        c = re.sub(r"(?<!\S)~+(?!\S)", " ", c)
        c = re.sub(r"\s+", " ", c).strip()
        c = re.sub(r"[_]{2,}", "_", c)
        c = re.sub(r"[~]{2,}", "", c)
        c = re.sub(r"\?\!", "", c)
        c = re.sub(r"([A-Za-z])([0-9])", r"\1 \2", c)
        c = re.sub(r"\s*_\s*", "_", c).strip(" _")
        return c

    def _combine_header_cells(self, top: str, bottom: str) -> str:
        a = self._clean_header_cell(top)
        b = self._clean_header_cell(bottom)
        if not a:
            return b
        if not b:
            return a
        if a.lower() == b.lower():
            return a
        if self.UNIT_TOKEN_PATTERN.match(b.lower()) or self.NUMERIC_UNIT_PATTERN.match(b):
            return f"{a} ({b})"
        bl = b.lower()
        if re.match(r"^[\d.,\s\-–/]+$", bl) and len(bl) <= 28:
            return f"{a} ({b})"
        if len(bl) <= 20 and re.match(r"^[a-z][a-z\s\-/]+$", bl) and len(bl) < 18:
            return f"{a}_{b.replace(' ', '_')}"
        if bl in a.lower():
            return a
        if a.lower() in bl:
            return b
        return f"{a} | {b}"

    def _row_similarity(self, row_a: List[str], row_b: List[str]) -> float:
        if not row_a or not row_b:
            return 0.0
        a_tokens = set(" ".join(row_a).lower().split())
        b_tokens = set(" ".join(row_b).lower().split())
        if not a_tokens or not b_tokens:
            return 0.0
        inter = len(a_tokens & b_tokens)
        union = len(a_tokens | b_tokens)
        return inter / union if union else 0.0

    def _remove_repeated_header_rows(
        self, data_rows: List[List[str]], header_rows: List[List[str]]
    ) -> List[List[str]]:
        if not data_rows or not header_rows:
            return data_rows
        header_ref = header_rows[-1]
        out: List[List[str]] = []
        for row in data_rows:
            if self._row_similarity(row, header_ref) >= 0.85 and self._is_header_like(row):
                self._diag["duplicate_headers_removed"] += 1
                continue
            out.append(row)
        return out

    def _infer_headers(self, rows: List[List[str]]) -> Tuple[List[TableRow], List[TableRow]]:
        if not rows:
            return [], []
        # First row always seeds column structure; extend while rows look like stacked headers.
        header_depth = 1
        for idx in range(1, min(6, len(rows))):
            if self._is_header_like(rows[idx]) or self._is_stack_header_row(rows, idx, header_depth):
                header_depth = idx + 1
            else:
                break

        detected_headers = [rows[i] for i in range(header_depth)]
        self._diag["header_rows_detected"] += len(detected_headers)
        data = rows[header_depth:]
        data = self._remove_repeated_header_rows(data, detected_headers)

        # Stacked header tiers can be ragged vs row 0 (merge/extraction); never index past row length.
        n_cols = len(rows[0])
        for hr in detected_headers:
            n_cols = max(n_cols, len(hr))
        for r in data:
            n_cols = max(n_cols, len(r))

        combined: List[str] = []
        for col in range(n_cols):
            label = ""
            for hr in detected_headers:
                cell = hr[col] if col < len(hr) else ""
                label = self._combine_header_cells(label, cell)
            cleaned = self._clean_header_cell(label)
            scrubbed = self._scrub_standards_glyph_only_cell(cleaned)
            combined.append(scrubbed or f"Column {col + 1}")

        header_rows = [TableRow(cells=combined, is_header=True)]
        data_rows: List[TableRow] = []
        for r in data:
            cells = list(r)
            if len(cells) < n_cols:
                cells.extend([""] * (n_cols - len(cells)))
            elif len(cells) > n_cols:
                cells = cells[:n_cols]
            data_rows.append(TableRow(cells=cells, is_header=False))
        return header_rows, data_rows

    def _promote_multipage_header_dups(
        self, header_rows: List[TableRow], data_rows: List[TableRow]
    ) -> Tuple[List[TableRow], List[TableRow]]:
        """Drop leading data rows that repeat the table header after multipage / continuation merge."""
        if len(header_rows) != 1 or not data_rows:
            return header_rows, data_rows
        ref = list(header_rows[0].cells)
        new_data = list(data_rows)
        while new_data:
            r = new_data[0]
            sim = self._row_similarity(r.cells, ref)
            headerish = self._is_header_like(r.cells) or (
                sim >= 0.78 and sum(1 for c in r.cells if (c or "").strip()) <= max(3, len(ref))
            )
            if headerish and sim >= 0.72:
                self._diag["duplicate_headers_removed"] += 1
                new_data.pop(0)
            else:
                break
        return header_rows, new_data

    def _column_layout_compatible_rows(
        self, rows_a: List[List[str]], rows_b: List[List[str]], max_scan: int = 6
    ) -> bool:
        if not rows_a or not rows_b:
            return False
        ca = max((len(r) for r in rows_a[:max_scan]), default=0)
        cb = max((len(r) for r in rows_b[:max_scan]), default=0)
        if ca < 2 or cb < 2:
            return False
        diff = abs(ca - cb)
        return diff <= max(2, int(0.34 * max(ca, cb)))

    def _first_row_starts_table_caption(self, rows: List[List[str]]) -> bool:
        if not rows:
            return False
        for cell in rows[0]:
            s = (cell or "").strip()
            if not s or len(s) > 400:
                continue
            if _parse_table_number_from_text(s, anchor="line_start"):
                return True
        return False

    def _merge_adjacent_body_only_continuation(self, prev: _RawTable, t: _RawTable) -> bool:
        """Next page is body-only: inherit table_number from previous numbered segment."""
        if not _merge_adjacent_unnumbered_continuation_enabled():
            return False
        if not prev.table_number:
            return False
        if t.table_number and t.table_number != prev.table_number:
            return False
        if t.page_start - prev.page_end != 1:
            return False
        if t.continuation_caption:
            return False
        if t.table_number:
            return False
        if self._first_row_starts_table_caption(t.rows):
            return False
        return self._column_layout_compatible_rows(prev.rows, t.rows)

    def _merge_continuations(self, raw_tables: List[_RawTable]) -> List[_RawTable]:
        if not raw_tables:
            return []
        raw_tables = sorted(raw_tables, key=lambda t: (t.page_start, t.bbox[1]))
        merged: List[_RawTable] = []
        by_num: Dict[str, int] = {}

        for t in raw_tables:
            num = t.table_number
            is_cont = t.continuation_caption or bool(
                t.title and self.CONTINUED_PATTERN.search(t.title)
            )
            if num and num in by_num:
                idx = by_num[num]
                prev = merged[idx]
                if t.page_start >= prev.page_end and (t.page_start - prev.page_end) <= 2:
                    merged_rows = prev.rows + t.rows
                    merged_rows = (
                        self._remove_repeated_header_rows(merged_rows[1:], [merged_rows[0]])
                        if merged_rows
                        else merged_rows
                    )
                    if merged_rows:
                        merged_rows = [prev.rows[0]] + merged_rows
                    merged[idx] = _RawTable(
                        page_start=prev.page_start,
                        page_end=max(prev.page_end, t.page_end),
                        bbox=prev.bbox,
                        rows=merged_rows,
                        table_number=num,
                        title=prev.title or t.title,
                        source_method=prev.source_method,
                        continuation_caption=prev.continuation_caption or t.continuation_caption,
                    )
                    continue
            elif is_cont and merged:
                prev = merged[-1]
                merged_rows = prev.rows + t.rows
                merged_rows = (
                    self._remove_repeated_header_rows(merged_rows[1:], [merged_rows[0]])
                    if merged_rows
                    else merged_rows
                )
                if merged_rows:
                    merged_rows = [prev.rows[0]] + merged_rows
                merged[-1] = _RawTable(
                    page_start=prev.page_start,
                    page_end=max(prev.page_end, t.page_end),
                    bbox=prev.bbox,
                    rows=merged_rows,
                    table_number=prev.table_number or t.table_number,
                    title=prev.title or t.title,
                    source_method=prev.source_method,
                    continuation_caption=prev.continuation_caption or t.continuation_caption,
                )
                continue
            elif merged:
                prev = merged[-1]
                if (
                    (t.page_start - prev.page_end) <= 1
                    and self._header_similarity(prev.rows, t.rows) >= 0.8
                    and (
                        prev.table_number == t.table_number
                        or not prev.table_number
                        or not t.table_number
                    )
                ):
                    merged_rows = prev.rows + t.rows
                    merged_rows = (
                        self._remove_repeated_header_rows(merged_rows[1:], [merged_rows[0]])
                        if merged_rows
                        else merged_rows
                    )
                    if merged_rows:
                        merged_rows = [prev.rows[0]] + merged_rows
                    merged[-1] = _RawTable(
                        page_start=prev.page_start,
                        page_end=max(prev.page_end, t.page_end),
                        bbox=prev.bbox,
                        rows=merged_rows,
                        table_number=prev.table_number or t.table_number,
                        title=prev.title or t.title,
                        source_method=prev.source_method,
                        continuation_caption=prev.continuation_caption or t.continuation_caption,
                    )
                    continue
                if self._merge_adjacent_body_only_continuation(prev, t):
                    merged_rows = prev.rows + t.rows
                    merged_rows = (
                        self._remove_repeated_header_rows(merged_rows[1:], [merged_rows[0]])
                        if merged_rows
                        else merged_rows
                    )
                    if merged_rows:
                        merged_rows = [prev.rows[0]] + merged_rows
                    merged[-1] = _RawTable(
                        page_start=prev.page_start,
                        page_end=max(prev.page_end, t.page_end),
                        bbox=prev.bbox,
                        rows=merged_rows,
                        table_number=prev.table_number,
                        title=prev.title or t.title,
                        source_method=prev.source_method,
                        continuation_caption=prev.continuation_caption,
                    )
                    self._diag["continuation_body_merges"] += 1
                    continue

            merged.append(t)
            if num:
                by_num[num] = len(merged) - 1
        return merged

    def _header_similarity(self, rows_a: List[List[str]], rows_b: List[List[str]]) -> float:
        if not rows_a or not rows_b:
            return 0.0
        a = " | ".join((c or "").strip().lower() for c in rows_a[0])
        b = " | ".join((c or "").strip().lower() for c in rows_b[0])
        if not a or not b:
            return 0.0
        a_tokens = set(a.split())
        b_tokens = set(b.split())
        if not a_tokens or not b_tokens:
            return 0.0
        inter = len(a_tokens & b_tokens)
        union = len(a_tokens | b_tokens)
        return inter / union if union else 0.0

    def _table_shape_metrics(self, table: Table) -> Tuple[int, int, float]:
        headers = table.header_rows or []
        data = table.data_rows or []
        col_count = len(headers[0].cells) if headers else (len(data[0].cells) if data else 0)
        multiline = 0
        filled = 0
        for row in data:
            for cell in row.cells:
                s = (cell or "").strip()
                if not s:
                    continue
                filled += 1
                if "\n" in s:
                    multiline += 1
        multiline_ratio = (multiline / filled) if filled else 0.0
        return col_count, len(data), multiline_ratio

    def _quality_components_header_only(
        self, table: Table, headers: List[TableRow]
    ) -> _QualityComponents:
        """Score tables with no body rows using header cells only (correct col_count / ratios)."""
        if not headers:
            return _QualityComponents(
                0.0,
                0,
                0,
                1.0,
                0.0,
                0.0,
                0,
                1.0,
                -1.0,
                True,
                True,
                1.0,
                1.0,
                1.0,
                1.0,
                1.0,
                1.0,
                True,
            )
        col_count = len(headers[0].cells)
        all_cell_rows: List[List[str]] = [list(hr.cells) for hr in headers]
        total_cells = sum(len(r) for r in all_cell_rows) or 1

        meaningful = 0
        placeholders = 0
        garbage_cells = 0
        symbol_junk_cells = 0
        mojibake_cells = 0
        unique_cells = set()
        noise_cells = 0
        multiline_cells = 0

        for row in all_cell_rows:
            for c in row:
                cell = (c or "").strip()
                if self._is_placeholder_text(cell):
                    placeholders += 1
                    continue
                if not cell:
                    continue
                meaningful += 1
                unique_cells.add(cell.lower())
                if "\n" in cell:
                    multiline_cells += 1
                if self.NOISE_TOKEN_PATTERN.search(cell):
                    noise_cells += 1
                if self._cell_is_garbage(cell):
                    garbage_cells += 1
                if self._cell_symbol_junk(cell):
                    symbol_junk_cells += 1
                if self._cell_ocr_digit_mojibake(cell):
                    mojibake_cells += 1
                    if not self._cell_symbol_junk(cell):
                        symbol_junk_cells += 1

        fill_ratio = (meaningful / total_cells) if total_cells else 0.0
        placeholder_ratio = (placeholders / total_cells) if total_cells else 0.0
        garbage_cell_ratio = (garbage_cells / meaningful) if meaningful else 0.0
        symbol_junk_ratio = (symbol_junk_cells / meaningful) if meaningful else 0.0
        ocr_mojibake_ratio = (mojibake_cells / meaningful) if meaningful else 0.0
        diversity = (len(unique_cells) / meaningful) if meaningful else 0.0
        noise_ratio = (noise_cells / meaningful) if meaningful else 0.0
        multiline_ratio = (multiline_cells / meaningful) if meaningful else 0.0

        header_corrupt_ratio = 0.0
        hn = 0
        h_bad = 0
        for c in headers[0].cells:
            cell = (c or "").strip()
            if not cell:
                continue
            hn += 1
            if (
                self._cell_is_garbage(cell)
                or self._cell_symbol_junk(cell)
                or (self.NOISE_TOKEN_PATTERN.search(cell) and len(cell) < 30)
            ):
                h_bad += 1
        header_corrupt_ratio = (h_bad / hn) if hn else 0.0

        penalty = 0.72
        if table.table_number is None:
            penalty += 0.08
        if placeholder_ratio > 0.05:
            penalty += min(0.35, placeholder_ratio * 1.0)
        if garbage_cell_ratio > 0.08:
            penalty += min(0.3, garbage_cell_ratio * 0.8)
        if symbol_junk_ratio > 0.06:
            penalty += min(0.28, symbol_junk_ratio * 0.9)
        if ocr_mojibake_ratio > 0.02:
            penalty += min(0.3, ocr_mojibake_ratio * 1.5)
        if header_corrupt_ratio > 0.06:
            penalty += min(0.25, header_corrupt_ratio * 0.7)
        if noise_ratio > 0.1:
            penalty += min(0.2, noise_ratio * 0.5)

        semantic_hard_fail = True
        score = max(-1.0, min(1.0, fill_ratio - penalty))
        return _QualityComponents(
            fill_ratio,
            col_count,
            0,
            noise_ratio,
            multiline_ratio,
            diversity,
            0,
            penalty,
            score,
            False,
            True,
            placeholder_ratio,
            garbage_cell_ratio,
            symbol_junk_ratio,
            ocr_mojibake_ratio,
            header_corrupt_ratio,
            0.0,
            semantic_hard_fail,
        )

    def _quality_components(self, table: Table) -> _QualityComponents:
        headers = table.header_rows or []
        data = table.data_rows or []
        if not data:
            return self._quality_components_header_only(table, headers)

        col_count = len(headers[0].cells) if headers else (len(data[0].cells) if data else 0)
        all_cell_rows: List[List[str]] = [list(hr.cells) for hr in headers] + [list(r.cells) for r in data]
        total_cells = sum(len(r) for r in all_cell_rows)

        meaningful = 0
        placeholders = 0
        garbage_cells = 0
        symbol_junk_cells = 0
        mojibake_cells = 0
        unique_cells = set()
        noise_cells = 0
        multiline_cells = 0
        repeated_header_rows = 0
        header_ref = headers[0].cells if headers else []

        for r in data:
            if header_ref and self._row_similarity(r.cells, header_ref) >= 0.85 and self._is_header_like(
                r.cells
            ):
                repeated_header_rows += 1

        for row in all_cell_rows:
            for c in row:
                cell = (c or "").strip()
                if self._is_placeholder_text(cell):
                    placeholders += 1
                    continue
                if not cell:
                    continue
                meaningful += 1
                unique_cells.add(cell.lower())
                if "\n" in cell:
                    multiline_cells += 1
                if self.NOISE_TOKEN_PATTERN.search(cell):
                    noise_cells += 1
                if self._cell_is_garbage(cell):
                    garbage_cells += 1
                if self._cell_symbol_junk(cell):
                    symbol_junk_cells += 1
                if self._cell_ocr_digit_mojibake(cell):
                    mojibake_cells += 1
                    if not self._cell_symbol_junk(cell):
                        symbol_junk_cells += 1

        fill_ratio = (meaningful / total_cells) if total_cells else 0.0
        placeholder_ratio = (placeholders / total_cells) if total_cells else 0.0
        garbage_cell_ratio = (garbage_cells / meaningful) if meaningful else 0.0
        symbol_junk_ratio = (symbol_junk_cells / meaningful) if meaningful else 0.0
        ocr_mojibake_ratio = (mojibake_cells / meaningful) if meaningful else 0.0
        diversity = (len(unique_cells) / meaningful) if meaningful else 0.0
        noise_ratio = (noise_cells / meaningful) if meaningful else 0.0
        multiline_ratio = (multiline_cells / meaningful) if meaningful else 0.0

        header_corrupt_ratio = 0.0
        if headers:
            hn = 0
            h_bad = 0
            for c in headers[0].cells:
                cell = (c or "").strip()
                if not cell:
                    continue
                hn += 1
                if (
                    self._cell_is_garbage(cell)
                    or self._cell_symbol_junk(cell)
                    or (self.NOISE_TOKEN_PATTERN.search(cell) and len(cell) < 30)
                ):
                    h_bad += 1
            header_corrupt_ratio = (h_bad / hn) if hn else 0.0

        data_row_repeat_ratio = 0.0
        if len(data) >= 4:
            keys = ["|".join(x.strip().lower() for x in r.cells) for r in data]
            mc = Counter(keys).most_common(1)[0][1]
            data_row_repeat_ratio = mc / len(keys)

        penalty = 0.0
        if col_count <= 1:
            penalty += 0.38
        if table.table_number is None:
            penalty += 0.14
            if col_count <= 3:
                penalty += 0.08
        if placeholder_ratio > 0.05:
            penalty += min(0.55, 0.12 + placeholder_ratio * 1.2)
        if garbage_cell_ratio > 0.08:
            penalty += min(0.48, 0.1 + garbage_cell_ratio * 1.0)
        if symbol_junk_ratio > 0.06:
            penalty += min(0.42, 0.1 + symbol_junk_ratio * 1.1)
        if ocr_mojibake_ratio > 0.025:
            penalty += min(0.45, 0.14 + ocr_mojibake_ratio * 2.0)
        if header_corrupt_ratio > 0.08:
            penalty += min(0.38, 0.08 + header_corrupt_ratio * 0.9)
        if data_row_repeat_ratio > 0.52 and col_count <= 3 and len(data) >= 5:
            penalty += min(0.35, 0.12 + (data_row_repeat_ratio - 0.52))

        long_cells = 0
        for r in data:
            for c in r.cells:
                s = (c or "").strip()
                if self._is_placeholder_text(s):
                    continue
                if len(s) > 45:
                    long_cells += 1
        one_column_value_list = col_count == 1 and len(data) >= 5 and long_cells >= max(3, len(data) // 2)
        if one_column_value_list:
            penalty += 0.28

        partial_fragment = (
            len(data) < 4 and col_count >= 4 and fill_ratio < 0.38 and fill_ratio > 0
        ) or (len(data) <= 2 and col_count >= 3)
        if partial_fragment:
            penalty += 0.22

        if repeated_header_rows:
            penalty += min(0.3, 0.12 * repeated_header_rows)
        if meaningful and diversity < 0.32:
            penalty += 0.18
        if noise_ratio > 0.12:
            penalty += min(0.35, 0.15 + noise_ratio)
        if col_count == 1 and multiline_ratio > 0.38:
            penalty += 0.18
        if col_count <= 2 and multiline_ratio > 0.42:
            penalty += 0.18
        if col_count == 2 and len(data) >= 5 and data_row_repeat_ratio > 0.62:
            penalty += 0.16

        tiny_single_data_row = len(data) == 1 and col_count >= 1
        if tiny_single_data_row:
            penalty += 0.2
            if table.table_number is None:
                penalty += 0.14
            if tiny_single_data_row and col_count >= 4 and fill_ratio < 0.55:
                penalty += 0.1

        semantic_hard_fail = (
            garbage_cell_ratio > 0.12
            or placeholder_ratio > 0.16
            or symbol_junk_ratio > 0.14
            or ocr_mojibake_ratio > 0.048
            or header_corrupt_ratio > 0.26
            or (data_row_repeat_ratio >= 0.68 and col_count <= 3 and len(data) >= 5)
            or (
                len(data) == 1
                and col_count >= 4
                and (
                    header_corrupt_ratio > 0.1
                    or noise_ratio > 0.24
                    or garbage_cell_ratio > 0.08
                )
            )
            or (
                table.table_number is None
                and len(data) == 1
                and col_count >= 3
                and (noise_ratio > 0.22 or placeholder_ratio > 0.06)
            )
            or (
                col_count >= 3
                and len(data) <= 2
                and header_corrupt_ratio > 0.18
                and noise_ratio > 0.18
            )
        )
        if semantic_hard_fail:
            penalty += 0.25

        score = max(-1.0, min(1.0, fill_ratio - penalty))
        return _QualityComponents(
            fill_ratio,
            col_count,
            len(data),
            noise_ratio,
            multiline_ratio,
            diversity,
            repeated_header_rows,
            penalty,
            score,
            one_column_value_list,
            partial_fragment,
            placeholder_ratio,
            garbage_cell_ratio,
            symbol_junk_ratio,
            ocr_mojibake_ratio,
            header_corrupt_ratio,
            data_row_repeat_ratio,
            semantic_hard_fail,
        )

    def _confidence_from_components(self, q: _QualityComponents, table: Table) -> ConfidenceLevel:
        if q.row_count == 0:
            return ConfidenceLevel.LOW
        if q.semantic_hard_fail:
            return ConfidenceLevel.LOW
        unnumbered = table.table_number is None
        if unnumbered and q.ocr_mojibake_ratio > 0.02:
            return ConfidenceLevel.LOW
        if unnumbered and q.col_count <= 2 and q.row_count >= 10 and q.score < 0.82:
            return ConfidenceLevel.LOW
        if unnumbered and q.score < 0.48 and q.col_count <= 3:
            return ConfidenceLevel.LOW
        block_high = (
            unnumbered
            or q.placeholder_ratio > 0.042
            or q.garbage_cell_ratio > 0.065
            or q.symbol_junk_ratio > 0.042
            or q.ocr_mojibake_ratio > 0.018
            or q.header_corrupt_ratio > 0.075
            or q.fill_ratio < 0.42
            or (q.data_row_repeat_ratio > 0.55 and q.col_count <= 3 and q.row_count >= 5)
            or (q.col_count == 2 and q.data_row_repeat_ratio > 0.62 and q.row_count >= 5)
        )
        if (
            not block_high
            and q.score >= 0.7
            and q.row_count >= 3
            and q.col_count >= 2
            and q.multiline_ratio < 0.32
            and q.noise_ratio < 0.095
            and q.repeated_header_rows == 0
            and not q.one_column_value_list
            and not q.partial_fragment
        ):
            return ConfidenceLevel.HIGH
        if q.score >= 0.28 and q.col_count >= 1:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW

    def _should_trigger_image_recovery(
        self, raw: _RawTable, table: Table, q: _QualityComponents
    ) -> bool:
        """Iteration 3: More aggressive OCR triggering for image-based tables."""
        if raw.page_start != raw.page_end:
            return False
        col_count, row_count, multiline_ratio = self._table_shape_metrics(table)
        conf = str(table.confidence).lower()
        
        # Iteration 3: Lowered thresholds to trigger OCR more readily
        if q.score < 0.55 and row_count >= 2:  # Was 0.48
            return True
        if conf in {"low", "medium"} and row_count >= 2 and q.score < 0.62:  # Was 0.55
            return True
        if col_count <= 2 and multiline_ratio > 0.28:  # Was 0.32
            return True
        if col_count == 1 and table.table_number is not None and row_count >= 3:
            return True
        # Iteration 3: Trigger OCR for tables with very few rows (likely incomplete extraction)
        if row_count <= 2 and table.table_number is not None:
            return True
        # Iteration 3: Trigger OCR for tables with high noise ratio
        if q.noise_ratio > 0.25 and row_count >= 2:
            return True
        # Iteration 3: Trigger OCR for tables with low fill ratio
        if q.fill_ratio < 0.30 and row_count >= 2 and col_count >= 2:
            return True
        return False

    def _is_structurally_better(
        self,
        candidate: Table,
        cq: _QualityComponents,
        baseline: Table,
        bq: _QualityComponents,
    ) -> bool:
        c_cols, c_rows, c_multi = self._table_shape_metrics(candidate)
        b_cols, b_rows, b_multi = self._table_shape_metrics(baseline)
        if cq.score > bq.score + 0.03:
            return True
        if c_cols > b_cols and c_rows >= max(1, b_rows // 2):
            return True
        if str(candidate.confidence).lower() != "low" and str(baseline.confidence).lower() == "low":
            return cq.score >= bq.score - 0.05
        if c_cols == b_cols and c_rows >= b_rows and c_multi + 0.1 < b_multi:
            return True
        return False

    def _recover_table_from_image(self, source_pdf_path: str, raw: _RawTable) -> Optional[_RawTable]:
        """Iteration 3: Enhanced OCR with multiple PSM modes and higher resolution."""
        try:
            import pdfplumber
            import pytesseract
        except Exception:
            return None
        
        # Iteration 3: Try multiple Tesseract PSM (Page Segmentation Mode) strategies
        psm_modes = [
            ("6", "Assume uniform text block"),  # Original default
            ("4", "Assume single column of variable sizes"),
            ("3", "Fully automatic page segmentation"),
            ("1", "Automatic with OSD (Orientation and Script Detection)"),
        ]
        
        best_result = None
        best_score = 0
        
        for psm, description in psm_modes:
            try:
                with pdfplumber.open(source_pdf_path) as pdf:
                    page = pdf.pages[raw.page_start - 1]
                    crop = page.crop(raw.bbox)
                    # Iteration 3: Increased resolution from 250 to 300 for better OCR quality
                    img = crop.to_image(resolution=300).original
                    ocr_text = pytesseract.image_to_string(img, config=f"--psm {psm}")
            except Exception as e:
                logger.debug(f"OCR failed with PSM {psm}: {e}")
                continue
            
            rows = self._rows_from_ocr_text(ocr_text)
            norm_rows = self._normalize_rows(rows)  # type: ignore[arg-type]
            
            if len(norm_rows) < 2:
                continue
            
            # Score this OCR result based on row count, column consistency, and content quality
            score = self._score_ocr_result(norm_rows)
            
            if score > best_score:
                best_score = score
                best_result = _RawTable(
                    page_start=raw.page_start,
                    page_end=raw.page_end,
                    bbox=raw.bbox,
                    rows=norm_rows,
                    table_number=raw.table_number,
                    title=raw.title,
                    source_method=f"{raw.source_method}+image_ocr_psm{psm}",
                    continuation_caption=raw.continuation_caption,
                )
                logger.debug(
                    f"OCR PSM {psm} ({description}): {len(norm_rows)} rows, score={score:.2f}"
                )
        
        return best_result
    
    def _score_ocr_result(self, rows: List[List[str]]) -> float:
        """Iteration 3: Score OCR results to pick the best PSM mode."""
        if not rows:
            return 0.0
        
        score = 0.0
        
        # More rows is better (up to a point)
        row_count = len(rows)
        score += min(20, row_count) * 0.5
        
        # Column consistency is good (all rows have similar column counts)
        col_counts = [len(r) for r in rows]
        if col_counts:
            avg_cols = sum(col_counts) / len(col_counts)
            col_variance = sum((c - avg_cols) ** 2 for c in col_counts) / len(col_counts)
            if col_variance < 2.0:  # Low variance means consistent structure
                score += 5.0
            elif col_variance < 5.0:
                score += 2.0
        
        # Non-empty cells are good
        all_cells = [cell for row in rows for cell in row]
        non_empty = sum(1 for c in all_cells if c.strip())
        if all_cells:
            fill_ratio = non_empty / len(all_cells)
            score += fill_ratio * 10.0
        
        # Penalize noise artifacts
        noise_count = sum(1 for row in rows if self._row_is_noise_artifact(row))
        noise_ratio = noise_count / len(rows) if rows else 0
        score -= noise_ratio * 8.0
        
        return max(0.0, score)

    def _rows_from_ocr_text(self, text: str) -> List[List[str]]:
        """Iteration 3: Enhanced OCR text parsing with better delimiter detection."""
        rows: List[List[str]] = []
        if not text:
            return rows
        
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            
            # Iteration 3: Try multiple splitting strategies
            # Strategy 1: Split on multiple spaces (2+)
            cells = [
                self._normalize_scalar_to_str(c)
                for c in re.split(r"\s{2,}", s)
                if c.strip()
            ]
            
            # Strategy 2: If single column detected, try tab splitting
            if len(cells) == 1 and "\t" in s:
                cells = [
                    self._normalize_scalar_to_str(c)
                    for c in s.split("\t")
                    if c.strip()
                ]
            
            # Strategy 3: If still single column, try pipe delimiter
            if len(cells) == 1 and "|" in s:
                cells = [
                    self._normalize_scalar_to_str(c)
                    for c in s.split("|")
                    if c.strip()
                ]
            
            if cells and not self._row_is_noise_artifact(cells):
                rows.append(cells)
        
        return rows

    def _csv(self, rows: List[TableRow]) -> Optional[str]:
        if not rows:
            return None
        out = StringIO()
        writer = csv.writer(out)
        for r in rows:
            writer.writerow(r.cells)
        return out.getvalue()

    def _normalized_text(
        self,
        table_number: Optional[str],
        title: Optional[str],
        headers: List[TableRow],
        data: List[TableRow],
    ) -> str:
        lines: List[str] = []
        if table_number:
            lines.append(f"TABLE {table_number}")
        clean_title = self._clean_title(title)
        if clean_title:
            lines.append(f"TITLE: {clean_title}")
        if headers:
            lines.append("COLUMNS: " + " | ".join(headers[0].cells))
        for i, row in enumerate(data, start=1):
            lines.append(f"ROW {i}: " + " | ".join(row.cells))
        return "\n".join(lines).strip()

    def _clean_title(self, title: Optional[str]) -> Optional[str]:
        if not title:
            return None
        t = re.sub(r"\s+", " ", title).strip()
        if self.CONTINUED_PATTERN.search(t) and len(t) < 42:
            rem = re.sub(r"(?i)\bcontinued\b", "", t)
            rem = re.sub(r"^[\s.,;:()\-]+|[\s.,;:()\-]+$", "", rem).strip()
            if not rem:
                return None
            t = rem
        t = re.sub(r"\.{3,}\s*\d*\s*$", "", t).strip()
        if not t or self.NOISY_TITLE_PATTERN.match(t):
            return None
        return t

    def _link_parent_clause(self, raw: _RawTable, clauses: List[Any]) -> Optional[str]:
        if not clauses:
            return None
        if raw.table_number:
            pattern = re.compile(rf"\btable\s+{re.escape(raw.table_number)}\b", re.IGNORECASE)
            nearby = [c for c in clauses if abs(int(getattr(c, "page_start", 1)) - raw.page_start) <= 2]
            for c in nearby:
                body = getattr(c, "body_with_subitems", "") or ""
                if pattern.search(body):
                    return getattr(c, "clause_number", None)
            # Do not fall back to "nearest preceding clause" when we already have a table id;
            # that mis-attaches clause numbers that only sit near the table on the page.
            return None
        preceding = [c for c in clauses if int(getattr(c, "page_start", 1)) <= raw.page_start]
        if not preceding:
            return None
        preceding.sort(
            key=lambda c: (
                int(getattr(c, "page_start", 1)),
                str(getattr(c, "clause_number", "")).count("."),
            ),
            reverse=True,
        )
        return getattr(preceding[0], "clause_number", None)

    def _scrub_layout_only_data_cells(self, cells: List[str]) -> List[str]:
        """Blank PDF rule-drawing artifacts in body cells (not letter grades like A/B)."""
        out: List[str] = []
        for c in cells:
            s = (c or "").strip()
            if re.fullmatch(r"~+", s):
                out.append("")
                continue
            parts = s.split()
            if parts and all(re.fullmatch(r"~+", p) for p in parts):
                out.append("")
                continue
            if re.fullmatch(r"[\-–—_\.]{1,8}", s):
                out.append("")
                continue
            if re.fullmatch(r"I{1,4}", s, re.I) and len(s) <= 4:
                out.append("")
                continue
            if re.fullmatch(r"[\s~I]{1,8}", s):
                out.append("")
                continue
            out.append(c)
        return out

    def _to_table_model(self, raw: _RawTable, clauses: List[Any]) -> Table:
        headers, data = self._infer_headers(raw.rows)
        if raw.page_end > raw.page_start or raw.continuation_caption:
            headers, data = self._promote_multipage_header_dups(headers, data)
        data = [
            TableRow(
                cells=self._scrub_layout_only_data_cells(list(r.cells)),
                is_header=False,
            )
            for r in data
        ]
        csv_text = self._csv(headers + data)
        clean_title = self._clean_title(raw.title)
        norm = self._normalized_text(raw.table_number, raw.title, headers, data)
        tid = f"table_{uuid.uuid4().hex[:8]}"
        t = Table(
            table_id=tid,
            table_number=raw.table_number,
            title=clean_title,
            parent_clause_reference=self._link_parent_clause(raw, clauses),
            page_start=raw.page_start,
            page_end=raw.page_end,
            header_rows=headers,
            data_rows=data,
            footer_notes=[],
            raw_csv=csv_text,
            normalized_text_representation=norm,
            confidence=ConfidenceLevel.MEDIUM,
            has_headers=bool(headers),
            is_multipage=raw.page_end > raw.page_start,
            has_merged_cells=True,
        )
        conf = self._confidence_from_components(self._quality_components(t), t)
        return t.model_copy(update={"confidence": conf})
