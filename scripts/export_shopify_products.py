#!/usr/bin/env python3
"""
Export All Shopify Products with Metafields

Exports every product from Shopify (with metafields) to CSV and SQLite,
then prints a gap analysis showing which fields are missing most often.

This is the BASELINE step before building the supplier database:
1. Export what we have in Shopify  <-- THIS SCRIPT
2. Scrape supplier URLs into supplier_products table
3. Compare to find missing products and empty fields
4. Fill gaps using fix_existing_products.py

Usage:
    python scripts/export_shopify_products.py
    python scripts/export_shopify_products.py --output shopify_baseline.csv
    python scripts/export_shopify_products.py --vendor "Abey" --output abey_products.csv
"""

import os
import sys
import csv
import json
import time
import argparse
from datetime import datetime
from typing import Dict, Any, List, Optional
import importlib.util

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _import_module_from_path(module_name: str, relative_path: str):
    """Import a module by file path to avoid loading core/__init__.py."""
    module_path = os.path.join(REPO_ROOT, relative_path)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(REPO_ROOT, '.env'))

shopify_fetcher_module = _import_module_from_path(
    "shopify_fetcher", os.path.join("core", "shopify_fetcher.py")
)
get_shopify_fetcher = shopify_fetcher_module.get_shopify_fetcher

# Metafield keys we track (must match _build_metafield_updates in shopify_fetcher.py)
SPEC_METAFIELD_KEYS = [
    'overall_width_mm',
    'overall_depth_mm',
    'overall_height_mm',
    'bowl_width_mm',
    'bowl_depth_mm',
    'bowl_height_mm',
    'min_cabinet_size_mm',
    'material',
    'installation_type',
    'warranty_years',
    'colour_finish',
    'drain_position',
    'brand_name',
]

# Standard product fields to check for gaps
STANDARD_FIELDS = [
    'title', 'vendor', 'product_type', 'body_html', 'tags',
    'sku', 'price', 'compare_at_price', 'weight', 'image_src',
]


def fetch_metafields(shopify, product_id: int) -> Dict[str, str]:
    """Fetch metafields for a product from the specs namespace."""
    metafields = {}
    try:
        shopify._rate_limit()
        url = f"{shopify.base_url}/products/{product_id}/metafields.json"
        params = {'namespace': 'product_specifications', 'limit': 250}
        response = shopify.session.get(url, params=params)
        response.raise_for_status()

        for mf in response.json().get('metafields', []):
            key = mf.get('key', '')
            value = mf.get('value', '')
            if key and value:
                metafields[key] = value
    except Exception as e:
        print(f"  Warning: Failed to fetch metafields for product {product_id}: {e}")

    return metafields


def fetch_all_products(shopify, vendor_filter: str = None) -> List[Dict[str, Any]]:
    """
    Fetch all products from Shopify using cursor-based pagination.

    Returns a list of flat dicts (one per variant) with product + metafield data.
    """
    products = []
    page_info = None
    page_num = 0

    while True:
        page_num += 1
        shopify._rate_limit()

        url = f"{shopify.base_url}/products.json"
        params = {'limit': 250}

        if page_info:
            # Cursor-based pagination: only pass page_info, no other filters
            params = {'limit': 250, 'page_info': page_info}
        elif vendor_filter:
            params['vendor'] = vendor_filter

        response = shopify.session.get(url, params=params)
        response.raise_for_status()

        batch = response.json().get('products', [])
        if not batch:
            break

        print(f"  Page {page_num}: {len(batch)} products (total variants so far: {len(products)})")

        for product in batch:
            product_id = product.get('id')

            # Fetch metafields for this product
            metafields = fetch_metafields(shopify, product_id)

            # One row per variant
            variants = product.get('variants', [])
            if not variants:
                variants = [{}]

            images = product.get('images', [])
            image_src = images[0].get('src', '') if images else ''

            for variant in variants:
                row = {
                    'product_id': product_id,
                    'variant_id': variant.get('id', ''),
                    'title': product.get('title', ''),
                    'vendor': product.get('vendor', ''),
                    'product_type': product.get('product_type', ''),
                    'tags': product.get('tags', ''),
                    'status': product.get('status', ''),
                    'handle': product.get('handle', ''),
                    'body_html': (product.get('body_html') or '')[:200],  # Truncate for CSV
                    'body_html_length': len(product.get('body_html') or ''),
                    'sku': variant.get('sku', ''),
                    'price': variant.get('price', ''),
                    'compare_at_price': variant.get('compare_at_price', ''),
                    'weight': variant.get('weight', ''),
                    'image_src': image_src,
                    'image_count': len(images),
                    'created_at': product.get('created_at', ''),
                    'updated_at': product.get('updated_at', ''),
                }

                # Add metafields
                for key in SPEC_METAFIELD_KEYS:
                    row[f'meta_{key}'] = metafields.get(key, '')

                products.append(row)

        # Check for next page via Link header
        link_header = response.headers.get('Link', '')
        if 'rel="next"' in link_header:
            # Extract page_info from Link header
            for part in link_header.split(','):
                if 'rel="next"' in part:
                    # Format: <https://...?page_info=XYZ>; rel="next"
                    url_part = part.split(';')[0].strip().strip('<>')
                    if 'page_info=' in url_part:
                        page_info = url_part.split('page_info=')[1].split('&')[0]
                    break
        else:
            break

    return products


def write_csv(products: List[Dict[str, Any]], output_file: str):
    """Write products to CSV."""
    if not products:
        print("No products to write.")
        return

    fieldnames = list(products[0].keys())

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(products)

    print(f"\nCSV written: {output_file} ({len(products)} rows)")


def analyze_gaps(products: List[Dict[str, Any]]):
    """Print gap analysis: which fields are missing most often."""
    if not products:
        return

    total = len(products)

    print(f"\n{'='*70}")
    print(f"GAP ANALYSIS - {total} product variants")
    print(f"{'='*70}")

    # --- Standard field gaps ---
    print(f"\n--- Standard Fields ---")
    standard_gaps = []
    for field in STANDARD_FIELDS:
        empty_count = sum(1 for p in products if not p.get(field))
        pct = (empty_count / total) * 100
        standard_gaps.append((field, empty_count, pct))

    standard_gaps.sort(key=lambda x: x[1], reverse=True)
    for field, count, pct in standard_gaps:
        bar = '#' * int(pct / 2)
        print(f"  {field:<25} {count:>5} empty ({pct:5.1f}%) {bar}")

    # --- Metafield gaps ---
    print(f"\n--- Spec Metafields ---")
    meta_gaps = []
    for key in SPEC_METAFIELD_KEYS:
        col = f'meta_{key}'
        empty_count = sum(1 for p in products if not p.get(col))
        pct = (empty_count / total) * 100
        meta_gaps.append((key, empty_count, pct))

    meta_gaps.sort(key=lambda x: x[1], reverse=True)
    for key, count, pct in meta_gaps:
        bar = '#' * int(pct / 2)
        print(f"  {key:<25} {count:>5} empty ({pct:5.1f}%) {bar}")

    # --- Vendor breakdown ---
    print(f"\n--- Products by Vendor (top 20) ---")
    vendor_counts = {}
    for p in products:
        vendor = p.get('vendor') or '(no vendor)'
        vendor_counts[vendor] = vendor_counts.get(vendor, 0) + 1

    sorted_vendors = sorted(vendor_counts.items(), key=lambda x: x[1], reverse=True)
    for vendor, count in sorted_vendors[:20]:
        pct = (count / total) * 100
        print(f"  {vendor:<35} {count:>5} ({pct:5.1f}%)")

    if len(sorted_vendors) > 20:
        print(f"  ... and {len(sorted_vendors) - 20} more vendors")

    # --- Vendor gap detail (top 10 vendors) ---
    print(f"\n--- Metafield Coverage by Top 10 Vendors ---")
    for vendor, _ in sorted_vendors[:10]:
        vendor_products = [p for p in products if p.get('vendor') == vendor]
        vcount = len(vendor_products)
        filled_counts = []
        for key in SPEC_METAFIELD_KEYS:
            col = f'meta_{key}'
            filled = sum(1 for p in vendor_products if p.get(col))
            filled_counts.append(filled)
        avg_fill = sum(filled_counts) / len(filled_counts) if filled_counts else 0
        avg_pct = (avg_fill / vcount) * 100 if vcount else 0
        print(f"  {vendor:<35} {vcount:>4} products, avg metafield fill: {avg_pct:5.1f}%")

    print(f"\n{'='*70}")


def main():
    parser = argparse.ArgumentParser(
        description='Export all Shopify products with metafields to CSV'
    )
    parser.add_argument(
        '--output', '-o',
        help='Output CSV file path (default: shopify_export_TIMESTAMP.csv)',
        default=None
    )
    parser.add_argument(
        '--vendor', '-v',
        help='Filter by vendor name (e.g., "Abey")',
        default=None
    )
    parser.add_argument(
        '--no-metafields',
        action='store_true',
        help='Skip fetching metafields (faster but no spec data)'
    )

    args = parser.parse_args()

    # Generate output filename
    if args.output is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        vendor_suffix = f"_{args.vendor.lower().replace(' ', '_')}" if args.vendor else ""
        args.output = f"shopify_export{vendor_suffix}_{timestamp}.csv"

    print("="*70)
    print("  Export Shopify Products with Metafields")
    print("="*70)
    print()

    # Initialize Shopify fetcher
    shopify = get_shopify_fetcher()

    if not shopify.shop_url or not shopify.access_token:
        print("Error: Shopify credentials not configured.")
        print("Set SHOPIFY_SHOP_URL and SHOPIFY_ACCESS_TOKEN in .env")
        sys.exit(1)

    print(f"Shop: {shopify.shop_url}")
    if args.vendor:
        print(f"Vendor filter: {args.vendor}")
    print(f"Output: {args.output}")
    print()

    # Fetch all products
    print("Fetching products from Shopify...")
    products = fetch_all_products(shopify, vendor_filter=args.vendor)

    if not products:
        print("\nNo products found.")
        sys.exit(0)

    print(f"\nFetched {len(products)} product variants total.")

    # Write CSV
    write_csv(products, args.output)

    # Gap analysis
    analyze_gaps(products)

    print(f"\nDone. CSV saved to: {args.output}")
    print(f"Next steps:")
    print(f"  1. Review the gap analysis above")
    print(f"  2. Identify top vendors with most missing metafields")
    print(f"  3. Scrape those supplier URLs into supplier_products database")
    print(f"  4. Run fix_existing_products.py to fill the gaps")


if __name__ == "__main__":
    main()
