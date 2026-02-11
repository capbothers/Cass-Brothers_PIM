"""
Queue Processor Module
Handles extraction and data processing for the Processing Queue, reusing
the existing ai_extractor, DataProcessor, and DataCleaner infrastructure
to ensure consistency with the collection workflows.
"""

import logging
import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class QueueExtractionResult:
    """Result of processing queue item extraction"""
    success: bool
    extracted_data: Optional[Dict[str, Any]] = None
    normalized_data: Optional[Dict[str, Any]] = None  # After column mapping
    raw_extraction: Optional[Dict[str, Any]] = None   # Original for audit
    error: Optional[str] = None
    source_url: Optional[str] = None
    collection: Optional[str] = None


class QueueProcessor:
    """
    Processes items in the Processing Queue using the same extraction and
    cleaning pipeline as the main collection workflows.
    """

    def __init__(self, ai_extractor, data_cleaner, sheets_manager):
        """
        Initialize with shared infrastructure components.

        Args:
            ai_extractor: AIExtractor instance for PDF/web extraction
            data_cleaner: DataCleaner instance for rule-based standardization
            sheets_manager: SheetsManager instance for column mapping
        """
        self.ai_extractor = ai_extractor
        self.data_cleaner = data_cleaner
        self.sheets_manager = sheets_manager
        self._collection_configs = {}

    def _get_collection_config(self, collection_name: str):
        """Get cached collection config"""
        if collection_name not in self._collection_configs:
            from config.collections import get_collection_config
            try:
                self._collection_configs[collection_name] = get_collection_config(collection_name)
            except ValueError:
                self._collection_configs[collection_name] = None
        return self._collection_configs[collection_name]

    def extract_from_spec_sheet(self, spec_sheet_url: str, collection_name: str,
                                 product_title: str = '', vendor: str = '') -> QueueExtractionResult:
        """
        Extract product data from a spec sheet using the collection's AI extractor.

        Uses the same extraction pipeline as the main collection workflow:
        1. AIExtractor for raw extraction
        2. DataCleaner for rule-based standardization
        3. Column mapping validation

        Args:
            spec_sheet_url: URL to the spec sheet (PDF or image)
            collection_name: Target collection key (e.g., 'toilets', 'sinks')
            product_title: Product title for context in cleaning rules
            vendor: Vendor/brand name for warranty lookup

        Returns:
            QueueExtractionResult with extracted and normalized data
        """
        try:
            logger.info(f"🔄 Queue extraction for {collection_name}: {spec_sheet_url[:60]}...")

            config = self._get_collection_config(collection_name)
            if not config:
                return QueueExtractionResult(
                    success=False,
                    error=f"Unknown collection: {collection_name}"
                )

            # Step 1: Fetch and extract using AIExtractor
            extraction_fields = getattr(config, 'ai_extraction_fields', [])
            logger.info(f"  📋 Using {len(extraction_fields)} extraction fields from collection config")

            # Try to extract using AIExtractor's methods
            raw_data = self._extract_with_ai(spec_sheet_url, collection_name, config)

            if not raw_data:
                return QueueExtractionResult(
                    success=False,
                    error="No data could be extracted from the spec sheet",
                    source_url=spec_sheet_url,
                    collection=collection_name
                )

            # Step 2: Apply data cleaning rules
            cleaned_data = self._apply_cleaning_rules(
                raw_data, collection_name, product_title, vendor
            )

            # Step 3: Normalize and validate against column mapping
            normalized_data = self._normalize_to_schema(cleaned_data, collection_name, config)

            logger.info(f"  ✅ Extracted {len(raw_data)} raw fields, cleaned to {len(cleaned_data)} fields, normalized {len(normalized_data)} fields")

            return QueueExtractionResult(
                success=True,
                extracted_data=cleaned_data,      # Cleaned, ready for display/edit
                normalized_data=normalized_data,   # Mapped to sheet columns
                raw_extraction=raw_data,           # Original for audit
                source_url=spec_sheet_url,
                collection=collection_name
            )

        except Exception as e:
            logger.error(f"❌ Queue extraction failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return QueueExtractionResult(
                success=False,
                error=str(e),
                source_url=spec_sheet_url,
                collection=collection_name
            )

    def _validate_product_type(self, spec_sheet_url: str, expected_collection: str) -> bool:
        """
        Validate that the spec sheet matches the expected product type.
        Returns True if valid, False if mismatch.
        """
        import requests as req
        from config.settings import get_settings

        settings = get_settings()
        openai_key = settings.OPENAI_API_KEY

        if not openai_key:
            return True  # Skip validation if no API key

        try:
            # Try text extraction first
            pdf_text = self._extract_text_from_pdf(spec_sheet_url)

            if pdf_text:
                # Quick text-based validation
                validation_prompt = f"""Is this spec sheet for a {self._get_collection_context(expected_collection)}?

Spec sheet content:
{pdf_text[:2000]}

Answer with ONLY 'yes' or 'no'."""
            else:
                # Fall back to image validation
                image_content = self._convert_to_image(spec_sheet_url)
                if not image_content:
                    return True  # Can't validate, proceed

                validation_prompt = f"""Is this spec sheet for a {self._get_collection_context(expected_collection)}?

Answer with ONLY 'yes' or 'no'."""

                # Use vision for validation
                payload = {
                    "model": "gpt-4o-mini",  # Use cheaper model for validation
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": validation_prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{image_content}"}
                            }
                        ]
                    }],
                    "max_tokens": 10
                }

                response = req.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {openai_key}"
                    },
                    json=payload,
                    timeout=30
                )
                response.raise_for_status()
                result = response.json()
                answer = result['choices'][0]['message']['content'].strip().lower()

                is_valid = 'yes' in answer
                if not is_valid:
                    logger.warning(f"  ⚠️  Product type mismatch: Expected {expected_collection}, spec sheet appears to be different")
                return is_valid

            # Text-based validation (simpler, no image needed)
            payload = {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": validation_prompt}],
                "max_tokens": 10
            }

            response = req.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {openai_key}"
                },
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            answer = result['choices'][0]['message']['content'].strip().lower()

            is_valid = 'yes' in answer
            if not is_valid:
                logger.warning(f"  ⚠️  Product type mismatch: Expected {expected_collection}, spec sheet appears to be different")
            return is_valid

        except Exception as e:
            logger.debug(f"  Product type validation failed: {e}")
            return True  # Proceed if validation fails

    def _extract_with_ai(self, spec_sheet_url: str, collection_name: str, config) -> Dict[str, Any]:
        """
        Perform AI extraction using the Vision API with collection-specific prompts.
        """
        import base64
        import io
        import requests as req
        from config.settings import get_settings

        settings = get_settings()
        openai_key = settings.OPENAI_API_KEY

        if not openai_key:
            raise ValueError("OpenAI API key not configured")

        # Validate product type first
        if not self._validate_product_type(spec_sheet_url, collection_name):
            logger.warning(f"  ⚠️  Skipping extraction - spec sheet doesn't match expected collection: {collection_name}")
            return {}

        # Get extraction fields from config
        extraction_fields = getattr(config, 'ai_extraction_fields', [])

        # Build collection-specific prompt
        collection_context = self._get_collection_context(collection_name)

        # Categorize fields for better prompt
        dimension_fields = [f for f in extraction_fields
                          if any(x in f for x in ['mm', 'width', 'depth', 'height', 'length', 'diameter'])]
        boolean_fields = [f for f in extraction_fields if f.startswith('is_') or f.startswith('has_')]
        other_fields = [f for f in extraction_fields if f not in dimension_fields and f not in boolean_fields]

        # Build extraction prompt
        field_list = ', '.join(other_fields[:15])
        if dimension_fields:
            field_list += f"\n- Dimensions (extract as SEPARATE numeric fields): {', '.join(dimension_fields[:12])}"
        if boolean_fields:
            field_list += f"\n- Boolean fields (true/false): {', '.join(boolean_fields)}"

        # Add standardization hints from DataCleaner rules if available
        standardization_hints = self._get_standardization_hints(collection_name)

        extraction_prompt = f"""Extract product specifications from this spec sheet for a {collection_context}.

Fields to extract:
- {field_list}
{standardization_hints}

RULES:
1. Extract each dimension as a SEPARATE numeric field (e.g., pan_width: 365)
2. Do NOT combine dimensions into single fields
3. Use numeric values for dimensions (no units)
4. Use lowercase snake_case for field names
5. Only include fields where values are clearly stated

Return as JSON object."""

        # Try text extraction first for PDFs (more reliable for structured specs)
        is_pdf = spec_sheet_url.lower().endswith('.pdf') or 'pdf' in spec_sheet_url.lower()
        pdf_text = None

        if is_pdf:
            pdf_text = self._extract_text_from_pdf(spec_sheet_url)

        # Build API request based on available content
        if pdf_text:
            # Use text-based extraction (more accurate for spec sheets with tables)
            payload = {
                "model": "gpt-4o",
                "messages": [{
                    "role": "user",
                    "content": f"{extraction_prompt}\n\nSpec sheet content:\n\n{pdf_text[:8000]}"
                }],
                "max_tokens": 2000,
                "response_format": {"type": "json_object"}
            }
        else:
            # Fall back to vision-based extraction
            image_content = self._convert_to_image(spec_sheet_url)

            if image_content:
                image_data = {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_content}"}
                }
            else:
                image_data = {
                    "type": "image_url",
                    "image_url": {"url": spec_sheet_url}
                }

            payload = {
                "model": "gpt-4o",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": extraction_prompt},
                        image_data
                    ]
                }],
                "max_tokens": 2000,
                "response_format": {"type": "json_object"}  # Force JSON responses
            }

        response = req.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {openai_key}"
            },
            json=payload,
            timeout=60
        )
        response.raise_for_status()

        result = response.json()
        content = result['choices'][0]['message']['content']

        # Parse JSON from response
        return self._parse_json_response(content)

    def _extract_text_from_pdf(self, url: str) -> Optional[str]:
        """Extract text content from PDF if available"""
        import requests as req

        try:
            pdf_response = req.get(url, timeout=30)
            pdf_response.raise_for_status()
            pdf_bytes = pdf_response.content

            # Try PyMuPDF for text extraction
            try:
                import fitz
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                text = ""
                # Extract text from first 2 pages
                for page_num in range(min(2, doc.page_count)):
                    text += doc[page_num].get_text()
                doc.close()

                # Check if we got meaningful text (at least 200 chars)
                if len(text.strip()) > 200:
                    logger.info(f"  📝 Extracted {len(text)} chars of text from PDF")
                    return text.strip()
            except ImportError:
                pass

        except Exception as e:
            logger.debug(f"  Text extraction failed: {e}")

        return None

    def _convert_to_image(self, url: str) -> Optional[str]:
        """Convert PDF to base64 image for Vision API"""
        import requests as req
        import base64
        import io

        is_pdf = url.lower().endswith('.pdf') or 'pdf' in url.lower()

        if not is_pdf:
            return None  # Use URL directly for images

        logger.info(f"  📄 Converting PDF to image: {url[:60]}...")

        try:
            pdf_response = req.get(url, timeout=30)
            pdf_response.raise_for_status()
            pdf_bytes = pdf_response.content

            # Try pdf2image first
            try:
                from pdf2image import convert_from_bytes
                images = convert_from_bytes(pdf_bytes, first_page=1, last_page=1, dpi=150)
                if images:
                    img_buffer = io.BytesIO()
                    images[0].save(img_buffer, format='PNG')
                    img_buffer.seek(0)
                    return base64.b64encode(img_buffer.read()).decode('utf-8')
            except ImportError:
                pass

            # Try PyMuPDF as fallback
            try:
                import fitz
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                if doc.page_count > 0:
                    page = doc[0]
                    mat = fitz.Matrix(2, 2)
                    pix = page.get_pixmap(matrix=mat)
                    result = base64.b64encode(pix.tobytes("png")).decode('utf-8')
                    doc.close()
                    return result
            except ImportError:
                raise ValueError("PDF conversion libraries not available")

        except Exception as e:
            logger.error(f"  ❌ PDF conversion failed: {e}")
            raise

        return None

    def _get_collection_context(self, collection_name: str) -> str:
        """Get context description for collection"""
        contexts = {
            'sinks': 'KITCHEN/LAUNDRY SINK (not bathroom basins)',
            'basins': 'BATHROOM BASIN (washbasin, vanity basin)',
            'taps': 'TAP/MIXER (kitchen or bathroom)',
            'filter_taps': 'FILTER/BOILING WATER TAP',
            'toilets': 'TOILET (close-coupled, back-to-wall, wall-hung)',
            'smart_toilets': 'SMART/BIDET TOILET',
            'showers': 'SHOWER (rail set, system, mixer)',
            'baths': 'BATH (freestanding, drop-in)',
            'hot_water': 'HOT WATER SYSTEM',
        }
        return contexts.get(collection_name, collection_name.upper().replace('_', ' '))

    def _get_standardization_hints(self, collection_name: str) -> str:
        """Get standardization hints for the prompt based on DataCleaner rules"""
        # These are key standardization rules to guide the AI
        hints = {
            'toilets': """
IMPORTANT - Use these EXACT values:
- installation_type: Close Coupled, Back To Wall, Wall Hung, Wall Faced, In-Wall
- trap_type: S-Trap, P-Trap, Skew Trap, Universal
- actuation_type: Dual Flush, Single Flush, Push Button, Sensor
- toilet_rim_design: Rimless, Standard Rim, Easy Clean Rim
- product_material: Vitreous China, Ceramic, Porcelain""",
            'sinks': """
IMPORTANT - Use these EXACT values:
- installation_type: Undermount, Topmount, Flush Mount, Farmhouse, Drop-In
- product_material: Stainless Steel, Granite, Composite, Fireclay, Ceramic
- drain_position: Centre, Left, Right, Rear Centre, Offset""",
            'basins': """
IMPORTANT - Use these EXACT values:
- installation_type: Wall Hung, Countertop, Semi-Recessed, Undermount, Pedestal, Inset
- product_material: Vitreous China, Ceramic, Stone Resin, Marble""",
            'taps': """
IMPORTANT - Use these EXACT values:
- spout_type: Fixed, Swivel, Pull-Out, Pull-Down, Gooseneck
- mounting_type: Deck Mounted, Wall Mounted, Sink Mounted""",
        }
        return hints.get(collection_name, '')

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        """Parse JSON from AI response"""
        import re
        if not content:
            logger.warning("Empty response content from AI")
            return {}

        # Try markdown code block first
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try raw JSON
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                logger.warning(f"Could not parse JSON from response: {content[:200]}")
                return {}

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return {}

    def _apply_cleaning_rules(self, data: Dict[str, Any], collection_name: str,
                              title: str, vendor: str) -> Dict[str, Any]:
        """
        Apply DataCleaner rules to standardize extracted data.
        """
        if not self.data_cleaner:
            return data

        try:
            cleaned = self.data_cleaner.clean_extracted_data(
                collection_name=collection_name,
                extracted_data=data,
                title=title,
                vendor=vendor
            )
            return cleaned
        except Exception as e:
            logger.warning(f"Data cleaning failed, using raw data: {e}")
            return data

    def _normalize_to_schema(self, data: Dict[str, Any], collection_name: str, config) -> Dict[str, Any]:
        """
        Normalize data to match the collection's column schema.
        Only includes fields that exist in the column_mapping.
        """
        if not config:
            return data

        column_mapping = getattr(config, 'column_mapping', {})
        if not column_mapping:
            return data

        normalized = {}
        valid_fields = set(column_mapping.keys())

        for field, value in data.items():
            # Check if field exists in schema
            if field in valid_fields:
                normalized[field] = value
            else:
                # Try to find a matching field (handle naming variations)
                for valid_field in valid_fields:
                    if field.lower().replace('-', '_') == valid_field.lower().replace('-', '_'):
                        normalized[valid_field] = value
                        break
                else:
                    logger.debug(f"  ⚠️ Field '{field}' not in schema, skipping")

        return normalized

    def get_collection_schema(self, collection_name: str) -> Dict[str, Any]:
        """
        Get the schema definition for a collection including:
        - ai_extraction_fields: Fields to extract
        - column_mapping: Field -> column number
        - field_types: Inferred types for UI rendering
        """
        config = self._get_collection_config(collection_name)
        if not config:
            return {'error': f'Unknown collection: {collection_name}'}

        extraction_fields = getattr(config, 'ai_extraction_fields', [])
        column_mapping = getattr(config, 'column_mapping', {})
        quality_fields = getattr(config, 'quality_fields', [])

        # Infer field types for UI
        field_types = {}
        for field in extraction_fields:
            if field.startswith('is_') or field.startswith('has_'):
                field_types[field] = 'boolean'
            elif any(x in field for x in ['mm', 'width', 'depth', 'height', 'length', 'diameter', 'capacity', 'flow', 'litres']):
                field_types[field] = 'number'
            elif 'year' in field or 'count' in field or 'number' in field:
                field_types[field] = 'number'
            elif field in column_mapping:
                field_types[field] = 'text'

        # Determine required fields (in quality_fields means it's important)
        required_fields = set(quality_fields) if quality_fields else set()

        return {
            'collection': collection_name,
            'extraction_fields': extraction_fields,
            'column_mapping': {k: v for k, v in column_mapping.items() if k in extraction_fields},
            'field_types': field_types,
            'required_fields': list(required_fields),
            'total_columns': len(column_mapping)
        }

    def validate_for_sheet(self, data: Dict[str, Any], collection_name: str) -> Dict[str, Any]:
        """
        Validate extracted data before writing to sheet.
        Returns validation result with any issues.
        """
        config = self._get_collection_config(collection_name)
        if not config:
            return {'valid': False, 'errors': [f'Unknown collection: {collection_name}']}

        errors = []
        warnings = []

        quality_fields = getattr(config, 'quality_fields', [])
        column_mapping = getattr(config, 'column_mapping', {})

        # Check required fields
        for field in quality_fields:
            if field not in data or not data[field]:
                warnings.append(f"Missing quality field: {field}")

        # Check field validity
        for field in data.keys():
            if field not in column_mapping:
                warnings.append(f"Field not in schema: {field}")

        # Validate data types
        for field, value in data.items():
            if field in column_mapping:
                # Check numeric fields
                if any(x in field for x in ['mm', 'width', 'depth', 'height', 'length', 'diameter']):
                    if value and not isinstance(value, (int, float)):
                        try:
                            float(str(value).replace(',', ''))
                        except ValueError:
                            errors.append(f"Invalid number for {field}: {value}")

        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'field_count': len(data),
            'mapped_fields': len([f for f in data.keys() if f in column_mapping])
        }


# Singleton instance
_queue_processor = None


def get_queue_processor():
    """Get or create the singleton QueueProcessor instance"""
    global _queue_processor
    if _queue_processor is None:
        from core.ai_extractor import get_ai_extractor
        from core.sheets_manager import get_sheets_manager
        from core.data_cleaner import DataCleaner

        sheets_mgr = get_sheets_manager()
        ai_extractor = get_ai_extractor()
        data_cleaner = DataCleaner(sheets_mgr)

        _queue_processor = QueueProcessor(ai_extractor, data_cleaner, sheets_mgr)

    return _queue_processor
