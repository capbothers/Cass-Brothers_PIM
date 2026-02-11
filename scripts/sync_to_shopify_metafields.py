#!/usr/bin/env python3
"""
Sync enriched product data (categories and specs) to Shopify metafields

Usage:
    python scripts/sync_to_shopify_metafields.py [--limit N] [--dry-run]
"""

import os
import sys
import json
import time
import sqlite3
import argparse
from typing import Dict, List, Optional
import requests
from dotenv import load_dotenv

class ShopifyMetafieldSync:
    """Sync enriched data from local DB to Shopify metafields"""

    def __init__(self, shop_url: str, access_token: str, dry_run: bool = False):
        # Ensure URL has https:// scheme
        if not shop_url.startswith(('http://', 'https://')):
            shop_url = f"https://{shop_url}"
        self.shop_url = shop_url.rstrip('/')
        self.access_token = access_token
        self.dry_run = dry_run
        self.api_version = '2024-01'

        self.headers = {
            'X-Shopify-Access-Token': access_token,
            'Content-Type': 'application/json'
        }

        self.synced_count = 0
        self.error_count = 0

    def get_enriched_products(self, limit: Optional[int] = None,
                              min_confidence: float = 0.0) -> List[Dict]:
        """Get products with enriched category data"""
        conn = sqlite3.connect('supplier_products.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = """
        SELECT
            s.product_id,
            s.sku,
            s.title,
            s.super_category,
            s.primary_category,
            s.product_category_type,
            s.collection_name,
            s.overall_width_mm,
            s.overall_depth_mm,
            s.overall_height_mm,
            s.material,
            s.colour_finish,
            s.warranty_years,
            s.weight_kg,
            s.tap_hole_size_mm,
            s.installation_type,
            s.flow_rate_lpm,
            s.water_pressure_min_kpa,
            s.water_pressure_max_kpa,
            s.is_boiling,
            s.is_chilled,
            s.is_sparkling,
            s.is_filtered,
            s.is_ambient,
            s.is_lead_free,
            s.wels_rating,
            s.enriched_confidence,
            sup.spec_sheet_url
        FROM shopify_products s
        LEFT JOIN supplier_products sup ON s.sku = sup.sku
        WHERE s.primary_category IS NOT NULL
        AND s.enriched_at IS NOT NULL
        AND s.enriched_confidence >= ?
        ORDER BY s.enriched_confidence DESC
        """

        params = [min_confidence]

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query, params)
        products = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return products

    def build_metafields(self, product: Dict) -> List[Dict]:
        """Build metafield objects from product data"""
        metafields = []

        # Category metafields (product_specifications namespace)
        category_fields = {
            'super_category': product.get('super_category'),
            'primary_category': product.get('primary_category'),
            'product_category_type': product.get('product_category_type'),
            'collection_name': product.get('collection_name'),
        }

        for key, value in category_fields.items():
            if value:
                metafields.append({
                    'namespace': 'product_specifications',
                    'key': key,
                    'value': str(value),
                    'type': 'single_line_text_field'
                })

        # Specification metafields (product_specifications namespace)
        spec_fields = {
            'overall_width_mm': product.get('overall_width_mm'),
            'overall_depth_mm': product.get('overall_depth_mm'),
            'overall_height_mm': product.get('overall_height_mm'),
            'material': product.get('material'),
            'colour_finish': product.get('colour_finish'),
            'warranty_years': product.get('warranty_years'),
            'weight_kg': product.get('weight_kg'),
            'tap_hole_size_mm': product.get('tap_hole_size_mm'),
            'installation_type': product.get('installation_type'),
            'flow_rate_lpm': product.get('flow_rate_lpm'),
            'water_pressure_min_kpa': product.get('water_pressure_min_kpa'),
            'water_pressure_max_kpa': product.get('water_pressure_max_kpa'),
            'wels_rating': product.get('wels_rating'),
        }

        integer_fields = {'warranty_years', 'tap_hole_size_mm', 'water_pressure_min_kpa', 'water_pressure_max_kpa', 'wels_rating'}
        decimal_fields = {'weight_kg', 'overall_width_mm', 'overall_depth_mm', 'overall_height_mm', 'flow_rate_lpm'}

        for key, value in spec_fields.items():
            if value is not None and str(value) not in ('None', '', '0', '0.0'):
                if key in integer_fields:
                    field_type = 'number_integer'
                elif key in decimal_fields:
                    field_type = 'number_decimal'
                else:
                    field_type = 'single_line_text_field'

                metafields.append({
                    'namespace': 'product_specifications',
                    'key': key,
                    'value': str(value),
                    'type': field_type
                })

        # Boolean capability metafields (Billi/Zip water systems + Lead Free)
        boolean_fields = {
            'is_boiling': product.get('is_boiling'),
            'is_chilled': product.get('is_chilled'),
            'is_sparkling': product.get('is_sparkling'),
            'is_filtered': product.get('is_filtered'),
            'is_ambient': product.get('is_ambient'),
            'is_lead_free': product.get('is_lead_free'),
        }

        for key, value in boolean_fields.items():
            if value is not None:
                metafields.append({
                    'namespace': 'product_specifications',
                    'key': key,
                    'value': 'true' if value else 'false',
                    'type': 'boolean'
                })

        # Spec sheet PDF URL (from supplier_products table)
        spec_sheet_url = product.get('spec_sheet_url')
        if spec_sheet_url and str(spec_sheet_url) not in ('None', ''):
            metafields.append({
                'namespace': 'product_specifications',
                'key': 'spec_sheet_url',
                'value': str(spec_sheet_url),
                'type': 'url'
            })

        return metafields

    def update_product_metafields(self, product_id: str, metafields: List[Dict]) -> bool:
        """Update product metafields via Shopify API"""

        if self.dry_run:
            print(f"  [DRY RUN] Would update {len(metafields)} metafields for product {product_id}")
            return True

        url = f"{self.shop_url}/admin/api/{self.api_version}/products/{product_id}/metafields.json"

        # Update each metafield (batch updates in production would use GraphQL)
        success = True
        for metafield in metafields:
            try:
                response = requests.post(
                    url,
                    headers=self.headers,
                    json={'metafield': metafield},
                    timeout=10
                )

                if response.status_code == 429:
                    # Rate limited - wait and retry
                    retry_after = int(response.headers.get('Retry-After', 2))
                    print(f"  Rate limited, waiting {retry_after}s...")
                    time.sleep(retry_after)
                    response = requests.post(url, headers=self.headers, json={'metafield': metafield})

                if response.status_code not in [200, 201]:
                    print(f"  ✗ Failed to update {metafield['key']}: {response.status_code}")
                    print(f"    {response.text}")
                    success = False

                time.sleep(0.5)  # Rate limiting

            except Exception as e:
                print(f"  ✗ Error updating {metafield['key']}: {e}")
                success = False

        return success

    def sync_products(self, limit: Optional[int] = None, min_confidence: float = 0.0):
        """Sync enriched products to Shopify"""
        print("=" * 80)
        print("SHOPIFY METAFIELD SYNC")
        print("=" * 80)

        if self.dry_run:
            print("\n  DRY RUN MODE - No actual updates will be made\n")

        if min_confidence > 0:
            print(f"  Minimum confidence: {min_confidence}")

        products = self.get_enriched_products(limit, min_confidence)
        total = len(products)

        print(f"\nProducts to sync: {total}")
        print()

        for i, product in enumerate(products, 1):
            sku = product['sku']
            product_id = product['product_id']

            print(f"[{i}/{total}] {sku} - {product['primary_category']}")

            # Build metafields
            metafields = self.build_metafields(product)
            print(f"  → {len(metafields)} metafields to sync")

            # Update Shopify
            if self.update_product_metafields(product_id, metafields):
                self.synced_count += 1
                print(f"  ✓ Synced")
            else:
                self.error_count += 1
                print(f"  ✗ Failed")

        print("\n" + "=" * 80)
        print("SYNC COMPLETE")
        print("=" * 80)
        print(f"\nProducts synced: {self.synced_count}/{total}")
        if self.error_count > 0:
            print(f"Errors: {self.error_count}")


def main():
    load_dotenv()  # Load environment variables from .env file

    parser = argparse.ArgumentParser(description='Sync enriched data to Shopify metafields')
    parser.add_argument('--limit', type=int, help='Limit number of products to sync')
    parser.add_argument('--dry-run', action='store_true', help='Preview without making changes')
    parser.add_argument('--min-confidence', type=float, default=0.0, help='Minimum confidence threshold (default: 0.0)')
    parser.add_argument('--shop-url', help='Shopify shop URL (or set SHOPIFY_SHOP_URL env var)')
    parser.add_argument('--access-token', help='Shopify API access token (or set SHOPIFY_ACCESS_TOKEN env var)')

    args = parser.parse_args()

    # Get credentials
    shop_url = args.shop_url or os.getenv('SHOPIFY_SHOP_URL')
    access_token = args.access_token or os.getenv('SHOPIFY_ACCESS_TOKEN')

    if not shop_url or not access_token:
        print("Error: Shopify credentials required")
        print("Set SHOPIFY_SHOP_URL and SHOPIFY_ACCESS_TOKEN environment variables")
        print("Or pass --shop-url and --access-token arguments")
        sys.exit(1)

    # Run sync
    syncer = ShopifyMetafieldSync(shop_url, access_token, dry_run=args.dry_run)
    syncer.sync_products(limit=args.limit, min_confidence=args.min_confidence)


if __name__ == '__main__':
    main()
