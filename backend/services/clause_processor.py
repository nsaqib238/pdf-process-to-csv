"""
Clause detection and processing module
"""
import re
import logging
from typing import List, Optional, Dict, Tuple
from models.clause import Clause, Note, Exception as ClauseException, ConfidenceLevel
import uuid

logger = logging.getLogger(__name__)


class ClauseProcessor:
    """Process and structure clauses from extracted text"""
    
    # Numbering patterns - improved to reject TOC and single digits
    PATTERNS = {
        # Accept clause starts with OCR noise variants:
        # *1.6.5.1, 1.4. 7, 1,6,5,1, Number: 1.4.8
        'numbered': re.compile(
            r'^\s*(?:number\s*[:\-]\s*)?\*?\s*((?:\d+(?:\s*[\.,]\s*\d+)+))\s*(?:[-:.)])?\s*(.+)$',
            re.IGNORECASE | re.MULTILINE,
        ),
        'top_level': re.compile(r'^\s*(?:number\s*[:\-]\s*)?\*?\s*(\d{1,2})\s+([A-Z].{10,})$', re.MULTILINE),  # Single/double digit with CAPS and substantive text
        'appendix': re.compile(r'^(Appendix\s+[A-Z](?:\.\d+)*)\s*[-:]?\s*(.*)$', re.IGNORECASE | re.MULTILINE),
        'letter_list': re.compile(r'^\s*\(([a-z])\)\s+(.*)$', re.MULTILINE),
        'roman_list': re.compile(r'^\s*\(([ivxlcdm]+)\)\s+(.*)$', re.IGNORECASE | re.MULTILINE),
        'bullet': re.compile(r'^\s*[•\-\*]\s+(.*)$', re.MULTILINE),
    }
    
    # Patterns to REJECT (TOC, page numbers, headers)
    REJECT_PATTERNS = [
        re.compile(r'^\d+\s*$'),  # Just a number (likely page number)
        re.compile(r'^\.{3,}'),  # Starts with dot leaders
        re.compile(r'\.{3,}\s*\d+\s*$'),  # Ends with dot leaders and page number (TOC format)
        re.compile(r'^(AS/NZS|ISO|IEC|BS|EN)\s+\d+[\d\.:\-]*\s*$', re.IGNORECASE),  # Standard titles
        re.compile(r'^page\s+\d+', re.IGNORECASE),  # Page headers
        re.compile(r'^\d+\s+(AS/NZS|ISO|IEC)', re.IGNORECASE),  # Number + standard title
    ]
    
    # Note and exception patterns - more strict, require explicit labels
    NOTE_PATTERNS = [
        re.compile(r'^\s*NOTE\s*:?\s+(.+)$', re.IGNORECASE | re.MULTILINE),  # NOTE: or NOTE
        re.compile(r'^\s*NOTES\s*:?\s+(.+)$', re.IGNORECASE | re.MULTILINE),  # NOTES: or NOTES
        re.compile(r'^\s*NOTE\s+\d+\s*:?\s+(.+)$', re.IGNORECASE | re.MULTILINE),  # NOTE 1: or NOTE 1
    ]
    
    # Exception patterns - only explicit structural exceptions, not generic text
    EXCEPTION_PATTERNS = [
        re.compile(r'^\s*EXCEPTION\s*:?\s+(.+)$', re.IGNORECASE | re.MULTILINE),
        re.compile(r'^\s*EXCEPTIONS\s*:?\s+(.+)$', re.IGNORECASE | re.MULTILINE),
        re.compile(r'^\s*Exception\s+\d+\s*:?\s+(.+)$', re.IGNORECASE | re.MULTILINE),
    ]
    
    # Conditional clause keywords (not exceptions, but related)
    CONDITIONAL_PATTERNS = [
        re.compile(r'^\s*Where\s*:?\s+(.+)$', re.MULTILINE),
        re.compile(r'^\s*However\s*,\s+(.+)$', re.MULTILINE),
        re.compile(r'^\s*Unless\s+(.+)$', re.MULTILINE),
        re.compile(r'^\s*Provided\s+that\s+(.+)$', re.IGNORECASE | re.MULTILINE),
    ]
    
    def __init__(self):
        self.clauses: List[Clause] = []
        self.clause_map: Dict[str, Clause] = {}
        self.page_map: Dict[str, int] = {}  # Store page_map for access in _build_clause
    
    def _clause_line_match(self, line: str):
        """Return first regex match if this line starts a clause (after reject checks)."""
        for rp in self.REJECT_PATTERNS:
            if rp.search(line):
                return None
        for key in ("numbered", "top_level", "appendix"):
            m = self.PATTERNS[key].match(line)
            if m:
                return m
        return None

    @staticmethod
    def _normalize_clause_number(raw: str) -> str:
        """Normalize OCR variants into canonical dotted clause numbers."""
        num = raw.strip().lstrip("*").strip()
        num = re.sub(r"\s+", "", num)
        # OCR sometimes uses commas as separators.
        num = re.sub(r"(?<=\d),(?=\d)", ".", num)
        num = re.sub(r"\.+", ".", num).strip(".")
        return num

    def process_elements(self, elements: List[Dict], page_map: Dict[str, int]) -> List[Clause]:
        """
        Process extracted elements and build clause hierarchy
        
        Args:
            elements: List of extracted text elements
            page_map: Mapping of element IDs to page numbers
            
        Returns:
            List of structured clauses
        """
        self.clauses = []
        self.clause_map = {}
        self.page_map = page_map  # Store for use in _build_clause
        
        logger.info(f"Processing {len(elements)} elements for clause extraction")
        
        # Group elements into potential clauses
        clause_candidates = self._identify_clause_candidates(elements, page_map)
        logger.info(f"Identified {len(clause_candidates)} clause candidates")
        
        # Build clause objects
        for candidate in clause_candidates:
            clause = self._build_clause(candidate)
            if clause:
                self.clauses.append(clause)
                self.clause_map[clause.clause_number] = clause
        
        # Establish parent-child relationships
        self._establish_hierarchy()
        
        # Attach notes and exceptions
        self._attach_notes_and_exceptions()
        
        logger.info(f"Processed {len(self.clauses)} clauses")
        return self.clauses
    
    def _identify_clause_candidates(self, elements: List[Dict], page_map: Dict[str, int]) -> List[Dict]:
        """Identify potential clause boundaries"""
        candidates = []
        current_candidate = None
        
        for element in elements:
            text = (element.get("Text") or element.get("text") or "").strip()
            if not text:
                continue
            _ek = element.get("Path") or element.get("id", "")
            _pg = page_map.get(_ek, element.get("Page", 1))
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

            for idx, line in enumerate(lines):
                match = self._clause_line_match(line)
                if match:
                    if current_candidate:
                        candidates.append(current_candidate)

                    clause_num = self._normalize_clause_number(match.group(1))
                    title_text = (match.group(2) or "").strip()
                    # Remove trailing OCR punctuation artifacts in titles.
                    title_text = re.sub(r"\s+[.,;:]+$", "", title_text)

                    if title_text and not re.match(r'^(AS/NZS|ISO|IEC)\s+\d+', title_text, re.IGNORECASE):
                        current_candidate = {
                            'clause_number': clause_num,
                            'title': title_text,
                            'elements': [{
                                "text": line,
                                "Page": _pg,
                                "id": f"{_ek}#line{idx}",
                            }],
                            'page_start': _pg,
                            'page_end': _pg,
                        }
                    else:
                        logger.debug(f"Rejecting clause with invalid title: {clause_num} {title_text}")
                        current_candidate = None
                elif current_candidate:
                    current_candidate['elements'].append({
                        "text": line,
                        "Page": _pg,
                        "id": f"{_ek}#line{idx}",
                    })
                    current_candidate['page_end'] = _pg
        
        # Add last candidate
        if current_candidate:
            candidates.append(current_candidate)
        
        return candidates
    
    def _build_clause(self, candidate: Dict) -> Optional[Clause]:
        """Build a Clause object from a candidate"""
        try:
            clause_number = candidate['clause_number']
            title = candidate.get('title', '')
            
            # Extract body text and track pages
            body_parts = []
            page_numbers = set([candidate['page_start']])
            
            for element in candidate['elements']:
                text = (element.get("Text") or element.get("text") or "").strip()
                if text:
                    body_parts.append(text)
                    elem_key = element.get("Path") or element.get("id", "")
                    if elem_key in self.page_map:
                        page_numbers.add(self.page_map[elem_key])
                    elif element.get("Page") is not None:
                        page_numbers.add(int(element.get("Page", 1)))
            
            # Determine actual page span
            if page_numbers:
                page_start = min(page_numbers)
                page_end = max(page_numbers)
            else:
                page_start = candidate.get('page_start', 1)
                page_end = candidate.get('page_end', 1)
            
            body_text = '\n'.join(body_parts)
            
            # Remove clause number and title from body if present
            number_pat = re.escape(clause_number).replace("\\.", r"[\.,]")
            if title:
                header_pat = rf'^\s*(?:number\s*[:\-]\s*)?\*?\s*{number_pat}\s*(?:[-:.)])?\s*{re.escape(title)}\s*'
            else:
                header_pat = rf'^\s*(?:number\s*[:\-]\s*)?\*?\s*{number_pat}\s*(?:[-:.)])?\s*'
            body_text = re.sub(
                header_pat,
                '',
                body_text,
                count=1,
                flags=re.IGNORECASE,
            ).strip()
            
            # Calculate level
            level = clause_number.count('.') + 1
            
            # Generate unique ID
            clause_id = f"clause_{uuid.uuid4().hex[:8]}"
            
            clause = Clause(
                clause_id=clause_id,
                clause_number=clause_number,
                title=title if title else None,
                level=level,
                page_start=page_start,
                page_end=page_end,
                body_with_subitems=body_text,
                full_normalized_text=f"[{clause_number}] {title}\n{body_text}",
                confidence=ConfidenceLevel.MEDIUM,
                has_body=bool(body_text.strip())
            )
            
            return clause
            
        except Exception as e:
            logger.error(f"Error building clause: {e}", exc_info=True)
            return None
    
    def _establish_hierarchy(self):
        """Establish parent-child relationships between clauses"""
        for clause in self.clauses:
            parent_num = self._find_parent_number(clause.clause_number)
            if parent_num:
                parent_clause = self.clause_map.get(parent_num)
                if parent_clause:
                    clause.parent_clause_id = parent_clause.clause_id
                    clause.parent_clause_number = parent_clause.clause_number
                    clause.has_parent = True
                else:
                    # Parent expected but not found - hierarchy issue
                    clause.has_parent = False
                    logger.warning(f"Clause {clause.clause_number} expects parent {parent_num} but not found")
            else:
                # Top-level clause (no parent expected)
                clause.has_parent = False
                clause.parent_clause_id = None
                clause.parent_clause_number = None
    
    def _find_parent_number(self, clause_number: str) -> Optional[str]:
        """Find parent clause number"""
        parts = clause_number.split('.')
        if len(parts) > 1:
            return '.'.join(parts[:-1])
        return None
    
    def _attach_notes_and_exceptions(self):
        """Detect and attach notes and exceptions to clauses"""
        for clause in self.clauses:
            text = clause.body_with_subitems
            
            # Extract notes
            notes = []
            for pattern in self.NOTE_PATTERNS:
                matches = pattern.finditer(text)
                for match in matches:
                    note_text = match.group(1).strip()
                    notes.append(Note(text=note_text, type="NOTE"))
            
            clause.notes = notes
            
            # Extract exceptions
            exceptions = []
            for pattern in self.EXCEPTION_PATTERNS:
                matches = pattern.finditer(text)
                for match in matches:
                    exception_text = match.group(1).strip() if match.groups() else match.group(0).strip()
                    exceptions.append(ClauseException(text=exception_text, type="Exception"))
            
            clause.exceptions = exceptions
    
    def get_clause_by_number(self, clause_number: str) -> Optional[Clause]:
        """Get clause by number"""
        return self.clause_map.get(clause_number)
