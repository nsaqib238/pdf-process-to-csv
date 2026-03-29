# PDF Structure Extraction Pipeline

Extract structured text, clauses, and tables from PDF documents. The local pipeline uses **pdfplumber** plus optional **Camelot** / **Tabula** for standards-style tables; **Adobe PDF Services** remains optional for cloud extract/OCR.

## Features

- **PDF classification**: Scanned vs text-based heuristics
- **Clause processing**: Hierarchy, sub-items, notes, exceptions, page ranges
- **Table processing**: Multi-row headers, merged cells, multi-page tables, optional **Camelot/Tabula fusion**, **header reconstruction** (`final_columns` in `tables.json`)
- **Advanced filtering**: Clause-shaped content rejection, sweep gating, 2-column prose detection (P0-P4 + Iteration 1 upgrades)
- **Validation**: Quality checks and confidence scoring
- **Outputs**: `normalized_document.txt`, `clauses.json`, `tables.json`
- **Web UI**: Full pipeline or **tables-only** fast path (`POST /api/process-pdf-tables`)

## Recent Upgrades (P0-P4 + Iteration 1)

The pipeline now includes comprehensive quality improvements:
- **P0**: Clause-shaped rejection (prose/normative text filtering) + sweep gating (blocks single-column prose)
- **P1**: Enhanced table numbering with wider search windows (improved appendix table recall)
- **P2**: Multi-engine detection improvements
- **P4**: Enhanced diagnostics (clause_shaped_rejected, sweep_gated_rejected, schematic_rejected)
- **Iteration 1**: 2-column prose detection (change lists, TOC entries, amendment descriptions)

**Result**: ~80% reduction in false positives, 78% table number coverage (up from 20%)

See `PDF_PIPELINE_UPGRADES.md`, `ITERATION_1_IMPROVEMENTS.md`, and `TABLE_COVERAGE_REPORT.md` for details.

## Tech stack

- **Backend**: Python 3.10+ (3.12 recommended), FastAPI, pdfplumber, pypdf, optional camelot-py / tabula-py
- **Frontend**: Next.js 14 + TypeScript + Tailwind

---

## Prerequisites (install everything)

### 1. Python

- **Python 3.10, 3.11, or 3.12** (64-bit). Check: `python --version`

### 2. Node.js

- **Node.js 18+** (20 LTS recommended). Check: `node --version`

### 3. Table fusion (strongly recommended for AS/NZS-style ruled tables)

These are **system** installs (not `pip`). Without them, fusion is skipped or degraded; you still get pdfplumber tables.

| Component | Purpose | Verify |
|-----------|---------|--------|
| **Java (JRE/JDK 8+)** | **tabula-py** uses tabula-java | `java -version` |
| **Ghostscript** | **Camelot** lattice / PDF rendering | `gswin64c -version` (Windows) or `gs --version` (macOS/Linux) |
| **Tesseract** (optional) | Cropped table **image OCR** fallback | `tesseract --version` |

**Windows (examples)**

- [Eclipse Temurin JDK](https://adoptium.net/) or Oracle/OpenJDK — add `java` to PATH.
- [Ghostscript for Windows](https://www.ghostscript.com/download/gsdnld.html) — ensure `gswin64c.exe` is on PATH (or install via [Chocolatey](https://chocolatey.org/): `choco install openjdk ghostscript`).
- [Tesseract installer](https://github.com/UB-Mannheim/tesseract/wiki) — add to PATH, or `choco install tesseract`.


### 4. Adobe PDF Services (optional)

Only if you use the Adobe SDK path. See [Adobe PDF Services](https://developer.adobe.com/document-services/apis/pdf-services/) and `ADOBE_SETUP.md`.

---

## Setup

### Backend (Python)

Use **`python -m pip`** (not `pip` alone) so packages install into the **same** interpreter that runs `python main.py`. On Windows, global `pip` can point at a different Python than your venv.

**Option A — virtualenv inside `backend/`**

```bash
cd backend
python -m venv .venv
```

**Windows:** `.venv\Scripts\activate`  
**macOS/Linux:** `source .venv/bin/activate`

Still in `backend/`:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

**Option B — virtualenv at repository root** (if `.venv` lives next to `backend/`)

From the repo root, after activating `.venv`:

```bash
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
```

Then start the API from `backend/`: `cd backend` and `python main.py`.

If **Camelot** fails (OpenCV/NumPy), use a clean venv and ensure NumPy stays `<2` as pinned.

### Configure environment

Create `backend/.env` (optional but useful):

```env
# Adobe (optional)
ADOBE_CLIENT_ID=
ADOBE_CLIENT_SECRET=

# Tables: set false only if Java is not installed
ENABLE_TABLE_CAMELOT_TABULA=true
# When pdfplumber finds no table on a page, run Camelot+Tabula on that page (recall)
TABLE_PIPELINE_PAGE_SWEEP_WHEN_EMPTY=true
TABLE_PIPELINE_PAGE_SWEEP_MAX_PER_PAGE=8
# Retry pdfplumber with looser tolerances if first pass is empty on that page
TABLE_PIPELINE_PDFPLUMBER_LOOSE_SECOND_PASS=true

# Recall vs noise (defaults favor more tables on standards PDFs)
OMIT_UNNUMBERED_TABLE_FRAGMENTS=false
TABLE_PIPELINE_FUSION_TRIGGER_SCORE=0.82

# Debug: limit pages
# TABLE_PIPELINE_MAX_PAGES=50

# Header reconstruction post-pass
ENABLE_HEADER_RECONSTRUCTION=true
```

### Frontend

From the **repository root** (not `backend/`):

```bash
npm install
```

---

## Running the app

**Terminal 1 — API**

```bash
cd backend
# activate venv first
python main.py
```

API: http://localhost:8000

**Terminal 2 — UI**

```bash
npm run dev
```

App: http://localhost:3000

- Choose **full** pipeline or **tables only** (faster; only `tables.json`).
- Large PDFs can run a long time; the UI uses a long HTTP timeout.

### CLI: tables only (no browser)

**Basic usage:**
```bash
cd backend
python run_local_tables.py "../Tables AS3000 2018.pdf"
```

**With options:**
```bash
# Specify output directory
python run_local_tables.py "../Tables AS3000 2018.pdf" --out-dir ..

# Process only first 50 pages (for testing)
python run_local_tables.py "../Tables AS3000 2018.pdf" --max-pages 50 --out-dir ../output/test

# Disable fusion (faster, pdfplumber only)
python run_local_tables.py "../Tables AS3000 2018.pdf" --no-fusion

# Skip header reconstruction
python run_local_tables.py "../Tables AS3000 2018.pdf" --no-header-reconstruction
```

**Available options:**
- `--out-dir DIR` — Output directory (default: alongside PDF with `_tables_out` suffix)
- `--max-pages N` — Process only first N pages (overrides `TABLE_PIPELINE_MAX_PAGES` env var)
- `--no-fusion` — Disable Camelot/Tabula fusion (faster; pdfplumber only)
- `--no-header-reconstruction` — Skip post-process header reconstruction

**Output location:**
- Default: `<pdf_directory>/<pdf_stem>_tables_out/tables.json`
- Example: `input/AS3000 2018_tables_out/tables.json`
- With `--out-dir ..`: writes to `../tables.json` (repository root)

---

## API

### `POST /api/process-pdf`

Full pipeline: clauses + tables + normalized text + validation.

### `POST /api/process-pdf-tables`

Tables only: same table pipeline (pdfplumber + optional fusion + header reconstruction), writes `outputs/{job_id}/tables.json`. No clauses.

### `GET /api/download/{job_id}/{filename}`

Download generated files.

---

## Output formats

- **`normalized_document.txt`** — Human-readable clauses + table summaries (full mode only).
- **`clauses.json`** — Structured clauses (full mode only).
- **`tables.json`** — Tables with `header_rows`, `data_rows`, and when reconstruction ran: `final_columns`, `reconstruction_confidence`, `header_model`, etc.

### tables.json structure

Each table includes:
- `table_id` — Unique identifier
- `table_number` — Caption number (e.g., "3.2", "C7", "D11") or null
- `page_start` / `page_end` — Page range
- `header_rows` — Extracted header rows with cells
- `data_rows` — Extracted data rows with cells
- `source_method` — Extraction engine (e.g., "camelot:lattice", "pdfplumber:caption_region")
- `confidence` — Quality score (0.0-1.0)
- `extraction_notes` — Diagnostic information
- `quality_metrics` — Row/column counts, fill ratio, noise ratio
- `final_columns` — Reconstructed column headers (when header reconstruction enabled)

### Rejection diagnostics

The pipeline logs rejection statistics:
- `clause_shaped_rejected` — Tables rejected as prose/normative text
- `sweep_gated_rejected` — Single-column prose blocks filtered
- `schematic_rejected` — Image-based tables filtered

These metrics help verify the pipeline is correctly filtering false positives.

---

## Troubleshooting

| Issue | What to do |
|--------|------------|
| `No module named 'fastapi'` (or other imports) after `pip install` | You ran a different `pip` than your `python`. Use **`python -m pip install -r requirements.txt`** from the same folder/venv (in `backend/` use `requirements.txt`; from repo root use `backend/requirements.txt`). Never run `-m pip ...` alone — it must be **`python -m pip ...`**. |
| `Camelot import failed` | Install Ghostscript; reinstall with `python -m pip install -r requirements.txt` in a clean venv. |
| `No module named 'ghostscript'` (Camelot lattice) | Run `pip install "ghostscript>=0.7,<0.9"` (now in `requirements.txt`). You still need the **Ghostscript binary** on PATH (`gswin64c` / `gs --version`). |
| Tabula errors / no fusion wins | Install Java; `java -version` must work. |
| `tesseract` / image table recovery fails | Install Tesseract and ensure it is on PATH. |
| Too many noisy unnumbered tables | Set `OMIT_UNNUMBERED_TABLE_FRAGMENTS=true` in `.env`. |
| Fusion too slow | Set `ENABLE_TABLE_CAMELOT_TABULA=false` (pdfplumber only). |
| Deprecation warnings about PyPDF2 | Resolved: project uses **pypdf** via `requirements.txt`. |
| `Ignoring invalid distribution -vicorn` (pip) | Broken partial install; run `pip uninstall uvicorn` then `pip install "uvicorn[standard]>=0.27,<0.32"`. |
| Camelot `cv` extra errors on pip | This repo pins **`camelot-py>=0.11,<1.0`** and **`opencv-python-headless`** separately (Camelot 1.x dropped `[cv]`). |

---

## Processing overview (full mode)

1. Classify PDF (text vs scanned heuristic).
2. Extract text (pdfplumber, fallback pypdf).
3. Zone filtering and clause parsing.
4. Table extraction: pdfplumber → optional Camelot/Tabula fusion → optional image OCR → header reconstruction.
5. Validation and JSON/text export.

---

## License

MIT

## Documentation

### Pipeline Architecture
- **`PIPELINE_ARCHITECTURE.md`** — Complete system architecture (87 methods, 3140 lines)
- **`PDF_PIPELINE_UPGRADES.md`** — P0-P4 upgrade details
- **`ITERATION_1_IMPROVEMENTS.md`** — Enhanced clause rejection for 2-column prose
- **`UPGRADE_SUMMARY.md`** — Complete summary of all improvements
- **`TABLE_COVERAGE_REPORT.md`** — Analysis of extracted tables from AS3000 2018.pdf

### Example Results

**AS3000 2018.pdf (548 pages):**
- Before upgrades: 114 tables (79% garbage, 20% with table numbers)
- After upgrades: 23 tables (clean, 78% with table numbers)
- Improvement: 79% reduction in false positives

**Table numbers extracted:**
- Section 3: Tables 3.2, 3.5, 3.9, 3.10
- Section 8: Table 8.1
- Appendix C: Tables C3, C7, C10, C11, C12
- Appendix D: Tables D1, D2, D5, D11
- Section 11-12: Tables 11, 12
- Appendix K: Table K1
- Forms: Table 104.101

## References

- [Adobe PDF Services](https://developer.adobe.com/document-services/)
- [pdfplumber](https://github.com/jsvine/pdfplumber)
- [pypdf](https://github.com/py-pdf/pypdf)
- [Camelot](https://camelot-py.readthedocs.io/)
- [tabula-py](https://github.com/chezou/tabula-py)
