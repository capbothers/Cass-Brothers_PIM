"""
Export Shopify Updates to CSV

Generates Shopify-compatible CSV for bulk import.
Includes only high-confidence and reviewed fields.

Usage:
    python scripts/export_shopify_updates.py
    python scripts/export_shopify_updates.py --collection sinks --output sinks_updates.csv
    python scripts/export_shopify_updates.py --threshold 0.7
"""

import sys
import os
import csv
import json
import argparse
from datetime import datetime
from typing import Dict, Any, List
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

supplier_db_module = _import_module_from_path("supplier_db", os.path.join("core", "supplier_db.py"))
apply_to_shopify_module = _import_module_from_path("apply_to_shopify", os.path.join("scripts", "apply_to_shopify.py"))

get_supplier_db = supplier_db_module.get_supplier_db
merge_fields_for_shopify = apply_to_shopify_module.merge_fields_for_shopify


def export_shopify_csv(output_file: str = None, collection: str = None,
                       confidence_threshold: float = 0.6, limit: int = None,
                       run_id: str = None) -> str:
    """
    Export processing queue items to Shopify-compatible CSV

    Args:
        output_file: Output CSV file path
        collection: Filter by collection
        confidence_threshold: Only include fields >= this confidence
        limit: Max items to export

    Returns:
        Path to generated CSV file
    """
    db = get_supplier_db()

    # Generate output filename if not provided
    if output_file is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        collection_suffix = f"_{collection}" if collection else ""
        output_file = f'shopify_updates{collection_suffix}_{timestamp}.csv'

    # Get items to export
    if collection:
        result = db.get_processing_queue(collection=collection, status='ready', limit=limit or 1000)
    else:
        result = db.get_processing_queue(status='ready', limit=limit or 1000)

    items = result['items']
    if run_id:
        # When run_id is provided, ignore status gating
        all_items = db.get_processing_queue(status=None, limit=limit or 2000)
        items = [i for i in all_items['items'] if i and i.get('run_id') == run_id]

    if not items:
        print("⚠️  No items ready for export")
        return None

    print(f"📊 Found {len(items)} items to export")

    # Prepare CSV rows
    csv_rows = []
    skipped_count = 0

    for item in items:
        queue_id = item['id']
        sku = item['sku']

        try:
            # Merge fields
            merged = merge_fields_for_shopify(queue_id, confidence_threshold)
            fields = merged['fields']

            if not fields:
                skipped_count += 1
                continue

            # Build Shopify CSV row
            csv_row = build_shopify_row(item, fields)
            csv_rows.append(csv_row)

        except Exception as e:
            print(f"⚠️  Error processing {sku}: {e}")
            skipped_count += 1

    if not csv_rows:
        print("⚠️  No items with fields to export")
        return None

    # Write Shopify CSV
    write_shopify_csv(output_file, csv_rows)

    print(f"\n✅ Exported {len(csv_rows)} products to {output_file}")
    if skipped_count > 0:
        print(f"⚠️  Skipped {skipped_count} items (no fields to apply)")

    print(f"\nNext steps:")
    print(f"1. Review {output_file}")
    print(f"2. Import to Shopify: Products → Import")
    print(f"3. Upload the CSV file")

    return output_file


def build_shopify_row(item: Dict[str, Any], fields: Dict[str, Any]) -> Dict[str, str]:
    """
    Build a Shopify CSV row from queue item and merged fields

    Args:
        item: Processing queue item
        fields: Merged fields (high-confidence + reviewed)

    Returns:
        Dict with Shopify CSV columns
    """
    row = {
        'Handle': item.get('shopify_handle', ''),
        'Title': item.get('title', ''),
        'Body (HTML)': fields.get('body_html', item.get('body_html', '')),
        'Vendor': item.get('vendor', ''),
        'Type': item.get('target_collection', ''),
        'Tags': '',
        'Published': 'TRUE',
        'Option1 Name': '',
        'Option1 Value': '',
        'Option2 Name': '',
        'Option2 Value': '',
        'Option3 Name': '',
        'Option3 Value': '',
        'Variant SKU': item.get('sku', ''),
        'Variant Grams': '',
        'Variant Inventory Tracker': '',
        'Variant Inventory Qty': '',
        'Variant Inventory Policy': 'deny',
        'Variant Fulfillment Service': 'manual',
        'Variant Price': item.get('shopify_price', ''),
        'Variant Compare At Price': item.get('shopify_compare_price', ''),
        'Variant Requires Shipping': 'TRUE',
        'Variant Taxable': 'TRUE',
        'Variant Barcode': '',
        'Image Src': '',
        'Image Position': '',
        'Image Alt Text': '',
        'Gift Card': 'FALSE',
        'SEO Title': '',
        'SEO Description': '',
        'Google Shopping / Google Product Category': '',
        'Google Shopping / Gender': '',
        'Google Shopping / Age Group': '',
        'Google Shopping / MPN': '',
        'Google Shopping / AdWords Grouping': '',
        'Google Shopping / AdWords Labels': '',
        'Google Shopping / Condition': '',
        'Google Shopping / Custom Product': '',
        'Google Shopping / Custom Label 0': '',
        'Google Shopping / Custom Label 1': '',
        'Google Shopping / Custom Label 2': '',
        'Google Shopping / Custom Label 3': '',
        'Google Shopping / Custom Label 4': '',
        'Variant Image': '',
        'Variant Weight Unit': '',
        'Variant Tax Code': '',
        'Cost per item': '',
        'Status': item.get('shopify_status', 'draft')
    }

    # Add metafields for dimensions and other structured data
    metafield_count = 1
    for field_name, value in fields.items():
        # Skip fields that map to standard Shopify columns
        if field_name in ['body_html', 'title', 'vendor']:
            continue

        # Add as metafield
        row[f'Metafield: custom.{field_name} [single_line_text_field]'] = str(value)
        metafield_count += 1

    return row


def write_shopify_csv(output_file: str, rows: List[Dict[str, str]]):
    """Write Shopify-compatible CSV"""
    if not rows:
        return

    # Get all unique column names from all rows
    all_columns = set()
    for row in rows:
        all_columns.update(row.keys())

    # Standard Shopify columns (in order)
    standard_columns = [
        'Handle', 'Title', 'Body (HTML)', 'Vendor', 'Type', 'Tags', 'Published',
        'Option1 Name', 'Option1 Value', 'Option2 Name', 'Option2 Value',
        'Option3 Name', 'Option3 Value', 'Variant SKU', 'Variant Grams',
        'Variant Inventory Tracker', 'Variant Inventory Qty', 'Variant Inventory Policy',
        'Variant Fulfillment Service', 'Variant Price', 'Variant Compare At Price',
        'Variant Requires Shipping', 'Variant Taxable', 'Variant Barcode',
        'Image Src', 'Image Position', 'Image Alt Text', 'Gift Card',
        'SEO Title', 'SEO Description', 'Status'
    ]

    # Metafield columns (dynamic)
    metafield_columns = sorted([col for col in all_columns if col.startswith('Metafield:')])

    # Combine columns
    fieldnames = standard_columns + metafield_columns

    # Write CSV
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(
        description='Export Shopify updates to CSV'
    )
    parser.add_argument(
        '--output', '-o',
        help='Output CSV file path',
        default=None
    )
    parser.add_argument(
        '--collection', '-c',
        help='Filter by collection (e.g., sinks, taps)',
        default=None
    )
    parser.add_argument(
        '--threshold', '-t',
        type=float,
        default=0.6,
        help='Confidence threshold (default: 0.6)'
    )
    parser.add_argument(
        '--limit', '-l',
        type=int,
        default=None,
        help='Max items to export'
    )
    parser.add_argument(
        '--run-id',
        help='Only include items from a specific run_id',
        default=None
    )

    args = parser.parse_args()

    print("╔════════════════════════════════════════════════════════════╗")
    print("║  Export Shopify Updates to CSV                            ║")
    print("╚════════════════════════════════════════════════════════════╝\n")

    try:
        export_shopify_csv(
            output_file=args.output,
            collection=args.collection,
            confidence_threshold=args.threshold,
            limit=args.limit,
            run_id=args.run_id
        )
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
