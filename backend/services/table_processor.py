"""
Simplified Table Processor - Uses Modal.com Complete Data
=========================================================
Modal.com provides complete table extraction, backend just validates.
"""

import logging
from typing import List, Dict, Any, Optional
from models.table import Table

logger = logging.getLogger(__name__)


class TableProcessor:
    """Process tables from Modal.com (complete data, no extraction needed)"""

    def __init__(self):
        self.tables: List[Table] = []

    def process_tables_from_modal(
        self,
        modal_tables: List[Dict],
        clauses: List[Any] = None
    ) -> List[Table]:
        """
        Process tables from Modal.com complete extraction.
        
        Modal provides:
        - Complete table content (headers, data rows)
        - Table numbers and titles
        - Structure metadata
        
        Backend just:
        - Converts to Table objects
        - Links to parent clauses (if provided)
        - Validates data quality

        Args:
            modal_tables: Complete tables from Modal.com
            clauses: Optional list of clauses for parent linking

        Returns:
            List of Table objects
        """
        logger.info(f"Processing {len(modal_tables)} tables from Modal.com")

        if not modal_tables:
            logger.warning("No tables provided from Modal.com")
            return []

        # Convert Modal format to Table objects
        self.tables = self._convert_dicts_to_table_objects(modal_tables)

        # Link tables to parent clauses if provided
        if clauses:
            self._link_tables_to_clauses(clauses)
            logger.info("✅ Linked tables to parent clauses")

        logger.info(f"✅ Processed {len(self.tables)} tables from Modal.com")
        return self.tables

    def _convert_dicts_to_table_objects(self, table_dicts: List[Dict]) -> List[Table]:
        """Convert table dicts to Table model objects."""
        tables = []
        
        for table_dict in table_dicts:
            try:
                table = Table(**table_dict)
                tables.append(table)
            except Exception as e:
                logger.error(f"Error converting table to object: {e}")
                logger.debug(f"Table dict: {table_dict}")
                continue

        return tables

    def _link_tables_to_clauses(self, clauses: List[Any]):
        """Link tables to their parent clauses based on page location."""
        if not clauses:
            return

        # Build clause lookup by page
        clause_by_page = {}
        for clause in clauses:
            for page in range(clause.page_start, clause.page_end + 1):
                if page not in clause_by_page:
                    clause_by_page[page] = []
                clause_by_page[page].append(clause)

        # Link each table to nearest clause
        for table in self.tables:
            page = table.page_start
            
            if page in clause_by_page:
                page_clauses = clause_by_page[page]
                
                # Find the deepest (most specific) clause on this page
                # Prefer clauses with matching numbers (e.g., table 3.6.1 → clause 3.6.1)
                best_clause = None
                
                if table.table_number:
                    # Try exact or prefix match
                    for clause in page_clauses:
                        if clause.clause_number == table.table_number:
                            best_clause = clause
                            break
                        if table.table_number.startswith(clause.clause_number + "."):
                            best_clause = clause
                
                # If no match, use deepest clause on page
                if not best_clause and page_clauses:
                    best_clause = max(page_clauses, key=lambda c: c.level)
                
                if best_clause:
                    table.parent_clause_id = best_clause.clause_id
                    table.parent_clause_number = best_clause.clause_number
