"""
Configuration settings for PDF processing pipeline
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # Adobe PDF Services credentials
    adobe_client_id: Optional[str] = None
    adobe_client_secret: Optional[str] = None

    # File paths
    upload_dir: str = "uploads"
    output_dir: str = "outputs"

    # Processing settings (below Adobe 100MB API cap)
    max_file_size: int = 85 * 1024 * 1024  # 85MB
    ocr_locale: str = "en-US"
    # Extract API applies a low page limit to PDFs Adobe treats as scanned (~100 pages).
    # Chunk large PDFs so each part stays under that limit.
    adobe_extract_chunk_pages: int = 100
    # If Adobe times out server-side, auto-split a chunk until this floor.
    adobe_extract_min_chunk_pages: int = 10
    # Adobe SDK defaults are too low for long-running extract polling on large files.
    adobe_connect_timeout_ms: int = 15000
    adobe_read_timeout_ms: int = 120000

    # Table pipeline: Camelot/Tabula fusion (needs Java; improves many standards-style grids)
    enable_table_camelot_tabula: bool = True
    # When True, drops many unnumbered low-score grids (reduces noise but misses real AS/NZS tables).
    # Default False for recall on standards like AS3000. Env: OMIT_UNNUMBERED_TABLE_FRAGMENTS=true
    omit_unnumbered_table_fragments: bool = False
    # Run Camelot/Tabula when pdfplumber quality score is below this (0..1). Higher = try fusion more often.
    table_pipeline_fusion_trigger_score: float = 0.82
    # If True, always run fusion for every pdfplumber anchor (slow; max recall when Java deps work).
    table_pipeline_always_try_fusion: bool = False
    # Limit pages for debugging (None = full document). Env: TABLE_PIPELINE_MAX_PAGES
    table_pipeline_max_pages: Optional[int] = None
    # pdfplumber find_tables tolerances (looser helps ruled AS/NZS-style tables)
    table_snap_x_tolerance: int = 7
    table_snap_y_tolerance: int = 6
    table_intersection_tolerance: int = 6
    table_join_x_tolerance: int = 7
    # If primary find_tables finds nothing on a page, retry with looser tolerances (NEXT_TABLE_PIPELINE_IMPROVEMENTS.md)
    table_pipeline_pdfplumber_loose_second_pass: bool = True
    # When pdfplumber finds zero tables on a page, run Camelot+Tabula on that page (needs fusion deps). Env: TABLE_PIPELINE_PAGE_SWEEP_WHEN_EMPTY=false
    table_pipeline_page_sweep_when_empty: bool = True
    # Max tables to keep per page from sweep (Tabula can over-segment)
    table_pipeline_page_sweep_max_per_page: int = 8
    # Post-process tables with structure-first header reconstruction (TABLE_HEADER RECONSTRUCT.md)
    enable_header_reconstruction: bool = True
    # Use PDF word geometry: "TABLE X.X" line + find_tables in the band below (table pipeline only; no clause text).
    table_pipeline_caption_anchor_pass: bool = True
    # Max vertical distance (pt) below caption line to search for a grid.
    table_pipeline_caption_anchor_max_depth_pt: float = 520.0
    # Max distance (pt) from caption line bottom to grid top when labeling a detected table (allows
    # a few text/footer lines between "TABLE X.X" and the ruled area).
    table_pipeline_caption_anchor_max_gap_pt: float = 300.0
    # Merge page-N+1 body-only extract into previous table when same numbered table continues
    # (no caption on the next page; column layout matches). Table-pipeline only.
    table_pipeline_merge_adjacent_unnumbered_continuation: bool = True
    # For each TABLE caption, run pdfplumber + Camelot + Tabula on the band below (not only after bad score).
    table_pipeline_caption_region_multi_engine: bool = True
    # If no grid in the default band, expand once to the bottom of the page and retry extractors.
    table_pipeline_caption_region_expand_when_empty: bool = True

    # API settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000


settings = Settings()
