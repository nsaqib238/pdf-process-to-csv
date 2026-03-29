# Next table pipeline improvements

**Core track:** deterministic, rule-based table extraction (geometry, captions, scoring, filters). Do **not** feed clause JSON or Adobe clause bodies into the table pipeline as a **detection** source.

**Optional track:** AI (vision + structured JSON) as a **refinement** step after the pipeline has already proposed a table—never as the sole detector.

---

## P0 — Clause-like content in `tables.json` (open issue)

**Symptom:** Some emitted tables are clearly **prose / clause fragments** (running headers, numbered clause text, paragraph flow) rather than real grids. They appear as **single-column** “tables” with long header cells (e.g. `AS/NZS 3000 … | 3.3 … | clause body`), often from **Camelot stream** or **page sweep** when pdfplumber finds nothing on that page.

**Why it happens (conceptual):**

- **Page sweep** and **stream** flavors treat **ragged text blocks** as a matrix; one logical line becomes one “column.”
- **Caption-first** multi-engine improves real tables but does not, by itself, veto **non-table** blocks that other stages still add.
- **No hard “this is not a table” gate** tuned for standards PDFs where **clause text sits where a table might be**.

**Direction (table pipeline only):**

1. **Clause-shaped rejection** — After extraction, score “clause-likeness” from **structure + text** only: e.g. single column + very long first cell + clause numbering pattern + prose markers (`shall`, `may`, list markers) + lack of **multi-column numeric/tabular** character. **Drop or downgrade** (never emit as high-confidence table, or omit entirely when `omit_unnumbered_table_fragments`–style strictness applies).
2. **Sweep gating** — Before appending sweep results, require **minimum column count** (≥2) **or** explicit **caption anchor** on that page for single-column blocks **or** a **tabular score** from cell length / delimiter / alignment heuristics.
3. **Source tagging** — Keep `source_method` precise (`camelot:sweep:stream`, etc.) so downstream QA and presets can **filter by source** without new fields.
4. **Regression fixtures** — Tiny PDF snippets or saved matrices that must **not** produce a table row in `tables.json`.

**Out of scope for this doc:** Fixing **clause extraction** itself; using clause pipeline output to **label** tables (explicitly avoided per architecture choice).

---

## P1 — Table numbering recall (3.8, appendix, duplicates)

**Symptom:** Many grids have `table_number: null`; subset like **3.8** or **appendix** IDs missing while neighbors (3.7, 3.9, B…) appear.

**Why:** Captions must appear as **clean word lines** (often **line-start** `TABLE …`); merged headers, split words, or non-standard lines break anchors. Appendix layouts differ; **topmost-per-number** dedupe skips repeated captions.

**Direction:**

1. **Caption line variants** — Tolerate **short leading noise** on the same line (limited prefix before `Table …`) for discovery only; keep strict cell rules for row-inferred IDs.
2. **Second caption pass** — If a grid has **no** number but **one** strong `TABLE N.M` line in a **wider** vertical window (not only “above bbox”), link by **page + reading order + distance**.
3. **Appendix patterns** — Explicit tests and tuning for `TABLE B1`, `TABLE D12(A)` word clustering (spacing, parentheses).
4. **Merge audit** — Log when two fragments share a number vs when one is dropped by **IoU / table_key** dedupe.

---

## P2 — Detection and engine pool

**Already in place (high level):** Caption-first **multi-engine** band under anchors (pdfplumber + Camelot + Tabula), full-page pdfplumber with dedupe against caption wins, loose second pass, empty-page sweep (Camelot + Tabula), multipage continuation merge, header reconstruction.

**Next:**

1. **Single pool dedupe** — All engines on a page → **one IoU-scored pool** before merge; reduce duplicate fragments and conflicting bboxes.
2. **Fusion without prior pdfplumber hit** — Caption region already runs multiple engines; extend **optional** “weak page” pass: if **max(grid scores) < T** on a page, run **region = full column** (not full page noise) once.
3. **Word-column hints** — Vertical alignment bands from `extract_words` to flag tabular regions when `find_tables` returns nothing.
4. **Body-column crop** — Crop to main text column on two-column or wide pages before line detection.

---

## P3 — Captions and layout

1. **Wider / lateral caption search** — If nothing strictly above bbox, search **limited** band to the side or slightly overlapping (PDF-specific).
2. **Continuation / multipage** — Stronger signals: stable column count, repeated header row similarity, “(continued)” lines; **blank page** gap policy (configurable).
3. **Gap between caption and grid** — Already partially addressed with **max_gap** and **expand-to-bottom** retry; tune per document class if needed.

---

## P4 — Quality, diagnostics, operations

1. **Per-table diagnostics** — Structured `extraction_notes`: engines tried, caption anchor id, sweep vs anchor, rejection reason (e.g. `clause_shape_reject`).
2. **Confidence** — Down-rank single-engine, single-column, no caption, high clause-likeness.
3. **Config presets** — `recall` vs `precision`: fusion, `omit_unnumbered_table_fragments`, caption multi-engine, sweep limits.
4. **Env health** — Startup or log warnings: Java, Ghostscript binary, `ghostscript` PyPI module for Camelot lattice.
5. **Regression tests** — Committed small PDFs or matrices for caption parse, merge, and **non-table** rejection.

---

## P5 — Optional AI-assisted layout refinement (vision + JSON)

**Provider (decision):** Use the **OpenAI API** for this step (e.g. a **vision-capable** chat model so the crop is an image input alongside JSON). Store the API key in env (e.g. `OPENAI_API_KEY`); do not commit keys. Log **model name + API version** (or dated snapshot) in `extraction_notes` / job metadata for audit and reproducibility.

**Role:** **Assist** the deterministic pipeline—**repair** a candidate table, **not** replace geometry-first detection. The model receives a **raster crop of the table region** (or page snippet) **plus** the current structured proposal (e.g. rows/cells JSON matching your `Table` shape). It returns **corrected layout** (or a **validated patch**) under a **strict schema**.

**When to invoke (gating):**

- Low **unified_score** / confidence, **semantic_hard_fail**, or **single-column** sweep artifacts.
- **Caption present** (`table_number` set) but structure looks **implausible** (column count vs image).
- Optional **user/API flag**: `enable_table_ai_refinement` (default off in strict environments).

**What to ask for:**

- **Layout only:** merge/split cells, fix header/body boundary, reject **“not a table”** (prose block)—with instructions **not to paraphrase** normative cell text.
- **Structured output:** same JSON shape as today or a **minimal diff** (e.g. `reject: true` or `cells: [...]`) so the server can **validate** and **fallback** to baseline on parse failure.

**Guardrails:**

- **Low temperature**; explicit **“do not invent standard values or rewrite legal text”** in the prompt.
- **Validate** row/column counts against the crop; **reject** model output that drifts too far from baseline text (e.g. Levenshtein / token overlap on non-empty cells).
- **Audit:** log model id, prompt version, which `table_id`s were refined; store **before/after** for support.

**Risks and ops:**

- **Latency and cost** scale with number of tables; run only on **gated** candidates or cap per job.
- **OpenAI** (and any cloud vision API) sends **document pixels** off-device—check privacy, retention policy, and **copyright** for licensed PDFs (e.g. standards). Prefer org settings that match your compliance needs.
- **Reproducibility:** treat AI output as **non-deterministic**; pin `model` in config and log it; note OpenAI model updates over time.

**Relationship to P0:** Rule-based **clause-shaped rejection** should remain the **first** line of defense; AI can **second-guess** borderline cases but should not be the only filter for obvious prose.

---

## Suggested implementation order

| Order | Item | Rationale |
|-------|------|-----------|
| 1 | **P0 clause-shaped rejection + sweep gating** | Stops polluting `tables.json` with prose; highest user-visible quality win. |
| 2 | **P1 caption widening + appendix tuning** | More stable `table_number` without clause pipeline coupling. |
| 3 | **P2 pool dedupe + optional weak-page region** | Better recall without duplicating garbage. |
| 4 | **P4 diagnostics + presets** | Easier tuning and support. |
| 5 | **P5 AI refinement (optional, gated)** | Improves hard layouts after baseline exists; keep off until P0/P4 reduce noise and logging is ready. |

---

## Reference — recently implemented (for context)

- Page sweep when pdfplumber empty; loose pdfplumber second pass.
- Caption-first **multi-engine** region (`TABLE …` then pdfplumber + Camelot + Tabula + pick best); expand band to page bottom when empty.
- Full-page pdfplumber **after** caption pass, with IoU dedupe against caption results; **label** pass for unnumbered grids.
- Adjacent-page **body-only continuation** merge when previous segment is numbered.
- Header reconstruction pass; ragged header row fix in `_infer_headers`.
- Ghostscript **PyPI** dependency for Camelot lattice import error.
- Relaxed some **omit** rules for long narrow unnumbered tables.

Treat **P0–P5** as the active roadmap; **P5** is optional and config-gated.
