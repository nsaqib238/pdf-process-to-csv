import json
import logging
from typing import List
from pathlib import Path
from models.clause import Clause
from models.table import Table

logger = logging.getLogger(__name__)

class OutputGenerator:
    def generate_all(self, clauses: List[Clause], tables: List[Table], output_dir: str, document_title: str = "Document"):
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True, parents=True)
        txt_path = output_path / "normalized_document.txt"
        self.generate_normalized_text(clauses, tables, str(txt_path), document_title)
        clauses_path = output_path / "clauses.json"
        self.generate_clauses_json(clauses, str(clauses_path))
        tables_path = output_path / "tables.json"
        self.generate_tables_json(tables, str(tables_path))
        logger.info(f"Generated all output files in {output_dir}")
    
    def generate_normalized_text(self, clauses: List[Clause], tables: List[Table], output_path: str, document_title: str):
        lines = []
        lines.append("=" * 80)
        lines.append(f"DOCUMENT TITLE: {document_title}")
        lines.append("=" * 80)
        lines.append("")
        lines.append("CLAUSES")
        lines.append("=" * 80)
        lines.append("")
        for clause in clauses:
            lines.append("[CLAUSE]")
            lines.append(f"Number: {clause.clause_number}")
            if clause.title:
                lines.append(f"Title: {clause.title}")
            if clause.parent_clause_number:
                lines.append(f"Parent: {clause.parent_clause_number}")
            lines.append(f"Level: {clause.level}")
            lines.append(f"Pages: {clause.page_start}-{clause.page_end}")
            lines.append(f"Confidence: {clause.confidence}")
            lines.append("")
            lines.append("Body:")
            lines.append(clause.body_with_subitems)
            lines.append("")
            if clause.notes:
                lines.append("Notes:")
                for note in clause.notes:
                    lines.append(f"  * {note.type}: {note.text}")
                lines.append("")
            if clause.exceptions:
                lines.append("Exceptions:")
                for exc in clause.exceptions:
                    lines.append(f"  * {exc.type}: {exc.text}")
                lines.append("")
            lines.append("-" * 80)
            lines.append("")
        if tables:
            lines.append("")
            lines.append("TABLES")
            lines.append("=" * 80)
            lines.append("")
            for table in tables:
                lines.append("[TABLE]")
                if table.table_number:
                    lines.append(f"Number: {table.table_number}")
                if table.title:
                    lines.append(f"Title: {table.title}")
                if table.parent_clause_reference:
                    lines.append(f"Parent Clause: {table.parent_clause_reference}")
                lines.append(f"Pages: {table.page_start}-{table.page_end}")
                lines.append(f"Confidence: {table.confidence}")
                lines.append("")
                lines.append(table.normalized_text_representation)
                lines.append("")
                if table.footer_notes:
                    lines.append("Footer Notes:")
                    for note in table.footer_notes:
                        lines.append(f"  * {note}")
                    lines.append("")
                lines.append("-" * 80)
                lines.append("")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        logger.info(f"Generated normalized text: {output_path}")
    
    def generate_clauses_json(self, clauses: List[Clause], output_path: str):
        clauses_data = [clause.model_dump() for clause in clauses]
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(clauses_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Generated clauses JSON: {output_path} ({len(clauses)} clauses)")
    
    def generate_tables_json(self, tables: List[Table], output_path: str):
        recon_keys = (
            "reconstructed_header_rows",
            "promoted_header_rows",
            "final_columns",
            "header_model",
            "reconstruction_confidence",
            "reconstruction_notes",
        )

        def table_to_json_dict(table: Table) -> dict:
            d = table.model_dump()
            for k in recon_keys:
                if d.get(k) is None:
                    d.pop(k, None)
            return d

        tables_data = [table_to_json_dict(table) for table in tables]
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(tables_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Generated tables JSON: {output_path} ({len(tables)} tables)")
