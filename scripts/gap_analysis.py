#!/usr/bin/env python3
"""
Gap Analysis & Enrichment Pipeline

Compares supplier-scraped product data against the Shopify baseline to:
1. Identify products with empty/missing metafields
2. Extract structured specs from supplier data (tags, JSON-LD, etc.)
3. Map extracted specs to Shopify metafield schema
4. Optionally push updates to Shopify via Admin API

Usage:
    python scripts/gap_analysis.py                          # Dry run - show gaps
    python scripts/gap_analysis.py --vendor "Parisi"        # Single vendor
    python scripts/gap_analysis.py --push --limit 5         # Push first 5 updates
    python scripts/gap_analysis.py --push --sku "PM.001"    # Push single SKU
"""

import os
import sys
import re
import json
import csv
import sqlite3
import argparse
import time
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from core.data_validator import (
    validate_product_metafields, filter_by_confidence,
    ValidationResult,
)

# Shopify metafield keys we want to populate
# Namespace: product_specifications
METAFIELD_SCHEMA = {
    'overall_width_mm': {'type': 'number_decimal', 'extract_from': ['Width (mm)', 'Width', 'Length', 'width_mm', 'W', 'Overall Length']},
    'overall_depth_mm': {'type': 'number_decimal', 'extract_from': ['Depth (mm)', 'Depth', 'depth_mm', 'D', 'Overall Depth']},
    'overall_height_mm': {'type': 'number_decimal', 'extract_from': ['Height (mm)', 'Height', 'height_mm', 'H', 'Overall Height']},
    'material': {'type': 'single_line_text_field', 'extract_from': ['Material', 'Materials', 'SINKmaterial']},
    'colour_finish': {'type': 'single_line_text_field', 'extract_from': ['Colour/Finish', 'Colour', 'colour', 'Finish', 'Color', 'color']},
    'warranty_years': {'type': 'number_integer', 'extract_from': ['Warranty', 'Warranty (Years)']},
    'installation_type': {'type': 'single_line_text_field', 'extract_from': ['Installation', 'Mounting', 'Fixing Types', 'Mount Type']},
    'brand_name': {'type': 'single_line_text_field', 'extract_from': ['Brand', 'brand_name']},
    'drain_position': {'type': 'single_line_text_field', 'extract_from': ['Drain Position', 'Waste Outlet']},
}


def parse_shopify_tags(tags_str: str) -> Dict[str, str]:
    """
    Parse Shopify tags string into key:value pairs.
    Tags like "Width (mm): 1500, Material: Acrylic" become dict entries.
    """
    specs = {}
    if not tags_str:
        return specs

    for tag in tags_str.split(','):
        tag = tag.strip()
        if ':' in tag:
            key, _, value = tag.partition(':')
            key = key.strip()
            value = value.strip()
            if value and value not in ('', ' '):
                specs[key] = value

    return specs


def parse_supplier_specs(specs_json: str) -> Dict[str, str]:
    """Parse supplier specs JSON, including tags embedded in specs."""
    if not specs_json:
        return {}

    try:
        data = json.loads(specs_json)
    except json.JSONDecodeError:
        return {}

    specs = {}

    # If specs contain 'tags', parse them
    if 'tags' in data and isinstance(data['tags'], str):
        specs.update(parse_shopify_tags(data['tags']))
        del data['tags']

    # Add remaining specs directly
    for key, value in data.items():
        if key in ('all_skus', 'variant_count'):
            continue
        if isinstance(value, str) and value:
            specs[key] = value

    return specs


def extract_metafields(supplier_specs: Dict[str, str],
                       shopify_tags: Dict[str, str],
                       brand: str = '') -> Dict[str, str]:
    """
    Extract metafield values from supplier specs and Shopify tags.
    Returns dict of metafield_key -> value.
    """
    metafields = {}

    # Combine all available data sources (supplier specs take priority)
    # Build a case-insensitive lookup: lowercase key -> original value
    combined = {}
    combined_lower = {}
    for d in (shopify_tags, supplier_specs):
        for k, v in d.items():
            combined[k] = v
            combined_lower[k.lower()] = v

    for mf_key, mf_config in METAFIELD_SCHEMA.items():
        for source_key in mf_config['extract_from']:
            # Try exact match first, then case-insensitive
            raw_value = combined.get(source_key) or combined_lower.get(source_key.lower())
            if raw_value:
                # Clean and validate the value
                value = clean_metafield_value(mf_key, raw_value, mf_config['type'])
                if value:
                    metafields[mf_key] = value
                    break

    # Special handling for brand_name from supplier data
    if 'brand_name' not in metafields and brand:
        metafields['brand_name'] = brand

    return metafields


def clean_metafield_value(key: str, raw_value: str, value_type: str) -> str:
    """Clean and validate a metafield value."""
    value = raw_value.strip()

    if value_type == 'number_decimal':
        # Extract numeric value from strings like "1500" or "1500mm"
        match = re.search(r'(\d+(?:\.\d+)?)', value)
        if match:
            num = match.group(1)
            # Shopify number_decimal expects decimal format
            if '.' not in num:
                num = num + '.0'
            return num
        return ''

    if value_type == 'number_integer':
        match = re.search(r'(\d+)', value)
        if match:
            return match.group(1)
        return ''

    if key == 'warranty_years':
        # Extract warranty years from "15 Year Warranty" etc.
        match = re.search(r'(\d+)\s*(?:Year|yr)', value, re.IGNORECASE)
        if match:
            return match.group(1)
        # If it's just a number
        if value.isdigit():
            return value
        return value  # Keep as-is if can't parse

    if key == 'colour_finish':
        # Clean up multi-option strings like "Gloss White I Matt White"
        value = value.replace(' I ', ' / ')
        return value

    if key == 'material':
        # Clean up material strings
        value = value.replace('\u00ae', '®')
        return value

    return value


def get_matched_products(db_path: str, vendor: str = None,
                         sku: str = None) -> List[Dict[str, Any]]:
    """Get supplier products matched to Shopify products."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
        SELECT
            sp.sku,
            sp.supplier_name,
            sp.product_name as supplier_product_name,
            sp.description as supplier_description,
            sp.price as supplier_price,
            sp.image_url as supplier_image,
            sp.specs_json as supplier_specs_json,
            sp.extraction_source,
            sh.product_id,
            sh.variant_id,
            sh.vendor as shopify_vendor,
            sh.title as shopify_title,
            sh.tags as shopify_tags,
            sh.image_src as shopify_image,
            sh.body_html_length,
            sh.meta_json,
            sh.status as shopify_status
        FROM supplier_products sp
        INNER JOIN shopify_products sh ON sp.sku = sh.sku
        WHERE sp.sku NOT LIKE '\\_\\_%' ESCAPE '\\'
    """
    params = []

    if vendor:
        query += " AND sp.supplier_name = ?"
        params.append(vendor)

    if sku:
        query += " AND sp.sku = ?"
        params.append(sku)

    query += " ORDER BY sp.supplier_name, sp.sku"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def analyze_gaps(products: List[Dict[str, Any]],
                 auto_push_threshold: float = 0.7,
                 reject_threshold: float = 0.3) -> List[Dict[str, Any]]:
    """
    Analyze gaps for each matched product, validate proposed values,
    and assign confidence scores.
    Returns enriched product list with gap analysis and validation results.
    """
    results = []

    for product in products:
        # Parse existing metafields
        existing_meta = {}
        if product['meta_json']:
            try:
                existing_meta = json.loads(product['meta_json'])
            except json.JSONDecodeError:
                pass

        # Parse supplier specs
        supplier_specs = parse_supplier_specs(product.get('supplier_specs_json', ''))

        # Parse Shopify tags
        shopify_tags = parse_shopify_tags(product.get('shopify_tags', ''))

        # Extract metafields from all sources
        extracted = extract_metafields(
            supplier_specs,
            shopify_tags,
            brand=product.get('shopify_vendor', '')
        )

        # Determine which fields are new (not already in existing metafields)
        new_fields = {}
        for key, value in extracted.items():
            if key not in existing_meta or not existing_meta[key]:
                new_fields[key] = value

        # Validate all new fields with confidence scoring
        brand_source = ('brand_name' in new_fields and
                        new_fields.get('brand_name') == product.get('shopify_vendor', ''))
        validation = validate_product_metafields(
            new_fields,
            product.get('shopify_tags', ''),
            supplier_specs,
            METAFIELD_SCHEMA,
            brand_source=brand_source,
        )

        # Split into auto-push / review / reject
        auto_push, needs_review, rejected = filter_by_confidence(
            validation, auto_push_threshold, reject_threshold
        )

        product['extracted_metafields'] = extracted
        product['new_metafields'] = new_fields
        product['auto_push_fields'] = auto_push
        product['review_fields'] = needs_review
        product['rejected_fields'] = rejected
        product['validation'] = validation
        product['existing_metafields'] = existing_meta
        product['supplier_specs'] = supplier_specs
        product['gap_count'] = len(new_fields)

        results.append(product)

    return results


def push_metafields_to_shopify(product_id: str, metafields: Dict[str, str],
                                dry_run: bool = True) -> Dict[str, Any]:
    """
    Push metafield updates to Shopify via Admin API.
    Uses individual POST per metafield to respect existing type definitions.

    Args:
        product_id: Shopify product ID
        metafields: Dict of key -> value to set
        dry_run: If True, just return what would be sent

    Returns:
        Dict with status and details
    """
    from dotenv import load_dotenv
    load_dotenv(os.path.join(REPO_ROOT, '.env'))

    shop_url = os.environ.get('SHOPIFY_SHOP_URL', '')
    token = os.environ.get('SHOPIFY_ACCESS_TOKEN', '')
    api_version = os.environ.get('SHOPIFY_API_VERSION', '2024-01')

    if not shop_url or not token:
        return {'status': 'error', 'message': 'Missing Shopify credentials'}

    namespace = 'product_specifications'
    base_url = f"https://{shop_url}/admin/api/{api_version}"

    if dry_run:
        return {
            'status': 'dry_run',
            'product_id': product_id,
            'field_count': len(metafields),
        }

    # Push each metafield individually via POST
    import requests

    headers = {
        'X-Shopify-Access-Token': token,
        'Content-Type': 'application/json',
    }

    url = f"{base_url}/products/{product_id}/metafields.json"
    success_count = 0
    errors = []

    for key, value in metafields.items():
        mf_type = METAFIELD_SCHEMA.get(key, {}).get('type', 'single_line_text_field')

        payload = {
            'metafield': {
                'namespace': namespace,
                'key': key,
                'value': str(value),
                'type': mf_type,
            }
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)

            if resp.status_code in (200, 201):
                success_count += 1
            else:
                errors.append(f"{key}: {resp.status_code} - {resp.text[:100]}")
            time.sleep(0.2)  # Rate limit between metafield writes
        except Exception as e:
            errors.append(f"{key}: {str(e)}")

    if errors:
        return {
            'status': 'partial' if success_count > 0 else 'error',
            'product_id': product_id,
            'field_count': len(metafields),
            'success_count': success_count,
            'errors': errors,
        }

    return {
        'status': 'success',
        'product_id': product_id,
        'field_count': success_count,
    }


def export_review_queue(results: List[Dict[str, Any]], output_path: str):
    """Export products needing review to a CSV for manual inspection."""
    fieldnames = [
        'sku', 'vendor', 'shopify_title', 'product_id',
        'field', 'proposed_value', 'confidence', 'source', 'issues',
    ]

    rows = []
    for r in results:
        validation = r.get('validation', {})
        for key, vr in validation.items():
            if vr.confidence < 0.7:  # Only include items below auto-push threshold
                rows.append({
                    'sku': r['sku'],
                    'vendor': r['supplier_name'],
                    'shopify_title': r.get('shopify_title', ''),
                    'product_id': r.get('product_id', ''),
                    'field': key,
                    'proposed_value': vr.value,
                    'confidence': f"{vr.confidence:.2f}",
                    'source': vr.source,
                    'issues': '; '.join(vr.issues) if vr.issues else '',
                })

    if not rows:
        return 0

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def main():
    parser = argparse.ArgumentParser(description='Gap analysis and enrichment pipeline')
    parser.add_argument('--vendor', '-v', help='Filter by vendor name')
    parser.add_argument('--sku', '-s', help='Filter by specific SKU')
    parser.add_argument('--limit', '-l', type=int, default=0,
                       help='Limit number of products to process')
    parser.add_argument('--push', action='store_true',
                       help='Push HIGH-CONFIDENCE updates to Shopify (default: dry run)')
    parser.add_argument('--push-all', action='store_true',
                       help='Push ALL updates regardless of confidence (DANGEROUS)')
    parser.add_argument('--db', default='supplier_products.db',
                       help='SQLite database path')
    parser.add_argument('--csv-output', '-o', default='',
                       help='Export gap analysis to CSV')
    parser.add_argument('--review-csv', default='',
                       help='Export low-confidence items to review CSV')
    parser.add_argument('--min-gaps', type=int, default=1,
                       help='Only show products with at least N gap fields (default: 1)')
    parser.add_argument('--confidence', type=float, default=0.7,
                       help='Auto-push confidence threshold (default: 0.7)')

    args = parser.parse_args()

    db_path = os.path.join(REPO_ROOT, args.db)

    if not os.path.exists(db_path):
        print(f"Error: {db_path} not found.")
        sys.exit(1)

    # Get matched products
    products = get_matched_products(db_path, vendor=args.vendor, sku=args.sku)

    if not products:
        print("No matched products found. Run scrape_product_pages.py first.")
        sys.exit(0)

    print("=" * 70)
    print("  Gap Analysis & Enrichment (with Validation)")
    print("=" * 70)
    print(f"\nMatched products: {len(products)}")
    if args.push_all:
        print(f"Mode: PUSH ALL TO SHOPIFY (NO VALIDATION FILTER)")
    elif args.push:
        print(f"Mode: PUSH TO SHOPIFY (confidence >= {args.confidence})")
    else:
        print(f"Mode: DRY RUN (analysis only)")

    # Analyze gaps with validation
    results = analyze_gaps(products, auto_push_threshold=args.confidence)

    # Filter by min gaps
    results = [r for r in results if r['gap_count'] >= args.min_gaps]

    if args.limit > 0:
        results = results[:args.limit]

    print(f"Products with gaps: {len(results)}")

    if not results:
        print("\nNo gaps found! All metafields are already populated.")
        return

    # Summary stats
    total_gaps = sum(r['gap_count'] for r in results)
    total_auto = sum(len(r['auto_push_fields']) for r in results)
    total_review = sum(len(r['review_fields']) for r in results)
    total_rejected = sum(len(r['rejected_fields']) for r in results)

    gap_field_counts = {}
    for r in results:
        for key in r['new_metafields']:
            gap_field_counts[key] = gap_field_counts.get(key, 0) + 1

    print(f"\nTotal gap fields found:    {total_gaps}")
    print(f"  High confidence (auto):  {total_auto}  (>= {args.confidence})")
    print(f"  Needs review:            {total_review}  (0.3 - {args.confidence})")
    print(f"  Rejected:                {total_rejected}  (< 0.3)")

    print(f"\nGap fields breakdown:")
    for field, count in sorted(gap_field_counts.items(), key=lambda x: -x[1]):
        print(f"  {field:<25} {count:>5} products")

    # Show detailed results
    print(f"\n{'=' * 70}")
    print("PRODUCT DETAILS")
    print(f"{'=' * 70}")

    push_results = []

    for i, product in enumerate(results, 1):
        sku = product['sku']
        vendor = product['supplier_name']
        title = product['shopify_title'][:50] if product['shopify_title'] else ''
        product_id = product['product_id']
        validation = product['validation']

        print(f"\n[{i}/{len(results)}] {sku} - {title}")
        print(f"  Vendor: {vendor} | Product ID: {product_id}")

        # Show fields grouped by confidence
        if product['auto_push_fields']:
            print(f"  Auto-push ({len(product['auto_push_fields'])}):")
            for key, value in product['auto_push_fields'].items():
                vr = validation[key]
                display_val = str(value)[:50]
                print(f"    {key:<25} = {display_val:<50} [{vr.confidence:.2f}]")

        if product['review_fields']:
            print(f"  Needs review ({len(product['review_fields'])}):")
            for key, value in product['review_fields'].items():
                vr = validation[key]
                display_val = str(value)[:50]
                issues = ', '.join(vr.issues) if vr.issues else ''
                print(f"    {key:<25} = {display_val:<50} [{vr.confidence:.2f}] {issues}")

        if product['rejected_fields']:
            print(f"  Rejected ({len(product['rejected_fields'])}):")
            for key, value in product['rejected_fields'].items():
                vr = validation[key]
                display_val = str(value)[:50]
                issues = ', '.join(vr.issues) if vr.issues else ''
                print(f"    {key:<25} = {display_val:<50} [{vr.confidence:.2f}] {issues}")

        # Push if requested
        if args.push_all:
            fields_to_push = product['new_metafields']
        elif args.push:
            fields_to_push = product['auto_push_fields']
        else:
            fields_to_push = {}

        if fields_to_push:
            result = push_metafields_to_shopify(product_id, fields_to_push, dry_run=False)
            push_results.append(result)
            status = result['status']
            print(f"  => PUSH: {status} ({len(fields_to_push)} fields)")
            if status == 'error':
                print(f"     Error: {result.get('message', result.get('response_body', ''))[:100]}")
            time.sleep(0.5)  # Rate limit

    # Export gap analysis CSV if requested
    if args.csv_output:
        csv_path = os.path.join(REPO_ROOT, args.csv_output)
        fieldnames = ['sku', 'vendor', 'shopify_title', 'product_id', 'gap_count',
                      'auto_push_count', 'review_count', 'rejected_count']
        fieldnames += sorted(METAFIELD_SCHEMA.keys())

        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in results:
                row = {
                    'sku': r['sku'],
                    'vendor': r['supplier_name'],
                    'shopify_title': r['shopify_title'],
                    'product_id': r['product_id'],
                    'gap_count': r['gap_count'],
                    'auto_push_count': len(r['auto_push_fields']),
                    'review_count': len(r['review_fields']),
                    'rejected_count': len(r['rejected_fields']),
                }
                for key in METAFIELD_SCHEMA:
                    vr = r['validation'].get(key)
                    if vr:
                        row[key] = f"{vr.value} [{vr.confidence:.2f}]"
                    else:
                        row[key] = ''
                writer.writerow(row)

        print(f"\nGap analysis exported to: {csv_path}")

    # Export review queue CSV
    review_csv = args.review_csv
    if not review_csv and results:
        # Auto-generate review queue
        ts = time.strftime('%Y%m%d_%H%M%S')
        review_csv = f"review_queue_{ts}.csv"

    if review_csv:
        review_path = os.path.join(REPO_ROOT, review_csv)
        review_count = export_review_queue(results, review_path)
        if review_count > 0:
            print(f"Review queue exported: {review_path} ({review_count} items)")
        else:
            print("No items need review - all fields are high confidence!")

    # Push summary
    if push_results:
        success = sum(1 for r in push_results if r['status'] == 'success')
        errors = sum(1 for r in push_results if r['status'] == 'error')
        print(f"\n{'=' * 70}")
        print("PUSH SUMMARY")
        print(f"{'=' * 70}")
        print(f"Success: {success}")
        print(f"Errors:  {errors}")
        print(f"Total:   {len(push_results)}")


if __name__ == "__main__":
    main()
