"""
Confidence Scoring for AI-Extracted Product Data
Scores field-level confidence and determines auto-apply vs manual review
"""

import re
from typing import Dict, Any, Tuple, Optional, List
import logging

logger = logging.getLogger(__name__)


class ConfidenceScorer:
    """Score confidence of extracted product fields"""

    # Minimum confidence threshold for auto-applying fields
    DEFAULT_THRESHOLD = 0.6

    # High-confidence threshold (very reliable extractions)
    HIGH_CONFIDENCE_THRESHOLD = 0.8

    def __init__(self, threshold: float = DEFAULT_THRESHOLD):
        """
        Initialize confidence scorer

        Args:
            threshold: Minimum confidence (0.0-1.0) for auto-applying fields
        """
        self.threshold = threshold

    def score_extracted_data(self, extracted_data: Dict[str, Any],
                             collection_name: str = None) -> Dict[str, Any]:
        """
        Score confidence for all extracted fields

        Args:
            extracted_data: Dict of field_name -> extracted_value
            collection_name: Optional collection name for collection-specific rules

        Returns:
            Dict with structure:
            {
                "overall_confidence": 0.85,
                "field_scores": {
                    "length_mm": {"value": 450, "confidence": 0.95, "auto_apply": true},
                    "material": {"value": "Stainless Steel", "confidence": 0.45, "auto_apply": false}
                },
                "auto_apply_fields": {...},  # Fields meeting threshold
                "review_fields": {...},      # Low-confidence fields for manual review
                "summary": "8/10 fields auto-applied, 2 for review"
            }
        """
        schema_filtered = self._filter_to_schema_fields(extracted_data, collection_name)

        field_scores = {}
        auto_apply_fields = {}
        review_fields = {}
        total_confidence = 0.0
        field_count = 0

        for field_name, value in schema_filtered.items():
            # Skip empty values
            if value is None or (isinstance(value, str) and not value.strip()):
                continue

            # Score the field
            confidence = self._score_field(field_name, value, collection_name)
            auto_apply = confidence >= self.threshold

            field_scores[field_name] = {
                "value": value,
                "confidence": round(confidence, 3),
                "auto_apply": auto_apply
            }

            # Route to auto_apply or review
            if auto_apply:
                auto_apply_fields[field_name] = value
            else:
                review_fields[field_name] = value

            total_confidence += confidence
            field_count += 1

        # Calculate overall confidence
        overall_confidence = total_confidence / field_count if field_count > 0 else 0.0

        # Generate summary
        auto_count = len(auto_apply_fields)
        review_count = len(review_fields)
        summary = f"{auto_count}/{field_count} fields auto-applied, {review_count} for review"

        return {
            "overall_confidence": round(overall_confidence, 3),
            "field_scores": field_scores,
            "auto_apply_fields": auto_apply_fields,
            "review_fields": review_fields,
            "summary": summary,
            "threshold": self.threshold,
            "filtered_fields": len(schema_filtered),
            "total_fields": len(extracted_data)
        }

    def _filter_to_schema_fields(self, extracted_data: Dict[str, Any],
                                 collection_name: str = None) -> Dict[str, Any]:
        """
        Filter extracted data to only fields present in the collection schema.
        """
        if not collection_name:
            return extracted_data

        try:
            from config.collections import get_collection_config
            config = get_collection_config(collection_name)
            valid_fields = set(getattr(config, 'column_mapping', {}).keys())
            if not valid_fields:
                return extracted_data

            return {k: v for k, v in extracted_data.items() if k in valid_fields}
        except Exception:
            return extracted_data

    def _score_field(self, field_name: str, value: Any, collection_name: str = None) -> float:
        """
        Score confidence for a single field

        Scoring logic:
        - Numeric measurements with units: 0.9-1.0 (very reliable)
        - Boolean fields: 0.8-0.9
        - Standardized enums (materials, types): 0.7-0.9
        - Free text (descriptions): 0.4-0.6 (low confidence, needs review)
        - Guessed/inferred values: 0.0-0.3

        Args:
            field_name: Name of the field
            value: Extracted value
            collection_name: Optional collection for context

        Returns:
            Confidence score 0.0-1.0
        """
        # Convert value to string for pattern matching
        value_str = str(value).strip()

        # Empty or placeholder values -> very low confidence
        if not value_str or value_str.lower() in ['n/a', 'unknown', 'tbd', 'null', 'none']:
            return 0.0

        # Guessed values (AI often says "approximately" or "estimated")
        guess_indicators = ['approx', 'estimated', 'about', 'around', 'roughly', '~']
        if any(indicator in value_str.lower() for indicator in guess_indicators):
            logger.debug(f"Field '{field_name}' contains guess indicator: {value_str}")
            return 0.2  # Very low confidence - reject guesses

        # Dimension fields (length_mm, width_mm, etc.)
        if self._is_dimension_field(field_name):
            return self._score_dimension(value_str)

        # Boolean fields (is_*, has_*)
        if self._is_boolean_field(field_name):
            return self._score_boolean(value_str)

        # Material fields
        if 'material' in field_name.lower():
            return self._score_material(value_str)

        # Installation/mounting type fields
        if any(keyword in field_name.lower() for keyword in ['installation', 'mounting', 'type']):
            return self._score_enum_field(value_str)

        # WELS rating, grade, warranty (structured data)
        if any(keyword in field_name.lower() for keyword in ['wels', 'rating', 'grade', 'warranty']):
            return self._score_rating_field(value_str)

        # Price fields
        if 'price' in field_name.lower():
            return self._score_price(value_str)

        # Free text fields (descriptions, features, care instructions)
        if any(keyword in field_name.lower() for keyword in ['description', 'feature', 'care', 'instruction', 'body']):
            return 0.5  # Medium confidence - should be reviewed

        # Default: medium-low confidence
        return 0.5

    def _is_dimension_field(self, field_name: str) -> bool:
        """Check if field is a dimension/measurement"""
        dimension_patterns = [
            '_mm', '_cm', '_m', '_inches', '_ft',
            'length', 'width', 'height', 'depth', 'diameter',
            'size', 'dimension', 'clearance'
        ]
        return any(pattern in field_name.lower() for pattern in dimension_patterns)

    def _is_boolean_field(self, field_name: str) -> bool:
        """Check if field is boolean"""
        return field_name.lower().startswith(('is_', 'has_', 'includes_'))

    def _score_dimension(self, value: str) -> float:
        """Score dimension/measurement fields"""
        # Numeric value (450, 1200, etc.) -> high confidence
        if re.match(r'^\d+(\.\d+)?$', value):
            return 0.95

        # Numeric with unit (450mm, 12.5cm) -> very high confidence
        if re.match(r'^\d+(\.\d+)?\s*(mm|cm|m|inches|in|ft)$', value, re.IGNORECASE):
            return 1.0

        # Range (450-500mm) -> high confidence
        if re.match(r'^\d+\s*-\s*\d+\s*(mm|cm|m|inches)?$', value, re.IGNORECASE):
            return 0.85

        # Contains non-numeric characters -> low confidence
        return 0.3

    def _score_boolean(self, value: str) -> float:
        """Score boolean fields"""
        value_lower = value.lower()

        # Clear true/false values
        if value_lower in ['true', 'false', 'yes', 'no', '1', '0']:
            return 0.9

        # Boolean-ish phrases
        if value_lower in ['included', 'not included', 'available', 'n/a']:
            return 0.75

        # Unclear boolean
        return 0.4

    def _score_material(self, value: str) -> float:
        """Score material fields"""
        # Known materials (high confidence)
        known_materials = [
            'stainless steel', 'brass', 'copper', 'ceramic', 'porcelain',
            'chrome', 'nickel', 'granite', 'quartz', 'acrylic', 'vitreous china',
            'plastic', 'pvc', 'abs', 'glass', 'stone'
        ]

        value_lower = value.lower()

        # Exact match to known material
        if value_lower in known_materials:
            return 0.9

        # Contains known material
        if any(mat in value_lower for mat in known_materials):
            return 0.8

        # Includes finish/grade info (e.g., "304 Stainless Steel")
        if re.search(r'\d{3,4}\s+stainless', value_lower):
            return 0.95

        # Vague or unknown material
        return 0.4

    def _score_enum_field(self, value: str) -> float:
        """Score enumerated fields (installation type, mounting type, etc.)"""
        # Short, standardized values (1-3 words)
        word_count = len(value.split())
        if word_count <= 3:
            return 0.8

        # Longer, descriptive values
        if word_count <= 6:
            return 0.6

        # Very long -> probably not a clean enum
        return 0.4

    def _score_rating_field(self, value: str) -> float:
        """Score rating/grade fields (WELS, warranty, etc.)"""
        # Star rating (3 star, 4.5 star)
        if re.match(r'^\d+(\.\d+)?\s*star', value, re.IGNORECASE):
            return 0.95

        # Numeric rating
        if re.match(r'^\d+(\.\d+)?$', value):
            return 0.85

        # Warranty with years (5 year, 10 years)
        if re.match(r'^\d+\s*year', value, re.IGNORECASE):
            return 0.9

        # Letter grade (A, B+, Grade A)
        if re.match(r'^(grade\s*)?[A-F][+-]?$', value, re.IGNORECASE):
            return 0.85

        # Vague or complex
        return 0.5

    def _score_price(self, value: str) -> float:
        """Score price fields"""
        # Numeric with optional currency symbol ($450, 450.00)
        if re.match(r'^[\$]?\d+(\.\d{2})?$', value):
            return 0.9

        # Contains price but with extra text
        if re.search(r'\d+', value):
            return 0.6

        return 0.3

    def reject_guessed_fields(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter out fields that appear to be guessed by the AI

        Args:
            extracted_data: Raw extracted data

        Returns:
            Filtered data with only confident extractions
        """
        filtered = {}

        for field, value in extracted_data.items():
            confidence = self._score_field(field, value)

            # Reject low-confidence fields
            if confidence >= self.threshold:
                filtered[field] = value
            else:
                logger.debug(f"Rejecting field '{field}' with confidence {confidence:.2f}: {value}")

        return filtered


# Singleton instance
_scorer_instance = None


def get_confidence_scorer(threshold: float = ConfidenceScorer.DEFAULT_THRESHOLD) -> ConfidenceScorer:
    """Get singleton confidence scorer instance"""
    global _scorer_instance
    if _scorer_instance is None or _scorer_instance.threshold != threshold:
        _scorer_instance = ConfidenceScorer(threshold=threshold)
    return _scorer_instance
