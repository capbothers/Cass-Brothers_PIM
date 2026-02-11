"""
Data Validation & Confidence Scoring for Metafield Enrichment

Validates extracted metafield values before pushing to Shopify by:
1. Detecting duplicate/conflicting tag values
2. Range-checking numeric fields (dimensions, warranty)
3. Validating against known-good value lists (materials, colours)
4. Cross-validating between supplier data and Shopify tags
5. Producing a confidence score (0.0-1.0) per field

Products scoring below the confidence threshold go to a review queue
instead of being auto-pushed.
"""

import re
import logging
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)

# ============================================================
# Known-good value lists for bathroom/kitchen products
# ============================================================

KNOWN_MATERIALS = {
    'stainless steel', '316 stainless steel', '304 stainless steel',
    '316 marine grade stainless steel', 'brushed stainless steel',
    'brass', 'solid brass', 'zinc alloy', 'copper', 'cast iron',
    'aluminium', 'aluminum', 'chrome plated brass',
    'solid surface', 'engineered stone', 'natural stone', 'marble',
    'granite', 'quartz', 'terrazzo', 'concrete', 'composite',
    'mineralcast', 'mineral cast',
    'ceramic', 'fine ceramic', 'porcelain', 'vitreous china',
    'fireclay', 'fine fireclay',
    'acrylic', 'lucite acrylic', 'abs', 'polypropylene',
    'thermoplastic', 'resin', 'polymarble',
    'glass', 'tempered glass', 'toughened glass', 'frosted glass',
    'timber', 'bamboo', 'wood', 'oak', 'teak',
    'silicone', 'rubber', 'epdm', 'pvc',
}

KNOWN_COLOURS = {
    'black', 'white', 'grey', 'gray', 'silver', 'gold', 'red',
    'blue', 'green', 'beige', 'cream', 'ivory', 'tan', 'brown',
    'chrome', 'brushed nickel', 'satin nickel', 'polished nickel',
    'matte black', 'matt black', 'brushed gold', 'polished gold',
    'rose gold', 'brushed brass', 'aged brass', 'antique brass',
    'brushed bronze', 'oil rubbed bronze', 'gunmetal', 'pewter',
    'brushed gunmetal', 'polished chrome', 'satin chrome',
    'brushed chrome', 'matte white', 'matt white', 'gloss white',
    'polished stainless steel', 'brushed stainless steel',
    'matte', 'matt', 'gloss', 'satin', 'polished', 'brushed',
    'honed', 'textured', 'hammered',
    'black & gold', 'chrome & white', 'black & chrome',
    'white & chrome', 'black & brushed gold',
}

# Words indicating a material (not a colour)
MATERIAL_INDICATORS = {
    'steel', 'brass', 'copper', 'iron', 'aluminium', 'aluminum',
    'ceramic', 'porcelain', 'acrylic', 'stone', 'timber', 'wood',
    'glass', 'fireclay', 'marble', 'granite', 'quartz', 'resin',
    'silicone', 'rubber', 'abs', 'pvc', 'composite', 'vitreous',
    'mineralcast',
}

# Colour words that are OK even when a material indicator is present
COLOUR_EXCEPTIONS = {
    'black', 'white', 'grey', 'gray', 'gold', 'silver', 'chrome',
    'bronze', 'gunmetal', 'pewter', 'nickel', 'rose',
}

DIMENSION_RANGES = {
    'overall_width_mm': (10.0, 5000.0),
    'overall_depth_mm': (10.0, 3000.0),
    'overall_height_mm': (5.0, 3000.0),
}

WARRANTY_RANGE = (1, 100)


# ============================================================
# Tag Parser with duplicate detection
# ============================================================

def parse_tags_with_duplicates(tags_str: str) -> Dict[str, List[str]]:
    """
    Parse Shopify tags, preserving ALL values for duplicate keys.
    Returns dict of lowercase_key -> [list of values].
    """
    result = {}
    if not tags_str:
        return result

    for tag in tags_str.split(','):
        tag = tag.strip()
        if ':' in tag:
            key, _, value = tag.partition(':')
            key = key.strip()
            value = value.strip()
            if value and value not in ('', ' '):
                key_lower = key.lower()
                if key_lower not in result:
                    result[key_lower] = []
                result[key_lower].append(value)

    return result


def pick_best_tag_value(key: str, values: List[str]) -> Tuple[str, float]:
    """
    When a tag key has multiple values, pick the best one.
    Returns (best_value, confidence_penalty).
    """
    if len(values) == 1:
        return values[0], 0.0

    unique_values = list(dict.fromkeys(values))

    if len(unique_values) == 1:
        return unique_values[0], 0.0

    # For dimensions, pick the most common
    if any(k in key for k in ('width', 'depth', 'height', 'length')):
        from collections import Counter
        counts = Counter(values)
        best = counts.most_common(1)[0][0]
        return best, 0.3

    # For material/colour, pick the longest (most specific)
    if any(k in key for k in ('material', 'sinkmaterial', 'colour', 'color', 'finish')):
        best = max(unique_values, key=len)
        return best, 0.3

    # For mount/installation, join values
    if any(k in key for k in ('sinkmount', 'mounting', 'installation', 'mount', 'fixing')):
        combined = ' / '.join(unique_values)
        return combined, 0.2

    return unique_values[0], 0.3


# ============================================================
# Field-level validation
# ============================================================

def validate_dimension(value: str, field_key: str) -> Tuple[bool, str, float]:
    """Validate a dimension value. Returns (is_valid, cleaned_value, confidence_adj)."""
    match = re.search(r'(\d+(?:\.\d+)?)', value)
    if not match:
        return False, '', -1.0

    num = float(match.group(1))
    min_val, max_val = DIMENSION_RANGES.get(field_key, (1.0, 10000.0))

    if num < min_val or num > max_val or num == 0:
        return False, '', -1.0

    confidence = 0.1 if 50 <= num <= 2500 else 0.0
    cleaned = f"{num:.1f}" if num != int(num) else f"{int(num)}.0"
    return True, cleaned, confidence


def validate_material(value: str) -> Tuple[bool, str, float]:
    """Validate a material value. Returns (is_valid, cleaned_value, confidence_adj)."""
    cleaned = value.strip()
    if not cleaned:
        return False, '', -1.0

    lower = cleaned.lower()

    if lower in KNOWN_MATERIALS:
        return True, cleaned, 0.2

    for mat in KNOWN_MATERIALS:
        if mat in lower:
            return True, cleaned, 0.1

    return True, cleaned, -0.1


def validate_colour(value: str) -> Tuple[bool, str, float]:
    """
    Validate a colour/finish value.
    Detects when a material has been misclassified as a colour.
    """
    cleaned = value.strip()
    if not cleaned:
        return False, '', -1.0

    lower = cleaned.lower()

    # Check if this is actually a material
    for indicator in MATERIAL_INDICATORS:
        if indicator in lower:
            has_colour_word = any(cw in lower for cw in COLOUR_EXCEPTIONS)
            if not has_colour_word:
                return True, cleaned, -0.4  # Heavy penalty

    if lower in KNOWN_COLOURS:
        return True, cleaned, 0.2

    for colour in KNOWN_COLOURS:
        if colour in lower:
            return True, cleaned, 0.1

    return True, cleaned, 0.0


def validate_warranty(value: str) -> Tuple[bool, str, float]:
    """Validate warranty years."""
    match = re.search(r'(\d+)', value)
    if not match:
        return False, '', -1.0

    years = int(match.group(1))
    if years < WARRANTY_RANGE[0] or years > WARRANTY_RANGE[1]:
        return False, '', -1.0

    boost = 0.1 if years in (1, 2, 3, 5, 7, 10, 15, 20, 25, 50) else 0.0
    return True, str(years), boost


def validate_installation(value: str) -> Tuple[bool, str, float]:
    """Validate installation type."""
    cleaned = value.strip()
    if not cleaned:
        return False, '', -1.0

    known_types = {
        'wall mount', 'wall mounted', 'wall hung',
        'floor mount', 'floor mounted', 'freestanding', 'free standing',
        'countertop', 'counter top', 'above counter', 'above-counter',
        'undermount', 'under mount', 'under-mount',
        'topmount', 'top mount', 'top-mount', 'inset',
        'flushmount', 'flush mount', 'flush-mount',
        'drop-in', 'drop in', 'recessed', 'semi-recessed',
        'pedestal', 'console',
    }

    lower = cleaned.lower()
    for known in known_types:
        if known in lower:
            return True, cleaned, 0.1

    return True, cleaned, 0.0


# ============================================================
# Cross-validation
# ============================================================

def cross_validate_sources(
    supplier_value: Optional[str],
    tag_value: Optional[str],
    field_key: str,
) -> Tuple[Optional[str], float]:
    """
    Compare supplier data vs Shopify tag value.
    Returns (best_value, confidence_adjustment).
    """
    has_supplier = bool(supplier_value and supplier_value.strip())
    has_tag = bool(tag_value and tag_value.strip())

    if not has_supplier and not has_tag:
        return None, 0.0
    if has_supplier and not has_tag:
        return supplier_value.strip(), 0.0
    if has_tag and not has_supplier:
        return tag_value.strip(), 0.0

    s_val = supplier_value.strip()
    t_val = tag_value.strip()

    # Numeric comparison
    if field_key in ('overall_width_mm', 'overall_depth_mm', 'overall_height_mm'):
        s_m = re.search(r'(\d+(?:\.\d+)?)', s_val)
        t_m = re.search(r'(\d+(?:\.\d+)?)', t_val)
        if s_m and t_m:
            if abs(float(s_m.group(1)) - float(t_m.group(1))) < 2:
                return s_val, 0.3  # Agree
            return s_val, -0.3  # Disagree

    # Text comparison
    if s_val.lower() == t_val.lower():
        return s_val, 0.3

    if s_val.lower() in t_val.lower() or t_val.lower() in s_val.lower():
        return max(s_val, t_val, key=len), 0.1

    return s_val, -0.3


# ============================================================
# Validation result and pipeline
# ============================================================

class ValidationResult:
    """Result of validating a single metafield value."""

    def __init__(self, field_key: str, value: str, confidence: float,
                 source: str = '', issues: List[str] = None):
        self.field_key = field_key
        self.value = value
        self.confidence = max(0.0, min(1.0, confidence))
        self.source = source
        self.issues = issues or []

    def __repr__(self):
        status = 'OK' if self.confidence >= 0.7 else 'REVIEW' if self.confidence >= 0.4 else 'REJECT'
        return f"{self.field_key}={self.value!r} conf={self.confidence:.2f} [{status}] {self.issues}"


def validate_metafield(
    field_key: str,
    value: str,
    field_type: str,
    source: str = 'tag',
    tag_duplicates: int = 0,
    supplier_value: Optional[str] = None,
    tag_value: Optional[str] = None,
) -> ValidationResult:
    """
    Validate a single metafield value and produce a confidence score.
    """
    base_confidence = 0.6
    issues = []

    # Penalty for duplicate tags
    if tag_duplicates > 1:
        penalty = min(0.3, (tag_duplicates - 1) * 0.15)
        base_confidence -= penalty
        issues.append(f"duplicate_tags:{tag_duplicates}")

    # Field-specific validation
    if field_key in DIMENSION_RANGES:
        is_valid, cleaned, adj = validate_dimension(value, field_key)
        if not is_valid:
            return ValidationResult(field_key, value, 0.0, source, ['invalid_dimension'])
        value = cleaned
        base_confidence += adj

    elif field_key == 'material':
        is_valid, cleaned, adj = validate_material(value)
        if not is_valid:
            return ValidationResult(field_key, value, 0.0, source, ['invalid_material'])
        value = cleaned
        base_confidence += adj

    elif field_key == 'colour_finish':
        is_valid, cleaned, adj = validate_colour(value)
        if not is_valid:
            return ValidationResult(field_key, value, 0.0, source, ['invalid_colour'])
        value = cleaned
        base_confidence += adj
        if adj < -0.2:
            issues.append('material_as_colour')

    elif field_key == 'warranty_years':
        is_valid, cleaned, adj = validate_warranty(value)
        if not is_valid:
            return ValidationResult(field_key, value, 0.0, source, ['invalid_warranty'])
        value = cleaned
        base_confidence += adj

    elif field_key == 'installation_type':
        is_valid, cleaned, adj = validate_installation(value)
        if not is_valid:
            return ValidationResult(field_key, value, 0.0, source, ['invalid_installation'])
        value = cleaned
        base_confidence += adj

    elif field_key == 'brand_name':
        if source == 'brand':
            base_confidence = 0.9
        else:
            base_confidence += 0.1

    # Cross-validation
    if supplier_value or tag_value:
        _, cross_adj = cross_validate_sources(supplier_value, tag_value, field_key)
        base_confidence += cross_adj
        if cross_adj < 0:
            issues.append('source_conflict')
        elif cross_adj > 0.2:
            issues.append('source_agreement')

    if source == 'both':
        base_confidence += 0.1

    return ValidationResult(field_key, value, base_confidence, source, issues)


def validate_product_metafields(
    new_metafields: Dict[str, str],
    shopify_tags_str: str,
    supplier_specs: Dict[str, str],
    metafield_schema: Dict[str, Dict],
    brand_source: bool = False,
) -> Dict[str, ValidationResult]:
    """
    Validate all proposed metafield updates for a single product.

    Args:
        new_metafields: Dict of metafield_key -> proposed value
        shopify_tags_str: Raw Shopify tags string
        supplier_specs: Parsed supplier specs dict
        metafield_schema: The METAFIELD_SCHEMA dict from gap_analysis
        brand_source: Whether brand_name came from vendor field
    """
    tag_groups = parse_tags_with_duplicates(shopify_tags_str)

    results = {}

    for mf_key, value in new_metafields.items():
        mf_config = metafield_schema.get(mf_key, {})
        mf_type = mf_config.get('type', 'single_line_text_field')

        # Count duplicate tag values for this field
        extract_keys = mf_config.get('extract_from', [])
        tag_dup_count = 0
        tag_value = None
        for ek in extract_keys:
            ek_lower = ek.lower()
            if ek_lower in tag_groups:
                vals = tag_groups[ek_lower]
                if len(vals) > tag_dup_count:
                    tag_dup_count = len(vals)
                if len(vals) == 1:
                    tag_value = vals[0]
                else:
                    tag_value, _ = pick_best_tag_value(ek_lower, vals)

        # Find supplier value
        supplier_value = None
        supplier_lower = {k.lower(): v for k, v in supplier_specs.items()}
        for ek in extract_keys:
            if ek.lower() in supplier_lower:
                supplier_value = supplier_lower[ek.lower()]
                break

        # Determine source
        source = 'tag'
        if mf_key == 'brand_name' and brand_source:
            source = 'brand'
        elif supplier_value and tag_value:
            source = 'both'
        elif supplier_value:
            source = 'supplier'

        result = validate_metafield(
            field_key=mf_key,
            value=value,
            field_type=mf_type,
            source=source,
            tag_duplicates=tag_dup_count,
            supplier_value=supplier_value,
            tag_value=tag_value,
        )
        results[mf_key] = result

    return results


def filter_by_confidence(
    validation_results: Dict[str, ValidationResult],
    auto_push_threshold: float = 0.7,
    reject_threshold: float = 0.3,
) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
    """
    Split validated metafields into three buckets based on confidence.

    Returns:
        (auto_push, needs_review, rejected) - each Dict[key -> value]
    """
    auto_push = {}
    needs_review = {}
    rejected = {}

    for key, result in validation_results.items():
        if result.confidence >= auto_push_threshold:
            auto_push[key] = result.value
        elif result.confidence >= reject_threshold:
            needs_review[key] = result.value
        else:
            rejected[key] = result.value

    return auto_push, needs_review, rejected


# ============================================================
# Legacy DataValidator class (backward compatible)
# ============================================================

class DataValidator:
    """Legacy validator for existing code that uses the class-based API."""

    def __init__(self):
        self.dimension_bounds = {'min': 1, 'max': 10000}
        self.price_bounds = {'min': 0.01, 'max': 1000000}
        self.warranty_bounds = {'min': 0, 'max': 100}

    def validate_product_data(self, data, collection=None):
        errors = []
        warnings = []

        for field in ['overall_width_mm', 'overall_depth_mm', 'overall_height_mm']:
            if field in data and data[field] is not None:
                try:
                    val = float(data[field])
                    if val <= 0:
                        errors.append(f"{field}: must be positive")
                    elif val > self.dimension_bounds['max']:
                        errors.append(f"{field}: unreasonably large ({val}mm)")
                except (ValueError, TypeError):
                    errors.append(f"{field}: invalid type")

        if 'warranty_years' in data and data['warranty_years'] is not None:
            try:
                val = float(data['warranty_years'])
                if val < 0:
                    errors.append("warranty_years: negative")
                elif val > self.warranty_bounds['max']:
                    warnings.append(f"warranty_years: unusually long ({val})")
            except (ValueError, TypeError):
                errors.append("warranty_years: invalid type")

        return len(errors) == 0, errors, warnings

    def sanitize_data(self, data):
        return {k: v.strip() if isinstance(v, str) else v
                for k, v in data.items() if v is not None and v != ''}


_data_validator = None

def get_data_validator():
    global _data_validator
    if _data_validator is None:
        _data_validator = DataValidator()
    return _data_validator
