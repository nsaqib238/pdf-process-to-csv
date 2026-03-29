"""
Document zone classifier - identifies different sections of a document
Prevents front matter, TOC, headers/footers from being parsed as clauses
"""
import re
import logging
from typing import List, Dict, Tuple
from collections import Counter

logger = logging.getLogger(__name__)


class DocumentZone:
    """Document zone types"""
    COVER = "cover"
    PREFACE = "preface"
    FOREWORD = "foreword"
    CONTENTS = "contents"
    AMENDMENT = "amendment"
    BODY = "body"
    APPENDIX = "appendix"
    INDEX = "index"
    REFERENCES = "references"
    HEADER_FOOTER = "header_footer"
    UNKNOWN = "unknown"


class DocumentZoneClassifier:
    """Classifies pages/sections into document zones"""
    COVER_EXCLUSION_MAX_PAGE = 3
    
    # Keywords for zone detection
    ZONE_KEYWORDS = {
        DocumentZone.COVER: [
            r'\b(standard|specification|code of practice)\b',
            r'\bAS/NZS\s+\d+',
            r'\bISO\s+\d+',
            r'\bcopyright\b'
        ],
        DocumentZone.PREFACE: [
            r'^\s*preface\s*$',
            r'^\s*foreword\s*$',
            r'^\s*acknowledgements?\s*$',
            r'^\s*introduction\s*$'
        ],
        DocumentZone.CONTENTS: [
            r'^\s*contents?\s*$',
            r'^\s*table\s+of\s+contents\s*$',
            r'\.{3,}',  # Dot leaders
            r'\b\d+\s*$'  # Page numbers at end of line
        ],
        DocumentZone.AMENDMENT: [
            r'^\s*amendments?\s*$',
            r'^\s*revision\s+history\s*$',
            r'^\s*changes\s+in\s+this\s+edition\s*$',
            r'significant\s+changes?\s+have\s+been\s+made'
        ],
        DocumentZone.APPENDIX: [
            r'^\s*appendix\s+[A-Z]\b',
            r'^\s*annex\s+[A-Z]\b'
        ],
        DocumentZone.INDEX: [
            r'^\s*index\s*$',
            r'^\s*glossary\s*$'
        ],
        DocumentZone.REFERENCES: [
            r'^\s*references?\s*$',
            r'^\s*bibliography\s*$',
            r'^\s*normative\s+references\s*$'
        ]
    }
    
    # TOC specific patterns
    TOC_PATTERNS = [
        re.compile(r'^[\d\.]+\s+.+\.{3,}\s*\d+\s*$', re.MULTILINE),  # 1.1 Title ... 33
        re.compile(r'^.+\.{5,}\s*\d+\s*$', re.MULTILINE),  # Any text ..... 12
        re.compile(r'^\d+\.\d+\s+[A-Z\s]+\s+\.{3,}\s+\d+$', re.MULTILINE)  # 1.1 SCOPE ... 33
    ]
    
    # Header/footer noise patterns
    NOISE_PATTERNS = [
        re.compile(r'^(AS/NZS|ISO|IEC|BS|EN)\s+\d+[\d\.:]*\s*$', re.IGNORECASE),
        re.compile(r'^\s*page\s+\d+\s*$', re.IGNORECASE),
        re.compile(r'^\s*\d+\s*$'),  # Just a number
        re.compile(r'^©\s*\d{4}\b'),  # Copyright
        re.compile(r'^\s*(draft|confidential|preliminary)\s*$', re.IGNORECASE)
    ]
    
    def __init__(self):
        self.zone_history: List[str] = []
        self.page_zones: Dict[int, str] = {}
        self.repeated_strings: Counter = Counter()
        
    def classify_pages(self, pages: List[Dict]) -> Dict[int, str]:
        """
        Classify each page into a document zone
        
        Args:
            pages: List of page dictionaries with 'page' number and 'text' content
            
        Returns:
            Dictionary mapping page number to zone type
        """
        logger.info(f"Classifying {len(pages)} pages into document zones")
        
        # First pass: detect repeated strings (headers/footers)
        self._detect_repeated_strings(pages)
        
        # Second pass: classify each page
        for page_data in pages:
            page_num = page_data.get('page', 1)
            text = page_data.get('text', '')
            
            zone = self._classify_single_page(text, page_num)
            self.page_zones[page_num] = zone
            self.zone_history.append(zone)
        
        # Post-process: refine zones based on context
        self._refine_zones()
        
        zone_summary = Counter(self.page_zones.values())
        logger.info(f"Zone classification complete: {dict(zone_summary)}")
        
        return self.page_zones
    
    def _detect_repeated_strings(self, pages: List[Dict]):
        """Detect strings that appear on multiple pages (likely headers/footers)"""
        # Count lines across all pages
        line_counts = Counter()
        
        for page_data in pages:
            text = page_data.get('text', '')
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            
            # Only count short lines (likely headers/footers)
            for line in lines:
                if len(line) < 100:  # Headers/footers are usually short
                    line_counts[line] += 1
        
        # Store strings that appear on many pages
        threshold = max(3, len(pages) * 0.2)  # At least 3 times or 20% of pages
        self.repeated_strings = Counter({
            text: count for text, count in line_counts.items()
            if count >= threshold
        })
        
        logger.info(f"Detected {len(self.repeated_strings)} repeated strings (headers/footers)")
    
    def _classify_single_page(self, text: str, page_num: int) -> str:
        """Classify a single page"""
        text_lower = text.lower()
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Very short pages are likely noise or separators
        if len(lines) < 3:
            return DocumentZone.HEADER_FOOTER
        
        # Check for TOC patterns
        if self._is_toc_page(text, lines):
            return DocumentZone.CONTENTS
        
        # Check for specific zone keywords
        for zone, patterns in self.ZONE_KEYWORDS.items():
            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE | re.MULTILINE):
                    # Extra validation for certain zones
                    if zone == DocumentZone.CONTENTS:
                        if self._is_toc_page(text, lines):
                            return zone
                    else:
                        return zone
        
        # Check position in document
        if page_num <= 10:
            # First 10 pages are likely front matter unless proven otherwise
            if self._looks_like_body_content(text, lines):
                return DocumentZone.BODY
            else:
                return DocumentZone.PREFACE
        
        # Check for appendix (usually later in document)
        if re.search(r'^\s*appendix\s+[A-Z]', text, re.IGNORECASE | re.MULTILINE):
            return DocumentZone.APPENDIX
        
        # Default to body if it looks like clause content
        if self._looks_like_body_content(text, lines):
            return DocumentZone.BODY
        
        return DocumentZone.UNKNOWN
    
    def _is_toc_page(self, text: str, lines: List[str]) -> bool:
        """Check if page is a table of contents"""
        # Check for TOC heading
        if re.search(r'^\s*contents?\s*$', text, re.IGNORECASE | re.MULTILINE):
            return True
        
        # Check for multiple TOC-style lines
        toc_line_count = 0
        for line in lines:
            for pattern in self.TOC_PATTERNS:
                if pattern.match(line):
                    toc_line_count += 1
                    break
        
        # If more than 30% of lines look like TOC entries
        if len(lines) > 5 and toc_line_count / len(lines) > 0.3:
            return True
        
        # Check for dot leaders
        dot_leader_count = sum(1 for line in lines if '...' in line or '···' in line)
        if dot_leader_count >= 3:
            return True
        
        return False
    
    def _looks_like_body_content(self, text: str, lines: List[str]) -> bool:
        """Check if page looks like main body content with real clauses"""
        # Look for hierarchical numbering (1.1, 2.3.4, etc.) - lowered threshold
        hierarchical_pattern = re.compile(r'^\d+\.\d+(?:\.\d+)*\s+\w', re.MULTILINE)
        matches = hierarchical_pattern.findall(text)
        
        # Even one hierarchical number suggests body content
        if len(matches) >= 1:  # Changed from 2 to 1
            return True
        
        # Check for substantial paragraph content
        long_lines = [line for line in lines if len(line) > 50]
        if len(long_lines) >= 3:  # Changed from 5 to 3
            return True
        
        return False
    
    def _refine_zones(self):
        """Refine zones based on context and sequence"""
        # Convert to list for easier manipulation
        pages = sorted(self.page_zones.keys())
        
        for i, page_num in enumerate(pages):
            current_zone = self.page_zones[page_num]
            
            # If unknown, infer from neighbors
            if current_zone == DocumentZone.UNKNOWN:
                prev_zone = self.page_zones.get(pages[i-1]) if i > 0 else None
                next_zone = self.page_zones.get(pages[i+1]) if i < len(pages)-1 else None
                
                # If surrounded by same zone, adopt it
                if prev_zone == next_zone and prev_zone is not None:
                    self.page_zones[page_num] = prev_zone
                elif prev_zone and prev_zone != DocumentZone.HEADER_FOOTER:
                    self.page_zones[page_num] = prev_zone
        
        # Once we hit body, most subsequent pages are body or appendix
        body_started = False
        for page_num in pages:
            if self.page_zones[page_num] == DocumentZone.BODY:
                body_started = True
            elif body_started and self.page_zones[page_num] == DocumentZone.UNKNOWN:
                self.page_zones[page_num] = DocumentZone.BODY
    
    def is_parseable_zone(self, zone: str, page_num: int = 1) -> bool:
        """Check if zone should be parsed for clauses"""
        if zone in [DocumentZone.BODY, DocumentZone.APPENDIX, DocumentZone.UNKNOWN]:
            return True
        # Pages 4+ still labeled "cover" are usually misclassified (headers mention AS/NZS everywhere).
        if zone == DocumentZone.COVER and page_num > self.COVER_EXCLUSION_MAX_PAGE:
            return True
        return False
    
    def should_exclude_from_clauses(self, zone: str, page_num: int = 1) -> bool:
        """Check if zone should be excluded from clause parsing"""
        # TOC and preface are always excluded.
        if zone in [DocumentZone.CONTENTS, DocumentZone.PREFACE]:
            return True

        # Cover is excluded only in early pages to avoid over-filtering body pages.
        if zone == DocumentZone.COVER:
            return page_num <= self.COVER_EXCLUSION_MAX_PAGE

        # Keep other high-noise zones excluded.
        return zone in [
            DocumentZone.FOREWORD,
            DocumentZone.AMENDMENT,
            DocumentZone.INDEX,
            DocumentZone.HEADER_FOOTER,
            DocumentZone.REFERENCES
        ]
    
    def filter_elements_by_zone(self, elements: List[Dict], page_map: Dict[str, int]) -> List[Dict]:
        """Filter elements to only include those from parseable zones"""
        filtered = []
        
        for element in elements:
            lookup = element.get("Path") or element.get("id", "")
            page_num = page_map.get(lookup)
            if page_num is None:
                page_num = element.get("Page", 1)
            zone = self.page_zones.get(page_num, DocumentZone.UNKNOWN)
            
            if self.should_exclude_from_clauses(zone, page_num):
                continue

            if self.is_parseable_zone(zone, page_num):
                filtered.append(element)
        
        logger.info(f"Filtered {len(elements)} elements to {len(filtered)} (parseable zones only)")
        return filtered
    
    def clean_text(self, text: str) -> str:
        """Remove repeated headers/footers from text"""
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            
            # Skip if it's a repeated string
            if line_stripped in self.repeated_strings:
                continue
            
            # Skip if it matches noise patterns
            is_noise = False
            for pattern in self.NOISE_PATTERNS:
                if pattern.match(line_stripped):
                    is_noise = True
                    break
            
            if not is_noise:
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)
