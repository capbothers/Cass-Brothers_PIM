"""
Page Extractors Module
Extracts product specifications directly from supplier product pages (HTML)
before falling back to PDF spec sheets.

This provides more reliable extraction for suppliers with structured spec tables
on their product pages.
"""

import logging
import re
from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup
import requests

logger = logging.getLogger(__name__)


class PageExtractor:
    """
    Extract product specifications from supplier product pages.

    Uses supplier-specific patterns to find and parse spec tables,
    key-value pairs, and structured data from HTML.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; CassBrothersPIM/1.0; +https://cassbrothers.com.au)'
        })

    def extract_specs(self, product_url: str, supplier_hint: str = None) -> Dict[str, Any]:
        """
        Extract specifications from a product page.

        Args:
            product_url: URL of the product page
            supplier_hint: Supplier domain hint (e.g., 'abey.com.au')

        Returns:
            Dictionary of extracted specifications
        """
        try:
            logger.info(f"🔍 Extracting specs from product page: {product_url[:60]}...")

            # Fetch page
            response = self.session.get(product_url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            # Extract page title early
            title = self._extract_title(soup)

            # Use supplier-specific extraction if hint provided
            if supplier_hint:
                specs = self._extract_supplier_specific(soup, product_url, supplier_hint)
                if specs:
                    # If only image is found, try generic extraction for specs
                    if len(specs) == 1 and 'shopify_images' in specs:
                        generic_specs = self._extract_generic(soup)
                        if generic_specs:
                            specs.update(generic_specs)
                    if title and 'title' not in specs:
                        specs['title'] = title
                    logger.info(f"  ✅ Extracted {len(specs)} fields from page")
                    return specs

            # Generic extraction as fallback
            specs = self._extract_generic(soup)

            if specs:
                if title and 'title' not in specs:
                    specs['title'] = title
                logger.info(f"  ✅ Extracted {len(specs)} fields from page")
            else:
                logger.warning(f"  ⚠️  No specs found on page")

            return specs

        except Exception as e:
            logger.error(f"  ❌ Page extraction failed: {e}")
            return {}

    def _extract_supplier_specific(self, soup: BeautifulSoup, url: str, supplier: str) -> Dict[str, Any]:
        """Extract using supplier-specific patterns"""
        supplier_lower = supplier.lower()

        if 'abey' in supplier_lower:
            return self._extract_abey(soup)

        return {}

    def _extract_abey(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Extract specs from Abey.com.au product pages.

        Abey typically has spec tables with the following structure:
        - <div class="product-specifications"> or similar
        - <table> with rows of label/value pairs
        - Key-value lists in <ul> or <dl> tags
        """
        specs = {}

        # Strategy 1: Find specification tables
        spec_sections = soup.find_all(['div', 'section'], class_=re.compile(r'spec|detail|info', re.I))

        for section in spec_sections:
            # Look for tables
            tables = section.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True)

                        if label and value:
                            field_name = self._normalize_field_name(label)
                            field_value = self._normalize_field_value(value)
                            if field_name and field_value:
                                specs[field_name] = field_value

        # Strategy 2: Find definition lists
        dls = soup.find_all('dl')
        for dl in dls:
            dts = dl.find_all('dt')
            dds = dl.find_all('dd')

            for dt, dd in zip(dts, dds):
                label = dt.get_text(strip=True)
                value = dd.get_text(strip=True)

                if label and value:
                    field_name = self._normalize_field_name(label)
                    field_value = self._normalize_field_value(value)
                    if field_name and field_value:
                        specs[field_name] = field_value

        # Strategy 3: Find labeled divs/spans
        labeled_elements = soup.find_all(['div', 'span', 'p'], class_=re.compile(r'spec-|attribute-|detail-', re.I))
        for elem in labeled_elements:
            # Try to find label and value
            label_elem = elem.find(['span', 'strong', 'b'], class_=re.compile(r'label|name|title', re.I))
            value_elem = elem.find(['span', 'div'], class_=re.compile(r'value|data', re.I))

            if label_elem and value_elem:
                label = label_elem.get_text(strip=True)
                value = value_elem.get_text(strip=True)

                if label and value:
                    field_name = self._normalize_field_name(label)
                    field_value = self._normalize_field_value(value)
                    if field_name and field_value:
                        specs[field_name] = field_value

        # Strategy 4: Look for JSON-LD structured data
        json_ld_specs = self._extract_json_ld(soup)
        if json_ld_specs:
            specs.update(json_ld_specs)

        # Clean up and normalize
        return self._clean_specs(specs)

    def _extract_generic(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Generic extraction for any product page"""
        specs = {}

        # Try to find any tables that look like spec tables
        tables = soup.find_all('table')
        for table in tables:
            # Look for 2-column tables
            rows = table.find_all('tr')
            if len(rows) > 3:  # Likely a spec table
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) == 2:
                        label = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True)

                        if label and value and len(label) < 50:
                            field_name = self._normalize_field_name(label)
                            field_value = self._normalize_field_value(value)
                            if field_name and field_value:
                                specs[field_name] = field_value

        # Try JSON-LD
        json_ld_specs = self._extract_json_ld(soup)
        if json_ld_specs:
            specs.update(json_ld_specs)

        return self._clean_specs(specs)

    def _extract_json_ld(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract specs from JSON-LD structured data"""
        import json

        specs = {}
        scripts = soup.find_all('script', type='application/ld+json')

        for script in scripts:
            try:
                data = json.loads(script.string)

                # Handle Product schema
                if isinstance(data, dict) and data.get('@type') == 'Product':
                    # Extract basic product info
                    if data.get('name'):
                        specs['title'] = data.get('name')
                    if 'brand' in data:
                        if isinstance(data['brand'], dict):
                            specs['brand_name'] = data['brand'].get('name')
                        else:
                            specs['brand_name'] = data['brand']

                    if 'material' in data:
                        specs['product_material'] = data['material']

                    # Extract primary product image (conservative)
                    image = data.get('image')
                    if image:
                        if isinstance(image, list) and image:
                            specs['shopify_images'] = image[0]
                        elif isinstance(image, str):
                            specs['shopify_images'] = image

                    # Extract from additionalProperty
                    if 'additionalProperty' in data:
                        for prop in data['additionalProperty']:
                            if isinstance(prop, dict):
                                name = prop.get('name', '')
                                value = prop.get('value', '')
                                if name and value:
                                    field_name = self._normalize_field_name(name)
                                    specs[field_name] = value

            except (json.JSONDecodeError, AttributeError):
                continue

        return specs

    def _normalize_field_name(self, label: str) -> Optional[str]:
        """
        Normalize field labels to standard field names.

        Maps common labels to our standard field names:
        - "Dimensions" -> extract width/depth/height
        - "Material" -> "product_material"
        - "Installation" -> "installation_type"
        - etc.
        """
        label_lower = label.lower().strip()

        # Dimension fields
        if 'overall width' in label_lower or label_lower == 'width':
            return 'overall_width_mm'
        if 'overall depth' in label_lower or 'overall length' in label_lower or label_lower == 'depth' or label_lower == 'length':
            return 'overall_depth_mm'
        if 'overall height' in label_lower or label_lower == 'height':
            return 'overall_height_mm'

        # Bowl dimensions
        if 'bowl width' in label_lower:
            return 'bowl_width_mm'
        if 'bowl depth' in label_lower or 'bowl length' in label_lower:
            return 'bowl_depth_mm'
        if 'bowl height' in label_lower:
            return 'bowl_height_mm'

        # Material
        if label_lower in ['material', 'materials', 'product material']:
            return 'product_material'
        if 'grade' in label_lower:
            return 'grade_of_material'

        # Installation
        if 'installation' in label_lower or 'mounting' in label_lower:
            return 'installation_type'

        # Finish
        if 'finish' in label_lower or 'colour' in label_lower or 'color' in label_lower:
            return 'colour_finish'

        # Warranty
        if 'warranty' in label_lower:
            return 'warranty_years'

        # Drain/overflow
        if 'drain' in label_lower and 'position' in label_lower:
            return 'drain_position'
        if 'overflow' in label_lower:
            return 'has_overflow'

        # Bowls
        if 'bowl' in label_lower and 'number' in label_lower:
            return 'bowls_number'

        # Cabinet size
        if 'cabinet' in label_lower and 'size' in label_lower:
            return 'min_cabinet_size_mm'

        # Cutout
        if 'cutout' in label_lower:
            return 'cutout_size_mm'

        # Brand
        if 'brand' in label_lower or 'manufacturer' in label_lower:
            return 'brand_name'

        # Title
        if label_lower == 'title' or label_lower == 'name':
            return 'title'

        # Generic conversion: lowercase, replace spaces/dashes with underscores
        normalized = re.sub(r'[^\w\s-]', '', label_lower)
        normalized = re.sub(r'[\s-]+', '_', normalized)

        # Skip very short or very long field names
        if len(normalized) < 2 or len(normalized) > 50:
            return None

        return normalized

    def _normalize_field_value(self, value: str) -> Optional[str]:
        """Normalize and clean field values"""
        if not value:
            return None

        value = value.strip()

        # Skip empty or placeholder values
        if value.lower() in ['n/a', '-', 'tbd', 'tbc', 'varies', 'various']:
            return None

        # Extract numeric values from dimension strings
        # e.g., "500mm" -> "500", "500 x 400" -> "500x400"
        if 'mm' in value.lower():
            # Extract just the numbers
            numbers = re.findall(r'\d+\.?\d*', value)
            if numbers:
                if len(numbers) == 1:
                    return numbers[0]
                else:
                    # Multiple dimensions, keep as-is for now
                    return value.replace('mm', '').strip()

        # Boolean values
        if value.lower() in ['yes', 'true', 'included']:
            return 'true'
        if value.lower() in ['no', 'false', 'not included']:
            return 'false'

        # Clean up whitespace
        value = re.sub(r'\s+', ' ', value)

        return value

    def _clean_specs(self, specs: Dict[str, Any]) -> Dict[str, Any]:
        """Final cleanup of extracted specs"""
        cleaned = {}

        for key, value in specs.items():
            # Skip None/empty values
            if value is None or value == '':
                continue

            # Parse dimension strings like "L360 x W360 x D160"
            if isinstance(value, str) and re.search(r'[lwdh]\s*\d', value.lower()) and 'x' in value.lower():
                parsed = self._parse_dimension_string(value)
                if parsed:
                    cleaned.update(parsed)
                    continue

            # Convert dimension strings to numbers if possible
            if key.endswith('_mm') and isinstance(value, str):
                # Try to extract single number
                numbers = re.findall(r'\d+\.?\d*', value)
                if len(numbers) == 1:
                    try:
                        cleaned[key] = float(numbers[0]) if '.' in numbers[0] else int(numbers[0])
                        continue
                    except ValueError:
                        pass

            # Convert boolean strings
            if isinstance(value, str):
                if value.lower() == 'true':
                    cleaned[key] = True
                    continue
                elif value.lower() == 'false':
                    cleaned[key] = False
                    continue

                # Convert numeric strings to numbers
                if re.fullmatch(r'\d+(\.\d+)?', value.strip()):
                    cleaned[key] = float(value) if '.' in value else int(value)
                    continue

                # Validate product image URLs
                if key == 'shopify_images':
                    if value.startswith('http://') or value.startswith('https://'):
                        cleaned[key] = value
                        continue
                    # Drop non-URL values
                    continue

            # Keep as-is
            cleaned[key] = value

        return cleaned

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract product title from common page elements."""
        # Try h1 first
        h1 = soup.find('h1')
        if h1:
            title = h1.get_text(strip=True)
            if title:
                return title

        # Fallback to og:title
        og = soup.find('meta', property='og:title')
        if og and og.get('content'):
            return og.get('content').strip()

        # Fallback to document title
        if soup.title and soup.title.string:
            return soup.title.string.strip()

        return None

    def _parse_dimension_string(self, dim_str: str) -> Dict[str, Any]:
        """
        Parse dimension strings like "L360 x W360 x D160" into separate fields.
        """
        matches = re.findall(r'([LWDH])\s*:?\\s*(\\d+\\.?\\d*)', dim_str, re.IGNORECASE)
        if not matches:
            return {}

        result = {}
        for label, value in matches:
            label = label.upper()
            try:
                number = float(value) if '.' in value else int(value)
            except ValueError:
                continue

            if label == 'L':
                result['overall_depth_mm'] = number
            elif label == 'W':
                result['overall_width_mm'] = number
            elif label == 'D':
                result['overall_height_mm'] = number
            elif label == 'H':
                result['overall_height_mm'] = number

        return result


# Singleton instance
_page_extractor = None


def get_page_extractor():
    """Get or create the singleton PageExtractor instance"""
    global _page_extractor
    if _page_extractor is None:
        _page_extractor = PageExtractor()
    return _page_extractor
