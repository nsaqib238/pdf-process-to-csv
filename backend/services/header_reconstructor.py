"""
Universal table header reconstruction (structure-first, domain-agnostic).

Post-processes extracted Table JSON: promotes leaked headers, cleans cells,
builds final flat column names and debug metadata. See TABLE_HEADER RECONSTRUCT.md.
"""
from __future__ import annotations

import copy
import csv
import logging
import re
from io import StringIO
from typing import Any, Dict, List, Optional, Set, Tuple

from models.table import Table

logger = logging.getLogger(__name__)


# --- GENERIC CONFIG ---

GENERIC_HEADER_HINTS: Set[str] = {
    "type", "class", "category", "description", "material", "materials",
    "size", "sizes", "rating", "ratings", "length", "width", "height",
    "minimum", "maximum", "limit", "limits", "surface", "treatment",
    "dimensions", "requirement", "requirements", "group", "condition",
    "conditions", "use", "application", "zone", "zones", "range",
    "nominal", "current", "temperature", "voltage", "load", "capacity",
    "performance", "classification", "protective", "device", "devices",
}

GENERIC_UNIT_HINTS: Set[str] = {
    "mm", "mm2", "m", "m2", "a", "amp", "amps", "%", "°c", "c",
    "v", "va", "kw", "w", "hz", "ms", "s",
}

GENERIC_CATEGORY_WORDS: Set[str] = {
    "yes", "no", "not", "permitted", "allowed", "prohibited",
    "metallic", "non-metallic", "single", "three", "phase",
    "class", "type", "group", "zone", "active", "earth", "neutral",
}

PLACEHOLDER_HEADER_NAMES = {
    "column 1", "column1", "col 1", "col1", "column", "stub",
}

JUNK_FRAGMENT_PATTERNS = [
    r"^[~|_]+$",
    r"^[^\w\s]+$",
    r"^[Il1|]{1,3}$",
]

COMMON_OCR_JUNK = {
    "~ ~", "i i", "i_i", "l l", "go•c", "r•h•", "rph•", "phasel3", "zint",
}

TABLE_TYPE_MATRIX = "matrix"
TABLE_TYPE_NUMERIC_LOOKUP = "numeric_lookup"
TABLE_TYPE_PROPERTY = "property"
TABLE_TYPE_UNKNOWN = "unknown"


def reconstruct_headers(table_obj: Dict[str, Any]) -> Dict[str, Any]:
    table = copy.deepcopy(table_obj)

    raw_header_rows = normalize_rows(table.get("header_rows", []) or [])
    raw_data_rows = normalize_rows(table.get("data_rows", []) or [])

    detected_header_rows, remaining_data_rows, row_debug = detect_header_rows(
        raw_header_rows, raw_data_rows
    )

    cleaned_header_rows, clean_debug = clean_header_rows(detected_header_rows)

    remaining_data_rows, body_debug = remove_body_rows_that_still_look_like_headers(
        remaining_data_rows, cleaned_header_rows
    )

    target_n_cols = infer_column_width(cleaned_header_rows, remaining_data_rows)

    table_type = classify_table_type(cleaned_header_rows, remaining_data_rows)
    stub_column_index = detect_stub_column(cleaned_header_rows, remaining_data_rows)

    header_tree = build_header_tree(
        cleaned_header_rows=cleaned_header_rows,
        data_rows=remaining_data_rows,
        stub_column_index=stub_column_index,
        table_type=table_type,
    )

    pre_flat = flatten_header_tree(header_tree)
    final_columns = align_final_columns_to_width(pre_flat, target_n_cols)

    reconstruction_confidence = score_reconstruction_confidence(
        cleaned_header_rows=cleaned_header_rows,
        cleaned_body_rows=remaining_data_rows,
        final_columns=final_columns,
        table_type=table_type,
    )

    table["reconstructed_header_rows"] = cleaned_header_rows
    table["promoted_header_rows"] = [
        r for r in detected_header_rows[len(raw_header_rows) :]
    ]
    table["data_rows"] = remaining_data_rows
    table["final_columns"] = final_columns
    table["reconstruction_confidence"] = reconstruction_confidence
    table["reconstruction_notes"] = build_reconstruction_notes(
        row_debug=row_debug,
        clean_debug=clean_debug,
        body_debug=body_debug,
        truncated=len(pre_flat) > target_n_cols and target_n_cols > 0,
    )
    table["header_model"] = {
        "table_type": table_type,
        "stub_column_index": stub_column_index,
        "raw_header_row_count": len(raw_header_rows),
        "reconstructed_header_row_count": len(cleaned_header_rows),
        "final_column_count": len(final_columns),
        "header_tree": header_tree,
        "row_debug": row_debug,
        "clean_debug": clean_debug,
        "body_debug": body_debug,
    }

    return table


def reconstruct_headers_for_tables(tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for table in tables:
        try:
            output.append(reconstruct_headers(table))
        except Exception as exc:
            failed = copy.deepcopy(table)
            failed["reconstruction_confidence"] = "low"
            notes = failed.get("reconstruction_notes")
            if not isinstance(notes, list):
                notes = []
            notes.append(
                f"header reconstruction failed: {type(exc).__name__}: {str(exc)}"
            )
            failed["reconstruction_notes"] = notes
            output.append(failed)
    return output


def apply_reconstruction_to_tables(tables: List[Table]) -> List[Table]:
    """Run reconstruction and map back to Table models (updates norm text + raw_csv)."""
    out: List[Table] = []
    for t in tables:
        try:
            raw = t.model_dump(mode="json")
            merged = reconstruct_headers(raw)
            merged["normalized_text_representation"] = rebuild_normalized_text_representation(
                merged
            )
            merged["raw_csv"] = rebuild_raw_csv(merged)
            out.append(Table.model_validate(merged))
        except Exception as exc:
            logger.warning(
                "Header reconstruction skipped for table %s: %s",
                getattr(t, "table_id", "?"),
                exc,
                exc_info=logger.isEnabledFor(logging.DEBUG),
            )
            out.append(t)
    return out


def infer_column_width(
    header_rows: List[Dict[str, Any]], data_rows: List[Dict[str, Any]]
) -> int:
    w = 0
    for r in header_rows:
        w = max(w, len(r.get("cells", []) or []))
    for r in data_rows:
        w = max(w, len(r.get("cells", []) or []))
    return max(w, 1)


def align_final_columns_to_width(final_columns: List[str], n: int) -> List[str]:
    if n <= 0:
        return list(final_columns)
    fc = list(final_columns)
    if len(fc) == n:
        return fc
    if len(fc) > n:
        return fc[:n]
    for i in range(len(fc), n):
        fc.append(f"Column {i + 1}")
    return fc


def rebuild_normalized_text_representation(t: Dict[str, Any]) -> str:
    lines: List[str] = []
    num = t.get("table_number")
    if num:
        lines.append(f"TABLE {num}")
    title = t.get("title")
    if title:
        lines.append(f"TITLE: {title}")
    cols = t.get("final_columns")
    if not cols and t.get("header_rows"):
        hr0 = t["header_rows"][0]
        if isinstance(hr0, dict):
            cols = hr0.get("cells", [])
        else:
            cols = getattr(hr0, "cells", None)
    if cols:
        lines.append("COLUMNS: " + " | ".join(str(c) for c in cols))
    for i, row in enumerate(t.get("data_rows") or [], start=1):
        cells = row["cells"] if isinstance(row, dict) else row.cells
        lines.append(f"ROW {i}: " + " | ".join(str(c) for c in cells))
    return "\n".join(lines).strip()


def rebuild_raw_csv(t: Dict[str, Any]) -> Optional[str]:
    buf = StringIO()
    w = csv.writer(buf)
    cols = t.get("final_columns")
    if not cols and t.get("header_rows"):
        hr0 = t["header_rows"][0]
        if isinstance(hr0, dict):
            cols = hr0.get("cells", [])
        else:
            cols = list(getattr(hr0, "cells", []) or [])
    if cols:
        w.writerow(list(cols))
    for row in t.get("data_rows") or []:
        cells = row["cells"] if isinstance(row, dict) else row.cells
        w.writerow(list(cells))
    s = buf.getvalue()
    return s if s.strip() else t.get("raw_csv")


# --- NORMALIZATION ---


def normalize_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for row in rows:
        cells = row.get("cells", []) if isinstance(row, dict) else []
        normalized.append(
            {
                "cells": [normalize_cell_text(c) for c in cells],
                "is_header": bool(row.get("is_header", False))
                if isinstance(row, dict)
                else False,
            }
        )
    return normalized


def normalize_cell_text(text: Any) -> str:
    if text is None:
        return ""
    text = str(text)
    text = text.replace("\xa0", " ")
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


# --- HEADER DETECTION ---


def detect_header_rows(
    header_rows: List[Dict[str, Any]],
    data_rows: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    detected_header_rows: List[Dict[str, Any]] = []
    remaining_data_rows: List[Dict[str, Any]] = []
    row_debug: List[Dict[str, Any]] = []

    for idx, row in enumerate(header_rows):
        score_info = analyze_row(row["cells"])
        row_debug.append(
            {
                "source": "header_rows",
                "row_index": idx,
                "cells": row["cells"],
                "analysis": score_info,
            }
        )
        detected_header_rows.append({"cells": row["cells"], "is_header": True})

    for idx, row in enumerate(data_rows):
        score_info = analyze_row(row["cells"])
        similarity = max_similarity_to_rows(row["cells"], detected_header_rows)
        row_debug.append(
            {
                "source": "data_rows",
                "row_index": idx,
                "cells": row["cells"],
                "analysis": score_info,
                "max_header_similarity": similarity,
            }
        )
        if should_promote_body_row_to_header(score_info, similarity, row["cells"]):
            detected_header_rows.append({"cells": row["cells"], "is_header": True})
        else:
            remaining_data_rows.append(row)

    return detected_header_rows, remaining_data_rows, row_debug


def analyze_row(cells: List[str]) -> Dict[str, Any]:
    text_tokens = 0
    numeric_tokens = 0
    header_hint_hits = 0
    unit_hits = 0
    category_hits = 0
    multiline_cells = 0
    junk_hits = 0

    for cell in cells:
        if "\n" in cell:
            multiline_cells += 1
        tokens = tokenize(cell)
        for token in tokens:
            tl = token.lower()
            if is_numberish(tl):
                numeric_tokens += 1
            else:
                text_tokens += 1
            if tl in GENERIC_HEADER_HINTS:
                header_hint_hits += 1
            if tl in GENERIC_UNIT_HINTS:
                unit_hits += 1
            if tl in GENERIC_CATEGORY_WORDS:
                category_hits += 1
            if is_junk_token(tl):
                junk_hits += 1

    total = max(text_tokens + numeric_tokens, 1)
    text_ratio = text_tokens / total
    numeric_ratio = numeric_tokens / total
    multiline_ratio = multiline_cells / max(len(cells), 1)

    score = (
        0.32 * text_ratio
        + 0.20 * min(header_hint_hits / 4.0, 1.0)
        + 0.12 * min(unit_hits / 3.0, 1.0)
        + 0.12 * min(category_hits / 3.0, 1.0)
        + 0.10 * multiline_ratio
        - 0.18 * numeric_ratio
        - 0.15 * min(junk_hits / 3.0, 1.0)
    )

    return {
        "score": round(score, 4),
        "text_ratio": round(text_ratio, 4),
        "numeric_ratio": round(numeric_ratio, 4),
        "header_hint_hits": header_hint_hits,
        "unit_hits": unit_hits,
        "category_hits": category_hits,
        "multiline_ratio": round(multiline_ratio, 4),
        "junk_hits": junk_hits,
    }


def should_promote_body_row_to_header(
    score_info: Dict[str, Any], similarity: float, cells: List[str]
) -> bool:
    score = score_info["score"]
    numeric_ratio = score_info["numeric_ratio"]
    if score >= 0.48 and similarity >= 0.25:
        return True
    if score >= 0.38 and similarity >= 0.50:
        return True
    if score >= 0.42 and numeric_ratio < 0.30 and looks_like_repeated_header_row(cells):
        return True
    return False


def looks_like_repeated_header_row(cells: List[str]) -> bool:
    text = " ".join(cells).lower()
    repeated_patterns = [
        "type", "class", "zone", "material", "surface", "rating",
        "length", "description", "dimensions", "range", "size",
        "minimum", "maximum", "width", "height",
    ]
    hits = sum(1 for pattern in repeated_patterns if pattern in text)
    return hits >= 2


def max_similarity_to_rows(cells: List[str], rows: List[Dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    best = 0.0
    for row in rows:
        best = max(best, row_similarity(cells, row["cells"]))
    return round(best, 4)


def row_similarity(a_cells: List[str], b_cells: List[str]) -> float:
    a = set(tokenize(" ".join(a_cells).lower()))
    b = set(tokenize(" ".join(b_cells).lower()))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# --- HEADER CLEANING ---


def clean_header_rows(
    rows: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    cleaned_rows: List[Dict[str, Any]] = []
    changed = 0
    total = 0
    for row in rows:
        cleaned_cells: List[str] = []
        for cell in row["cells"]:
            total += 1
            new_cell = clean_header_cell(cell)
            if new_cell != cell:
                changed += 1
            cleaned_cells.append(new_cell)
        cleaned_rows.append({"cells": cleaned_cells, "is_header": True})
    debug = {"total_cells": total, "changed_cells": changed}
    return cleaned_rows, debug


def clean_header_cell(text: str) -> str:
    text = normalize_cell_text(text)
    for frag in COMMON_OCR_JUNK:
        text = text.replace(frag, " ")
    text = re.sub(r"\s*\|\s*", " | ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\b[IiLl]{1,2}\b", " ", text)
    text = re.sub(r"[~]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    low = text.lower()
    if low in PLACEHOLDER_HEADER_NAMES:
        return "Stub"
    return text


# --- TABLE TYPE ---


def classify_table_type(
    header_rows: List[Dict[str, Any]], data_rows: List[Dict[str, Any]]
) -> str:
    header_text = " ".join(" ".join(r["cells"]) for r in header_rows).lower()
    numeric_density = estimate_numeric_density(data_rows)
    category_hits = count_category_signals(header_text)
    property_hits = count_property_signals(header_text)
    if category_hits >= 2:
        return TABLE_TYPE_MATRIX
    if numeric_density >= 0.45:
        return TABLE_TYPE_NUMERIC_LOOKUP
    if property_hits >= 2:
        return TABLE_TYPE_PROPERTY
    return TABLE_TYPE_UNKNOWN


def count_category_signals(text: str) -> int:
    patterns = [
        "yes", "no", "class", "type", "zone", "group",
        "metallic", "non-metallic", "permitted", "not permitted",
    ]
    return sum(1 for p in patterns if p in text)


def count_property_signals(text: str) -> int:
    patterns = [
        "material", "surface", "treatment", "dimension", "size",
        "description", "category", "classification",
    ]
    return sum(1 for p in patterns if p in text)


def estimate_numeric_density(rows: List[Dict[str, Any]]) -> float:
    total = 0
    numeric = 0
    for row in rows:
        for cell in row["cells"]:
            for tok in tokenize(cell):
                total += 1
                if is_numberish(tok):
                    numeric += 1
    return numeric / max(total, 1)


# --- STUB COLUMN ---


def detect_stub_column(
    header_rows: List[Dict[str, Any]], data_rows: List[Dict[str, Any]]
) -> Optional[int]:
    if not data_rows:
        if header_rows and header_rows[0]["cells"]:
            return 0
        return None
    max_cols = max(len(row["cells"]) for row in data_rows)
    col_scores: List[float] = []
    for col_idx in range(max_cols):
        text_count = 0
        numeric_count = 0
        unique_words: Set[str] = set()
        for row in data_rows[:10]:
            if col_idx >= len(row["cells"]):
                continue
            cell = row["cells"][col_idx]
            for tok in tokenize(cell):
                unique_words.add(tok.lower())
                if is_numberish(tok):
                    numeric_count += 1
                else:
                    text_count += 1
        total = max(text_count + numeric_count, 1)
        text_ratio = text_count / total
        uniqueness = len(unique_words)
        score = 0.7 * text_ratio + 0.3 * min(uniqueness / 8.0, 1.0)
        col_scores.append(score)
    if not col_scores:
        return None
    best_idx = max(range(len(col_scores)), key=lambda i: col_scores[i])
    if best_idx != 0 and col_scores[0] >= col_scores[best_idx] - 0.08:
        return 0
    return best_idx


# --- HEADER TREE ---


def build_header_tree(
    cleaned_header_rows: List[Dict[str, Any]],
    data_rows: List[Dict[str, Any]],
    stub_column_index: Optional[int],
    table_type: str,
) -> List[Dict[str, Any]]:
    if not cleaned_header_rows:
        return fallback_tree_from_data(data_rows)
    if len(cleaned_header_rows) == 1:
        return build_tree_from_single_header(
            cleaned_header_rows[0]["cells"],
            stub_column_index=stub_column_index,
            table_type=table_type,
        )
    return build_tree_from_multiple_headers(
        cleaned_header_rows,
        stub_column_index=stub_column_index,
        table_type=table_type,
    )


def build_tree_from_single_header(
    cells: List[str],
    stub_column_index: Optional[int],
    table_type: str,
) -> List[Dict[str, Any]]:
    tree: List[Dict[str, Any]] = []
    for idx, cell in enumerate(cells):
        cell = clean_header_cell(cell)
        if idx == stub_column_index:
            tree.append({"name": normalize_stub_name(cell), "children": []})
            continue
        split_children = split_generic_bundled_header(cell)
        if len(split_children) > 1:
            tree.append(
                {
                    "name": infer_generic_parent_name(cell, table_type),
                    "children": split_children,
                }
            )
        else:
            tree.append({"name": cell, "children": []})
    return tree


def build_tree_from_multiple_headers(
    header_rows: List[Dict[str, Any]],
    stub_column_index: Optional[int],
    table_type: str,
) -> List[Dict[str, Any]]:
    max_cols = max(len(r["cells"]) for r in header_rows)
    padded_rows: List[List[str]] = []
    for row in header_rows:
        padded = list(row["cells"]) + [""] * (max_cols - len(row["cells"]))
        padded_rows.append(padded)
    tree: List[Dict[str, Any]] = []
    for col_idx in range(max_cols):
        parts: List[str] = []
        for row in padded_rows:
            cell = clean_header_cell(row[col_idx])
            if cell:
                parts.append(cell)
        merged = merge_header_parts(parts)
        if col_idx == stub_column_index:
            tree.append({"name": normalize_stub_name(merged), "children": []})
            continue
        split_children = split_generic_bundled_header(merged)
        if len(split_children) > 1:
            tree.append(
                {
                    "name": infer_generic_parent_name(merged, table_type),
                    "children": split_children,
                }
            )
        else:
            tree.append({"name": merged, "children": []})
    return tree


def merge_header_parts(parts: List[str]) -> str:
    seen: List[str] = []
    for part in parts:
        if part and part not in seen:
            seen.append(part)
    return " - ".join(seen).strip(" -")


def normalize_stub_name(name: str) -> str:
    low = name.lower().strip()
    if low in PLACEHOLDER_HEADER_NAMES or not low:
        return "Stub"
    return name


def infer_generic_parent_name(text: str, table_type: str) -> str:
    low = text.lower()
    if "zone" in low:
        return "Zones"
    if "type" in low:
        return "Types"
    if "class" in low:
        return "Classes"
    if "material" in low:
        return "Material"
    if "size" in low:
        return "Size"
    if "rating" in low:
        return "Rating"
    if table_type == TABLE_TYPE_MATRIX:
        return "Categories"
    if table_type == TABLE_TYPE_NUMERIC_LOOKUP:
        return "Values"
    return text


def split_generic_bundled_header(text: str) -> List[str]:
    low = text.lower()
    type_matches = re.findall(r"type\s+[a-z0-9]+", low)
    if len(type_matches) >= 2:
        return [t.title() for t in type_matches]
    class_matches = re.findall(r"class\s+[a-z0-9]+", low)
    if len(class_matches) >= 2:
        return [c.title() for c in class_matches]
    zone_matches = re.findall(r"zone\s+[a-z0-9]+", low)
    if len(zone_matches) >= 2:
        return [z.title() for z in zone_matches]
    yn: List[str] = []
    if re.search(r"\byes\b", low):
        yn.append("Yes")
    if re.search(r"\bno\b", low):
        yn.append("No")
    if len(yn) >= 2:
        return yn
    if "metallic" in low and "non-metallic" in low:
        return ["Metallic", "Non-metallic"]
    return [text]


def fallback_tree_from_data(data_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not data_rows:
        return []
    max_cols = max(len(r["cells"]) for r in data_rows)
    return [{"name": f"Column {i + 1}", "children": []} for i in range(max_cols)]


def flatten_header_tree(tree: List[Dict[str, Any]]) -> List[str]:
    flat: List[str] = []
    for node in tree:
        name = node.get("name", "").strip()
        children = node.get("children", []) or []
        if not children:
            flat.append(name)
        else:
            for child in children:
                if child == name:
                    flat.append(name)
                else:
                    flat.append(f"{name} - {child}")
    return flat


# --- BODY CLEANUP ---


def remove_body_rows_that_still_look_like_headers(
    data_rows: List[Dict[str, Any]], header_rows: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    kept: List[Dict[str, Any]] = []
    removed_indexes: List[int] = []
    for idx, row in enumerate(data_rows):
        analysis = analyze_row(row["cells"])
        similarity = max_similarity_to_rows(row["cells"], header_rows)
        if analysis["score"] >= 0.40 and similarity >= 0.45:
            removed_indexes.append(idx)
            continue
        kept.append(row)
    debug = {
        "removed_header_like_body_rows": removed_indexes,
        "remaining_data_rows": len(kept),
    }
    return kept, debug


# --- CONFIDENCE ---


def score_reconstruction_confidence(
    cleaned_header_rows: List[Dict[str, Any]],
    cleaned_body_rows: List[Dict[str, Any]],
    final_columns: List[str],
    table_type: str,
) -> str:
    score = 0.0
    if cleaned_header_rows:
        score += 0.20
    if len(final_columns) >= 2:
        score += 0.20
    if len(cleaned_body_rows) >= 2:
        score += 0.15
    if table_type != TABLE_TYPE_UNKNOWN:
        score += 0.10
    header_text = " ".join(" ".join(r["cells"]) for r in cleaned_header_rows).lower()
    if not contains_obvious_header_junk(header_text):
        score += 0.10
    else:
        score -= 0.15
    if len(final_columns) == 1 and len(cleaned_body_rows) <= 1:
        score -= 0.20
    if any(looks_like_repeated_header_row(r["cells"]) for r in cleaned_body_rows[:4]):
        score -= 0.15
    if score >= 0.65:
        return "high"
    if score >= 0.40:
        return "medium"
    return "low"


def contains_obvious_header_junk(text: str) -> bool:
    for frag in COMMON_OCR_JUNK:
        if frag in text:
            return True
    return False


# --- DEBUG NOTES ---


def build_reconstruction_notes(
    row_debug: List[Dict[str, Any]],
    clean_debug: Dict[str, Any],
    body_debug: Dict[str, Any],
    truncated: bool = False,
) -> List[str]:
    notes: List[str] = []
    promoted = 0
    for item in row_debug:
        if item["source"] == "data_rows":
            if (
                item.get("max_header_similarity", 0) >= 0.45
                and item["analysis"]["score"] >= 0.40
            ):
                promoted += 1
    if promoted:
        notes.append(
            f"Detected {promoted} possible repeated header-like body rows (see promoted_header_rows)."
        )
    if clean_debug.get("changed_cells", 0) > 0:
        notes.append(f"Cleaned {clean_debug['changed_cells']} header cells.")
    removed = body_debug.get("removed_header_like_body_rows", [])
    if removed:
        notes.append(f"Removed {len(removed)} header-like rows from body.")
    if truncated:
        notes.append("Flattened header names truncated to match table column width.")
    return notes


# --- TOKEN HELPERS ---


def tokenize(text: str) -> List[str]:
    if not text:
        return []
    text = text.replace("|", " ")
    text = text.replace("/", " ")
    text = re.sub(r"[(),;:<>]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    return text.split(" ")


def is_numberish(token: str) -> bool:
    token = token.strip().lower()
    if not token:
        return False
    return bool(
        re.match(
            r"^[<>]?\d+(\.\d+)?(%|mm2|mm|a|m|°c|c|v|va|kw|w|hz)?$",
            token,
        )
    )


def is_junk_token(token: str) -> bool:
    if token in COMMON_OCR_JUNK:
        return True
    for pattern in JUNK_FRAGMENT_PATTERNS:
        if re.match(pattern, token):
            return True
    return False
