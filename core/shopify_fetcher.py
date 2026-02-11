"""
Shopify Data Fetcher

Fetches existing product data from Shopify to enable gap-filling and error correction.
"""

import logging
import requests
from typing import Dict, Any, Optional, List
import os
import time

logger = logging.getLogger(__name__)


class ShopifyFetcher:
    """
    Fetch and manage Shopify product data.

    Enables:
    - Fetching existing product data by SKU
    - Identifying empty/missing fields
    - Comparing with extracted data
    - Smart merging for gap-filling and error correction
    """

    def __init__(self, shop_url: str = None, access_token: str = None):
        """
        Initialize Shopify fetcher.

        Args:
            shop_url: Shopify store URL (e.g., 'your-store.myshopify.com')
            access_token: Shopify Admin API access token
        """
        from config.settings import get_settings

        settings = get_settings()

        settings_shop_url = getattr(settings, 'SHOPIFY_SHOP_URL', None)
        settings_access_token = getattr(settings, 'SHOPIFY_ACCESS_TOKEN', None)
        shopify_config = getattr(settings, 'SHOPIFY_CONFIG', {}) or {}

        self.shop_url = shop_url or settings_shop_url or shopify_config.get('SHOP_URL', '')
        self.access_token = access_token or settings_access_token or shopify_config.get('ACCESS_TOKEN', '')

        if not self.shop_url or not self.access_token:
            logger.warning("⚠️  Shopify credentials not configured")
            logger.warning("   Set SHOPIFY_SHOP_URL and SHOPIFY_ACCESS_TOKEN in .env")

        self.api_version = shopify_config.get('API_VERSION', '2024-01')
        self.base_url = f'https://{self.shop_url}/admin/api/{self.api_version}'

        self.session = requests.Session()
        self.session.headers.update({
            'X-Shopify-Access-Token': self.access_token,
            'Content-Type': 'application/json'
        })

        # Rate limiting
        self.requests_made = 0
        self.last_request_time = 0
        self.rate_limit_delay = 0.5  # 2 requests/second

    def get_product_by_sku(self, sku: str) -> Optional[Dict[str, Any]]:
        """
        Get product from Shopify by SKU.

        Args:
            sku: Product SKU/variant SKU

        Returns:
            Product data dict or None if not found
        """
        try:
            if not self.shop_url or not self.access_token:
                logger.warning("⚠️  Shopify credentials not configured; skipping Shopify fetch")
                return None

            # Rate limiting
            self._rate_limit()

            # Search for product by SKU
            # Note: Shopify API searches variants, not just products
            url = f"{self.base_url}/products.json"
            params = {'limit': 1}

            # First try to find by variant SKU
            variant_url = f"{self.base_url}/variants.json"
            response = self.session.get(variant_url, params={'sku': sku})
            response.raise_for_status()

            variants = response.json().get('variants', [])

            if not variants:
                logger.debug(f"  Product not found in Shopify: {sku}")
                return None

            variant = variants[0]
            product_id = variant['product_id']

            # Get full product details
            product_url = f"{self.base_url}/products/{product_id}.json"
            response = self.session.get(product_url)
            response.raise_for_status()

            product = response.json().get('product', {})

            # Extract relevant data
            return self._normalize_product_data(product, variant)

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.debug(f"  Product not found: {sku}")
                return None
            logger.error(f"  HTTP error fetching {sku}: {e}")
            return None
        except Exception as e:
            logger.error(f"  Error fetching product {sku}: {e}")
            return None

    def _normalize_product_data(self, product: Dict[str, Any], variant: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize Shopify product data to our schema.

        Extracts:
        - Basic product info (title, vendor, etc.)
        - Metafields (dimensions, specs, etc.)
        - Variant info
        """
        # Helper to safely convert to float
        def safe_float(value, default=0.0):
            if value is None or value == '':
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default

        normalized = {
            'shopify_product_id': product.get('id'),
            'shopify_variant_id': variant.get('id'),
            'title': product.get('title'),
            'vendor': product.get('vendor'),
            'product_type': product.get('product_type'),
            'sku': variant.get('sku'),
            'shopify_price': safe_float(variant.get('price'), 0),
            'shopify_compare_price': safe_float(variant.get('compare_at_price')) if variant.get('compare_at_price') else None,
            'shopify_weight': variant.get('weight'),
            'body_html': product.get('body_html'),
            'tags': product.get('tags', '').split(',') if product.get('tags') else [],
        }

        # Extract images
        images = product.get('images', [])
        if images:
            normalized['shopify_images'] = images[0].get('src')

        # Extract metafields (dimensions, specs stored as metafields)
        # Note: Would need to fetch metafields separately in production
        # For now, return normalized product data

        return normalized

    def find_empty_fields(self, product_data: Dict[str, Any], field_list: List[str] = None) -> List[str]:
        """
        Find empty/missing fields in product data.

        Args:
            product_data: Product data dict
            field_list: Optional list of fields to check (if None, checks all common fields)

        Returns:
            List of field names that are empty/missing
        """
        if field_list is None:
            # Common fields to check
            field_list = [
                'overall_width_mm', 'overall_depth_mm', 'overall_height_mm',
                'bowl_width_mm', 'bowl_depth_mm', 'bowl_height_mm',
                'product_material', 'installation_type', 'warranty_years',
                'colour_finish', 'drain_position', 'min_cabinet_size_mm',
                'brand_name', 'body_html'
            ]

        empty_fields = []

        for field in field_list:
            value = product_data.get(field)
            if value is None or value == '' or value == 0:
                empty_fields.append(field)

        return empty_fields

    def merge_for_gaps_and_fixes(self, existing: Dict[str, Any], extracted: Dict[str, Any],
                                 field_confidence: Dict[str, float] = None,
                                 fill_empty: bool = True,
                                 fix_errors: bool = False,
                                 confidence_threshold: float = 0.8) -> tuple[Dict[str, Any], List[str]]:
        """
        Smart merge for filling gaps and fixing errors.

        Strategy:
        1. Fill empty fields (if fill_empty=True)
        2. Fix incorrect fields (if fix_errors=True AND confidence >= threshold)
        3. Keep existing for everything else

        Args:
            existing: Current Shopify product data
            extracted: Newly extracted data from supplier
            field_confidence: Confidence scores for extracted fields
            fill_empty: Whether to fill empty fields
            fix_errors: Whether to fix incorrect fields (requires high confidence)
            confidence_threshold: Minimum confidence to fix existing data

        Returns:
            Tuple of (merged product data, list of changes made)
        """
        merged = existing.copy()
        changes = []

        if field_confidence is None:
            field_confidence = {}

        for field, extracted_value in extracted.items():
            existing_value = existing.get(field)
            confidence = field_confidence.get(field, 0.6)  # Default medium confidence

            # Skip if extracted value is empty
            if extracted_value is None or extracted_value == '':
                continue

            # Rule 1: Fill gaps (existing is empty)
            if fill_empty and (existing_value is None or existing_value == '' or existing_value == 0):
                merged[field] = extracted_value
                changes.append(f"Filled {field}: {extracted_value}")
                continue

            # Rule 2: Fix errors (high confidence and values differ)
            if fix_errors and confidence >= confidence_threshold:
                if existing_value != extracted_value:
                    # Additional safety: only fix if values are significantly different
                    # Don't fix minor variations like "Stainless Steel" vs "Stainless steel"
                    if self._should_fix_value(existing_value, extracted_value, field):
                        merged[field] = extracted_value
                        changes.append(f"Fixed {field}: {existing_value} → {extracted_value}")
                        continue

            # Rule 3: Keep existing (low confidence or matching values)
            # No change needed

        if changes:
            logger.debug(f"  Changes: {', '.join(changes[:5])}")
            if len(changes) > 5:
                logger.debug(f"  ... and {len(changes) - 5} more")

        return merged, changes

    def _should_fix_value(self, existing, extracted, field_name: str) -> bool:
        """
        Determine if existing value should be replaced with extracted value.

        Prevents fixing minor variations or good existing data.
        """
        # If types don't match, likely a significant difference
        if type(existing) != type(extracted):
            return True

        # For strings, check if they're substantially different
        if isinstance(existing, str) and isinstance(extracted, str):
            existing_lower = existing.lower().strip()
            extracted_lower = extracted.lower().strip()

            # If they're the same ignoring case, don't fix
            if existing_lower == extracted_lower:
                return False

            # If one contains the other, probably not a fix worth making
            if existing_lower in extracted_lower or extracted_lower in existing_lower:
                return False

        # For numbers, check if difference is significant
        if isinstance(existing, (int, float)) and isinstance(extracted, (int, float)):
            # For dimensions, allow 5% tolerance
            if field_name.endswith('_mm'):
                if existing > 0:
                    percent_diff = abs(extracted - existing) / existing
                    if percent_diff < 0.05:  # Less than 5% difference
                        return False

        # Otherwise, yes, fix it
        return True

    def update_product(self, sku: str, product_data: Dict[str, Any]) -> bool:
        """
        Update product in Shopify.

        Args:
            sku: Product SKU to update
            product_data: Product data to update (must include shopify_product_id and shopify_variant_id)

        Returns:
            True if update succeeded, False otherwise
        """
        try:
            if not self.shop_url or not self.access_token:
                logger.error("  Shopify credentials not configured; cannot update Shopify")
                return False

            product_id = product_data.get('shopify_product_id')
            variant_id = product_data.get('shopify_variant_id')

            if not product_id or not variant_id:
                logger.error(f"  Missing Shopify IDs for {sku}")
                return False

            # Rate limiting
            self._rate_limit()

            # Build update payload
            product_update = self._build_product_update(product_data)
            variant_update = self._build_variant_update(product_data)

            # Update product (title, body, etc.)
            if product_update:
                url = f"{self.base_url}/products/{product_id}.json"
                response = self.session.put(url, json={'product': product_update})
                response.raise_for_status()
                logger.debug(f"  Updated product {product_id}")

            # Update variant (price, SKU, etc.)
            if variant_update:
                url = f"{self.base_url}/variants/{variant_id}.json"
                response = self.session.put(url, json={'variant': variant_update})
                response.raise_for_status()
                logger.debug(f"  Updated variant {variant_id}")

            # Update metafields (dimensions, specs)
            metafield_updates = self._build_metafield_updates(product_data)
            if metafield_updates:
                self._update_metafields(product_id, metafield_updates)

            return True

        except requests.exceptions.HTTPError as e:
            logger.error(f"  HTTP error updating {sku}: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"  Response: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"  Error updating product {sku}: {e}")
            return False

    def _build_product_update(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build product update payload for Shopify API."""
        update = {}

        # Map our fields to Shopify product fields
        field_mapping = {
            'title': 'title',
            'vendor': 'vendor',
            'product_type': 'product_type',
            'body_html': 'body_html',
        }

        for our_field, shopify_field in field_mapping.items():
            if our_field in product_data and product_data[our_field] is not None:
                update[shopify_field] = product_data[our_field]

        # Handle tags
        if 'tags' in product_data and product_data['tags']:
            if isinstance(product_data['tags'], list):
                update['tags'] = ','.join(product_data['tags'])
            else:
                update['tags'] = product_data['tags']

        return update

    def _build_variant_update(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build variant update payload for Shopify API."""
        update = {}

        # Map our fields to Shopify variant fields
        field_mapping = {
            'sku': 'sku',
            'shopify_price': 'price',
            'shopify_compare_price': 'compare_at_price',
            'shopify_weight': 'weight',
        }

        for our_field, shopify_field in field_mapping.items():
            if our_field in product_data and product_data[our_field] is not None:
                update[shopify_field] = product_data[our_field]

        return update

    def _build_metafield_updates(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build metafield updates for spec/dimension fields."""
        metafields = {}

        # Map our fields to Shopify metafields (namespace.key format)
        # Namespace: product_specifications (matches existing Shopify store config)
        # Dimension fields
        dimension_fields = {
            'overall_width_mm': 'product_specifications.overall_width_mm',
            'overall_depth_mm': 'product_specifications.overall_depth_mm',
            'overall_height_mm': 'product_specifications.overall_height_mm',
            'bowl_width_mm': 'product_specifications.bowl_width_mm',
            'bowl_depth_mm': 'product_specifications.bowl_depth_mm',
            'bowl_height_mm': 'product_specifications.bowl_height_mm',
            'min_cabinet_size_mm': 'product_specifications.min_cabinet_size_mm',
        }

        # Spec fields
        spec_fields = {
            'product_material': 'product_specifications.material',
            'installation_type': 'product_specifications.installation_type',
            'warranty_years': 'product_specifications.warranty_years',
            'colour_finish': 'product_specifications.colour_finish',
            'drain_position': 'product_specifications.drain_position',
            'brand_name': 'product_specifications.brand_name',
        }

        all_fields = {**dimension_fields, **spec_fields}

        for our_field, metafield_key in all_fields.items():
            if our_field in product_data and product_data[our_field] is not None and product_data[our_field] != '':
                namespace, key = metafield_key.split('.')
                value = product_data[our_field]

                # Determine type
                if isinstance(value, (int, float)):
                    value_type = 'number_integer' if isinstance(value, int) else 'number_decimal'
                else:
                    value_type = 'single_line_text_field'

                metafields[our_field] = {
                    'namespace': namespace,
                    'key': key,
                    'value': str(value),
                    'type': value_type
                }

        return metafields

    def _update_metafields(self, product_id: int, metafields: Dict[str, Any]):
        """Update product metafields via Shopify API."""
        for field_name, metafield_data in metafields.items():
            try:
                # Rate limiting
                self._rate_limit()

                # Create or update metafield
                url = f"{self.base_url}/products/{product_id}/metafields.json"

                # First, check if metafield exists
                params = {
                    'namespace': metafield_data['namespace'],
                    'key': metafield_data['key']
                }
                response = self.session.get(url, params=params)
                response.raise_for_status()
                existing = response.json().get('metafields', [])

                if existing:
                    # Update existing metafield
                    metafield_id = existing[0]['id']
                    update_url = f"{self.base_url}/products/{product_id}/metafields/{metafield_id}.json"
                    response = self.session.put(update_url, json={'metafield': {
                        'value': metafield_data['value'],
                        'type': metafield_data['type']
                    }})
                else:
                    # Create new metafield
                    response = self.session.post(url, json={'metafield': metafield_data})

                response.raise_for_status()
                logger.debug(f"  Updated metafield {metafield_data['namespace']}.{metafield_data['key']}")

            except Exception as e:
                logger.warning(f"  Failed to update metafield {field_name}: {e}")
                # Continue with other metafields even if one fails

    def _rate_limit(self):
        """Implement rate limiting for Shopify API"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - time_since_last)

        self.last_request_time = time.time()
        self.requests_made += 1


# Singleton instance
_shopify_fetcher = None


def get_shopify_fetcher():
    """Get or create the singleton ShopifyFetcher instance"""
    global _shopify_fetcher
    if _shopify_fetcher is None:
        _shopify_fetcher = ShopifyFetcher()
    return _shopify_fetcher
