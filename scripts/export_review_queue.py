"""
Export Manual Review Queue to CSV

Exports all low-confidence extracted fields to a CSV file for manual review.

Usage:
    python scripts/export_review_queue.py
    python scripts/export_review_queue.py --threshold 0.7 --output reviews.csv
"""

import sys
import os
import csv
import json
import argparse
import datetime
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
confidence_scorer_module = _import_module_from_path("confidence_scorer", os.path.join("core", "confidence_scorer.py"))

get_supplier_db = supplier_db_module.get_supplier_db
get_confidence_scorer = confidence_scorer_module.get_confidence_scorer


def export_review_queue(
    output_file: str = None,
    confidence_threshold: float = 0.6,
    supplier_filter: str = None,
    since_hours: float = None,
    run_id: str = None
):
    """
    Export low-confidence fields to CSV for manual review

    Args:
        output_file: Path to output CSV file (default: review_queue_YYYYMMDD_HHMMSS.csv)
        confidence_threshold: Export fields below this confidence score
    """
    db = get_supplier_db()

    # Generate output filename if not provided
    if output_file is None:
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f'review_queue_{timestamp}.csv'

    # Get items needing review
    items = db.get_items_needing_review(confidence_threshold=confidence_threshold)
    if supplier_filter:
        supplier_filter_lower = supplier_filter.lower()
        items = [
            item for item in items
            if supplier_filter_lower in (item.get('supplier_name') or '').lower()
        ]
    if since_hours is not None:
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=since_hours)
        items = [
            item for item in items
            if item.get('updated_at') and item['updated_at'] >= cutoff.strftime("%Y-%m-%d %H:%M:%S")
        ]
    if run_id:
        items = [item for item in items if item.get('run_id') == run_id]

    if not items:
        print(f"✅ No items need review (all above {confidence_threshold:.0%} confidence)")
        return

    print(f"📊 Found {len(items)} items with low-confidence fields")

    # Prepare CSV rows
    csv_rows = []
    total_fields = 0

    for item in items:
        queue_id = item['id']
        sku = item['sku']
        collection = item['target_collection']
        title = item.get('title', '')
        supplier_name = item.get('supplier_name', '')
        product_url = item.get('product_url', '')
        spec_sheet_url = item.get('spec_sheet_url', '')

        # Parse extracted data
        extracted_data = {}
        if item.get('extracted_data'):
            try:
                extracted_data = json.loads(item['extracted_data'])
            except (json.JSONDecodeError, TypeError):
                pass

        # Parse reviewed data (to exclude already-approved fields)
        reviewed_data = {}
        if item.get('reviewed_data'):
            try:
                reviewed_data = json.loads(item['reviewed_data'])
            except (json.JSONDecodeError, TypeError):
                pass

        # Parse confidence summary
        confidence_summary = {}
        if item.get('confidence_summary'):
            try:
                confidence_summary = json.loads(item['confidence_summary'])
            except (json.JSONDecodeError, TypeError):
                pass

        # Get field scores
        field_scores = confidence_summary.get('field_scores', {})

        # Export each low-confidence field
        for field_name, score_data in field_scores.items():
            confidence = score_data.get('confidence', 0.0)
            auto_apply = score_data.get('auto_apply', True)

            # Only export fields that need review
            if not auto_apply or confidence < confidence_threshold:
                if field_name in reviewed_data:
                    continue
                extracted_value = score_data.get('value', '')

                # Determine reason for low confidence
                reason = get_low_confidence_reason(field_name, extracted_value, confidence)

                csv_rows.append({
                    'queue_id': queue_id,
                    'sku': sku,
                    'collection': collection,
                    'title': title,
                    'supplier_name': supplier_name,
                    'product_url': product_url,
                    'spec_sheet_url': spec_sheet_url,
                    'field_name': field_name,
                    'extracted_value': extracted_value,
                    'confidence_score': f"{confidence:.3f}",
                    'reason': reason,
                    'approved_value': '',  # To be filled by reviewer
                    'notes': ''  # Optional reviewer notes
                })
                total_fields += 1

    if not csv_rows:
        print(f"✅ No low-confidence fields found")
        return

    # Write CSV
    fieldnames = [
        'queue_id', 'sku', 'collection', 'title', 'supplier_name',
        'product_url', 'spec_sheet_url', 'field_name', 'extracted_value',
        'confidence_score', 'reason', 'approved_value', 'notes'
    ]

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"\n✅ Exported {total_fields} low-confidence fields from {len(items)} products")
    print(f"📄 Output file: {output_file}")
    print(f"\nNext steps:")
    print(f"1. Open {output_file} in Excel/Google Sheets")
    print(f"2. Review each field and fill in 'approved_value' column")
    print(f"3. Save the CSV")
    print(f"4. Run: python scripts/import_review_queue.py {output_file}")

    return output_file


def get_low_confidence_reason(field_name: str, value: str, confidence: float) -> str:
    """Generate a human-readable reason for low confidence"""
    value_str = str(value).lower()

    # Check for guess indicators
    guess_indicators = ['approx', 'estimated', 'about', 'around', 'roughly', '~']
    if any(indicator in value_str for indicator in guess_indicators):
        return "Contains guess indicator"

    # Check for placeholder values
    if value_str in ['n/a', 'unknown', 'tbd', 'null', 'none', '']:
        return "Placeholder/empty value"

    # Field type issues
    if 'description' in field_name.lower() or 'feature' in field_name.lower():
        return "Free text field (needs review)"

    # Generic low confidence
    if confidence < 0.3:
        return "Very low confidence"
    elif confidence < 0.5:
        return "Low confidence"
    else:
        return "Below threshold"


def main():
    parser = argparse.ArgumentParser(
        description='Export low-confidence fields to CSV for manual review'
    )
    parser.add_argument(
        '--output', '-o',
        help='Output CSV file path',
        default=None
    )
    parser.add_argument(
        '--threshold', '-t',
        type=float,
        default=0.6,
        help='Confidence threshold (default: 0.6)'
    )
    parser.add_argument(
        '--supplier', '-s',
        help='Filter by supplier name/domain',
        default=None
    )
    parser.add_argument(
        '--since-hours',
        type=float,
        default=None,
        help='Only include items updated within the last N hours'
    )
    parser.add_argument(
        '--run-id',
        help='Only include items from a specific run_id',
        default=None
    )

    args = parser.parse_args()

    print("╔════════════════════════════════════════════════════════════╗")
    print("║  Export Manual Review Queue                                ║")
    print("╚════════════════════════════════════════════════════════════╝\n")

    try:
        export_review_queue(
            output_file=args.output,
            confidence_threshold=args.threshold,
            supplier_filter=args.supplier,
            since_hours=args.since_hours,
            run_id=args.run_id
        )
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
