"""
AI-powered table detection and validation using OpenAI Vision and Chat APIs.

This module implements three AI strategies to improve table extraction:
1. AI-Assisted Table Discovery: Find tables missed by geometric detection
2. AI-Powered Caption Detection: Handle non-standard caption formats
3. AI-Based Structure Validation: Fix malformed extractions and reject prose

See AI_ENHANCEMENT_PLAN.md for full architecture details.
"""

import base64
import json
import logging
import time
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class TableRegion:
    """AI-discovered table region with metadata."""
    bbox_percent: Dict[str, float]  # {"top": 15, "left": 10, "bottom": 45, "right": 90}
    table_number: Optional[str]
    description: str
    confidence: str  # "high", "medium", "low"
    caption_format: str  # "standard", "implicit", "none"
    page_num: int


@dataclass
class TableReference:
    """AI-detected table reference in text."""
    table_number: Optional[str]
    reference_type: str  # "explicit_caption", "implicit_reference", "continuation", "inline_reference"
    text_snippet: str
    is_continuation: bool
    confidence: str  # "high", "medium", "low"
    page_num: int


@dataclass
class ValidationResult:
    """AI validation result for table structure."""
    is_table: bool
    confidence: str  # "high", "medium", "low"
    reasoning: str
    structure_correct: bool
    suggested_corrections: List[Dict[str, Any]]
    token_usage: Dict[str, int]


@dataclass
class AICallMetrics:
    """Track AI API usage for cost monitoring."""
    discovery_calls: int = 0
    discovery_tables_found: int = 0
    caption_calls: int = 0
    caption_new_anchors: int = 0
    validation_calls: int = 0
    validation_accepted: int = 0
    validation_rejected: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    errors: int = 0


class AITableService:
    """
    AI-powered table detection and validation service.
    
    Integrates with OpenAI APIs to enhance deterministic table extraction pipeline.
    """
    
    def __init__(self):
        """Initialize AI service with configuration."""
        self.metrics = AICallMetrics()
        self.call_count = 0
        
        logger.info("Initializing AI Table Service...")
        
        try:
            from config import settings
            self.settings = settings
            
            # Check if AI features are enabled
            self.discovery_enabled = bool(getattr(settings, "enable_ai_table_discovery", False))
            self.caption_enabled = bool(getattr(settings, "enable_ai_caption_detection", False))
            self.validation_enabled = bool(getattr(settings, "enable_ai_structure_validation", False))
            
            logger.info(f"AI feature flags from .env:")
            logger.info(f"  - ENABLE_AI_TABLE_DISCOVERY: {self.discovery_enabled}")
            logger.info(f"  - ENABLE_AI_CAPTION_DETECTION: {self.caption_enabled}")
            logger.info(f"  - ENABLE_AI_STRUCTURE_VALIDATION: {self.validation_enabled}")
            
            # Get configuration
            self.api_key = getattr(settings, "openai_api_key", None)
            self.model = getattr(settings, "openai_model", "gpt-4o")
            self.max_retries = int(getattr(settings, "openai_max_retries", 3))
            self.timeout = int(getattr(settings, "openai_timeout_seconds", 60))
            self.max_calls = int(getattr(settings, "ai_max_calls_per_job", 100))
            self.discovery_threshold = float(getattr(settings, "ai_discovery_confidence_threshold", 0.7))
            self.validation_threshold = float(getattr(settings, "ai_validation_quality_threshold", 0.6))
            self.log_tokens = bool(getattr(settings, "ai_log_token_usage", True))
            self.cost_alert_threshold = float(getattr(settings, "ai_alert_cost_threshold", 5.0))
            
            if self.api_key:
                logger.info(f"  - OpenAI API key: {'*' * 10}{self.api_key[-8:] if len(self.api_key) > 8 else '***'}")
            else:
                logger.warning("  - OpenAI API key: NOT SET")
            
            # Initialize OpenAI client if any AI feature is enabled
            self.client = None
            if (self.discovery_enabled or self.caption_enabled or self.validation_enabled):
                if not self.api_key:
                    logger.warning(
                        "⚠️  AI features enabled but OPENAI_API_KEY not set. "
                        "AI enhancement will be skipped."
                    )
                else:
                    logger.info("Attempting to initialize OpenAI client...")
                    self._initialize_openai()
            else:
                logger.info("No AI features enabled. Skipping OpenAI initialization.")
        
        except Exception as e:
            logger.error(f"❌ AI service initialization failed: {e}", exc_info=True)
            logger.warning("AI features will be disabled.")
            self.discovery_enabled = False
            self.caption_enabled = False
            self.validation_enabled = False
            self.client = None
    
    def _initialize_openai(self):
        """Initialize OpenAI client."""
        try:
            from openai import OpenAI
            logger.info(f"Creating OpenAI client with model: {self.model}")
            self.client = OpenAI(
                api_key=self.api_key,
                timeout=self.timeout,
                max_retries=self.max_retries
            )
            logger.info(f"✅ OpenAI client initialized successfully with model: {self.model}")
        except ImportError:
            logger.error(
                "❌ OpenAI SDK not installed. Run: pip install openai\n"
                "AI features will be disabled."
            )
            self.client = None
        except Exception as e:
            logger.error(f"❌ Failed to initialize OpenAI client: {e}", exc_info=True)
            self.client = None
    
    def _can_make_call(self) -> bool:
        """Check if we can make another API call within limits."""
        if self.call_count >= self.max_calls:
            logger.warning(
                f"AI call limit reached ({self.max_calls}). "
                f"Skipping further AI calls for this job."
            )
            return False
        
        if self.metrics.total_cost_usd >= self.cost_alert_threshold:
            logger.warning(
                f"AI cost threshold reached (${self.metrics.total_cost_usd:.2f}). "
                f"Consider increasing ai_alert_cost_threshold or reducing AI usage."
            )
        
        return True
    
    def _encode_image_base64(self, image: Image.Image) -> str:
        """Encode PIL Image to base64 string."""
        buffered = BytesIO()
        image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    
    def _estimate_cost(self, prompt_tokens: int, completion_tokens: int, is_vision: bool = False) -> float:
        """
        Estimate API call cost based on token usage.
        
        OpenAI GPT-4o pricing (as of 2024):
        - Text input: $2.50 per 1M tokens
        - Vision input: $2.50 per 1M tokens
        - Output: $10 per 1M tokens
        """
        input_cost = (prompt_tokens / 1_000_000) * 2.50
        output_cost = (completion_tokens / 1_000_000) * 10.0
        return input_cost + output_cost
    
    def _call_vision_api(
        self,
        image: Image.Image,
        prompt: str,
        response_format: str = "json_object"
    ) -> Optional[Dict[str, Any]]:
        """
        Call OpenAI Vision API with image and prompt.
        
        Returns parsed JSON response or None on failure.
        """
        if not self.client or not self._can_make_call():
            return None
        
        try:
            self.call_count += 1
            
            # Encode image
            image_base64 = self._encode_image_base64(image)
            
            # Make API call
            start_time = time.time()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_base64}"
                                }
                            }
                        ]
                    }
                ],
                response_format={"type": response_format},
                temperature=0.0,  # Deterministic output
                max_tokens=2000
            )
            elapsed = time.time() - start_time
            
            # Extract response
            content = response.choices[0].message.content
            usage = response.usage
            
            # Update metrics
            self.metrics.total_tokens += usage.total_tokens
            cost = self._estimate_cost(usage.prompt_tokens, usage.completion_tokens, is_vision=True)
            self.metrics.total_cost_usd += cost
            
            if self.log_tokens:
                logger.info(
                    f"Vision API call completed in {elapsed:.2f}s. "
                    f"Tokens: {usage.total_tokens} (${cost:.4f})"
                )
            
            # Parse JSON response
            try:
                return json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Vision API JSON response: {e}")
                logger.debug(f"Raw response: {content}")
                self.metrics.errors += 1
                return None
        
        except Exception as e:
            logger.error(f"Vision API call failed: {e}")
            self.metrics.errors += 1
            return None
    
    def _call_chat_api(
        self,
        prompt: str,
        response_format: str = "json_object"
    ) -> Optional[Dict[str, Any]]:
        """
        Call OpenAI Chat API with text prompt.
        
        Returns parsed JSON response or None on failure.
        """
        if not self.client or not self._can_make_call():
            return None
        
        try:
            self.call_count += 1
            
            # Make API call
            start_time = time.time()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": response_format},
                temperature=0.0,  # Deterministic output
                max_tokens=1500
            )
            elapsed = time.time() - start_time
            
            # Extract response
            content = response.choices[0].message.content
            usage = response.usage
            
            # Update metrics
            self.metrics.total_tokens += usage.total_tokens
            cost = self._estimate_cost(usage.prompt_tokens, usage.completion_tokens, is_vision=False)
            self.metrics.total_cost_usd += cost
            
            if self.log_tokens:
                logger.info(
                    f"Chat API call completed in {elapsed:.2f}s. "
                    f"Tokens: {usage.total_tokens} (${cost:.4f})"
                )
            
            # Parse JSON response
            try:
                return json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Chat API JSON response: {e}")
                logger.debug(f"Raw response: {content}")
                self.metrics.errors += 1
                return None
        
        except Exception as e:
            logger.error(f"Chat API call failed: {e}")
            self.metrics.errors += 1
            return None
    
    def discover_tables(
        self,
        page_image: Image.Image,
        page_num: int,
        existing_table_bboxes: List[Tuple[float, float, float, float]] = None
    ) -> List[TableRegion]:
        """
        Use AI vision to discover tables missed by geometric detection.
        
        Args:
            page_image: PIL Image of PDF page
            page_num: Page number (1-indexed)
            existing_table_bboxes: List of already-detected table bboxes to avoid duplicates
        
        Returns:
            List of discovered table regions
        """
        if not self.discovery_enabled or not self.client:
            return []
        
        # Build prompt
        prompt = f"""You are analyzing page {page_num} from a technical standards document (AS/NZS 3000:2018).

TASK: Identify ONLY TABLES on this page - structured data in rows and columns.

WHAT TO INCLUDE:
- Tables with clear gridlines
- Tables with minimal or no gridlines (spacing-based)
- Tables embedded in text sections
- Tables with non-standard captions

WHAT TO EXCLUDE (CRITICAL - DO NOT MARK THESE AS TABLES):
❌ Clause text (e.g., "3.8.1 General requirements...")
❌ Paragraphs and body text (even if formatted with indents)
❌ Numbered lists or bullet points
❌ Section headings and subheadings
❌ Definitions or glossary entries
❌ Figures, diagrams, or images
❌ Running headers/footers
❌ Page numbers
❌ Single-column content that is not tabular

A TABLE MUST HAVE:
✓ Multiple columns of structured data
✓ Rows representing distinct data records
✓ Clear visual or spacing-based grid structure
✓ Data values, not continuous prose

For each table found, provide:
- Approximate bounding box (top, left, bottom, right as percentages of page height/width, 0-100)
- Table number if visible (e.g., "Table 3.2", "TABLE D12(A)", "3.8")
- Brief description
- Confidence level ("high", "medium", "low")
- Caption format: "standard" (explicit "Table X"), "implicit" (no clear caption), or "none"

OUTPUT FORMAT (JSON):
{{
  "tables": [
    {{
      "bbox_percent": {{"top": 15, "left": 10, "bottom": 45, "right": 90}},
      "table_number": "3.8",
      "description": "Wire sizing requirements table",
      "confidence": "high",
      "caption_format": "standard"
    }}
  ]
}}

REMEMBER: When in doubt, DO NOT mark it as a table. We only want structured tabular data, not clause text.
If no tables found, return {{"tables": []}}
"""
        
        # Call Vision API
        response = self._call_vision_api(page_image, prompt)
        
        if not response or "tables" not in response:
            return []
        
        # Parse response
        discovered = []
        for table_data in response["tables"]:
            try:
                region = TableRegion(
                    bbox_percent=table_data["bbox_percent"],
                    table_number=table_data.get("table_number"),
                    description=table_data.get("description", ""),
                    confidence=table_data.get("confidence", "medium"),
                    caption_format=table_data.get("caption_format", "none"),
                    page_num=page_num
                )
                
                # Filter by confidence threshold
                confidence_scores = {"high": 1.0, "medium": 0.7, "low": 0.4}
                if confidence_scores.get(region.confidence, 0) >= self.discovery_threshold:
                    discovered.append(region)
                    self.metrics.discovery_tables_found += 1
            
            except (KeyError, ValueError) as e:
                logger.warning(f"Failed to parse table region: {e}")
                continue
        
        self.metrics.discovery_calls += 1
        
        if discovered:
            logger.info(
                f"AI discovered {len(discovered)} table(s) on page {page_num}: "
                f"{[r.table_number or 'unnumbered' for r in discovered]}"
            )
        
        return discovered
    
    def detect_captions(
        self,
        page_text: str,
        page_num: int
    ) -> List[TableReference]:
        """
        Use AI text analysis to find table references including implicit captions.
        
        Args:
            page_text: Extracted text from PDF page
            page_num: Page number (1-indexed)
        
        Returns:
            List of detected table references
        """
        if not self.caption_enabled or not self.client:
            return []
        
        # Skip if text is too short
        if len(page_text.strip()) < 50:
            return []
        
        # Build prompt
        prompt = f"""You are analyzing text from page {page_num} of AS/NZS 3000:2018.

TASK: Find all references to tables, including:
1. Explicit captions: "Table 3.2", "TABLE D12(A)", etc.
2. Implicit references: "the following table", "as shown in the table below"
3. Continuation markers: "(continued)", "Table 3.2 cont."
4. Table references in body text: "refer to Table 3.8"

For each reference, provide:
- Table number (if explicit, otherwise null)
- Reference type: "explicit_caption", "implicit_reference", "continuation", "inline_reference"
- Text snippet (verbatim excerpt from source)
- Continuation: true if this is a continuation of a previous table
- Confidence level ("high", "medium", "low")

OUTPUT FORMAT (JSON):
{{
  "references": [
    {{
      "table_number": "3.8",
      "type": "explicit_caption",
      "text_snippet": "Table 3.8—Maximum demand",
      "is_continuation": false,
      "confidence": "high"
    }}
  ]
}}

RULES:
- Only include actual table references, not general mentions
- For implicit references without numbers, set table_number to null
- Extract text snippets verbatim (do not paraphrase)
- If no references found, return {{"references": []}}

TEXT TO ANALYZE:
{page_text[:3000]}"""  # Limit to first 3000 chars to control token usage
        
        # Call Chat API
        response = self._call_chat_api(prompt)
        
        if not response or "references" not in response:
            return []
        
        # Parse response
        references = []
        for ref_data in response["references"]:
            try:
                ref = TableReference(
                    table_number=ref_data.get("table_number"),
                    reference_type=ref_data.get("type", "inline_reference"),
                    text_snippet=ref_data.get("text_snippet", ""),
                    is_continuation=ref_data.get("is_continuation", False),
                    confidence=ref_data.get("confidence", "medium"),
                    page_num=page_num
                )
                references.append(ref)
            
            except (KeyError, ValueError) as e:
                logger.warning(f"Failed to parse table reference: {e}")
                continue
        
        self.metrics.caption_calls += 1
        
        if references:
            explicit_count = sum(1 for r in references if r.reference_type == "explicit_caption")
            implicit_count = len(references) - explicit_count
            logger.info(
                f"AI detected {len(references)} table reference(s) on page {page_num}: "
                f"{explicit_count} explicit, {implicit_count} implicit"
            )
            self.metrics.caption_new_anchors += len(references)
        
        return references
    
    def validate_structure(
        self,
        table_json: Dict[str, Any],
        page_crop_image: Image.Image,
        quality_score: float,
        quality_issues: List[str]
    ) -> Optional[ValidationResult]:
        """
        Use AI vision to validate table structure and suggest corrections.
        
        Args:
            table_json: Current table structure (matching Table model)
            page_crop_image: PIL Image of cropped table region
            quality_score: Unified quality score (0-1)
            quality_issues: List of quality concern descriptions
        
        Returns:
            ValidationResult or None if validation skipped
        """
        if not self.validation_enabled or not self.client:
            return None
        
        # Only validate borderline cases
        if quality_score >= self.validation_threshold:
            return None
        
        row_count = len(table_json.get("data_rows", []))
        col_count = len(table_json.get("data_rows", [[]])[0].get("cells", [])) if row_count > 0 else 0
        
        # Build prompt
        prompt = f"""You are validating a table extraction from a technical standards document.

CONTEXT:
- Extracted table has {row_count} rows and {col_count} columns
- Quality score: {quality_score:.2f} (borderline - threshold: {self.validation_threshold})
- Concerns: {', '.join(quality_issues) if quality_issues else 'Low quality score'}

IMAGE: [cropped table region shown above]

CURRENT STRUCTURE (JSON):
{json.dumps(table_json, indent=2)[:1500]}

TASK:
1. Is this ACTUALLY a table? (vs clause text, list, diagram, or prose)
2. If YES - is the structure correct?
   - Are columns properly detected?
   - Are headers correctly identified?
   - Are there merged cells or multi-row headers?
3. If structure needs correction, provide specific fixes

OUTPUT FORMAT (JSON):
{{
  "is_table": true,
  "confidence": "high",
  "reasoning": "Clear grid structure with 3 columns and numeric data",
  "structure_correct": false,
  "suggested_corrections": [
    {{
      "issue": "Header row should span rows 0-1",
      "fix_type": "header_merge",
      "details": {{"header_row_count": 2}}
    }}
  ]
}}

RULES:
- Reject clause text even if formatted in columns (look for prose flow, normative language)
- Accept sparse tables if clear grid structure exists
- Do NOT modify cell content, only structure
- Be conservative: only suggest corrections if clearly needed
- If structure is acceptable, return "structure_correct": true with empty corrections list
"""
        
        # Call Vision API
        response = self._call_vision_api(page_crop_image, prompt)
        
        if not response:
            return None
        
        try:
            result = ValidationResult(
                is_table=response.get("is_table", True),
                confidence=response.get("confidence", "medium"),
                reasoning=response.get("reasoning", ""),
                structure_correct=response.get("structure_correct", True),
                suggested_corrections=response.get("suggested_corrections", []),
                token_usage={"total": 0}  # Updated in _call_vision_api
            )
            
            self.metrics.validation_calls += 1
            
            if result.is_table:
                self.metrics.validation_accepted += 1
                logger.info(
                    f"AI validated table (score: {quality_score:.2f}). "
                    f"Structure correct: {result.structure_correct}"
                )
            else:
                self.metrics.validation_rejected += 1
                logger.info(
                    f"AI rejected table as non-table: {result.reasoning}"
                )
            
            return result
        
        except (KeyError, ValueError) as e:
            logger.error(f"Failed to parse validation result: {e}")
            self.metrics.errors += 1
            return None
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get AI usage metrics for job."""
        return {
            "ai_discovery_calls": self.metrics.discovery_calls,
            "ai_discovery_tables_found": self.metrics.discovery_tables_found,
            "ai_caption_calls": self.metrics.caption_calls,
            "ai_caption_new_anchors": self.metrics.caption_new_anchors,
            "ai_validation_calls": self.metrics.validation_calls,
            "ai_validation_accepted": self.metrics.validation_accepted,
            "ai_validation_rejected": self.metrics.validation_rejected,
            "ai_total_tokens": self.metrics.total_tokens,
            "ai_total_cost_usd": round(self.metrics.total_cost_usd, 4),
            "ai_errors": self.metrics.errors,
            "ai_model": self.model if self.client else None
        }
    
    def reset_metrics(self):
        """Reset metrics for new job."""
        self.metrics = AICallMetrics()
        self.call_count = 0


# Global instance
_ai_service_instance: Optional[AITableService] = None


def get_ai_service() -> AITableService:
    """Get or create global AI service instance."""
    global _ai_service_instance
    if _ai_service_instance is None:
        _ai_service_instance = AITableService()
    return _ai_service_instance
