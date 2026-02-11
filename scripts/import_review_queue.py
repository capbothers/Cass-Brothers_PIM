"""
Import Reviewed Fields from CSV

Reads a reviewed CSV file and updates the processing queue with approved values.

Usage:
    python scripts/import_review_queue.py review_queue_20260201_123456.csv
    python scripts/import_review_queue.py reviews.csv --dry-run
"""

import sys
import os
import csv
import json
import argparse
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.supplier_db import get_supplier_db


def import_review_queue(csv_file: str, dry_run: bool = False):
    """
    Import reviewed fields from CSV and update processing queue

    Args:
        csv_file: Path to reviewed CSV file
        dry_run: If True, show what would be updated without making changes
    """
    if not os.path.exists(csv_file):
        raise FileNotFoundError(f"CSV file not found: {csv_file}")

    db = get_supplier_db()

    # Read CSV
    reviewed_fields = []
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Only process rows with an approved value
            if row.get('approved_value', '').strip():
                reviewed_fields.append(row)

    if not reviewed_fields:
        print("⚠️  No approved values found in CSV")
        print("   Fill in the 'approved_value' column for fields you want to update")
        return

    print(f"📊 Found {len(reviewed_fields)} approved field values")

    # Group by queue_id
    updates_by_queue_id = defaultdict(dict)
    for field in reviewed_fields:
        queue_id = int(field['queue_id'])
        field_name = field['field_name']
        approved_value = field['approved_value'].strip()

        updates_by_queue_id[queue_id][field_name] = approved_value

    print(f"📦 Updating {len(updates_by_queue_id)} products\n")

    # Apply updates
    updated_count = 0
    error_count = 0

    for queue_id, approved_fields in updates_by_queue_id.items():
        try:
            # Get current item
            item = db.get_processing_queue_item(queue_id)
            if not item:
                print(f"⚠️  Queue item {queue_id} not found, skipping")
                error_count += 1
                continue

            sku = item['sku']

            # Parse existing extracted_data
            extracted_data = {}
            if item.get('extracted_data'):
                try:
                    extracted_data = json.loads(item['extracted_data'])
                except (json.JSONDecodeError, TypeError):
                    pass

            # Parse existing reviewed_data
            reviewed_data = {}
            if item.get('reviewed_data'):
                try:
                    reviewed_data = json.loads(item['reviewed_data'])
                except (json.JSONDecodeError, TypeError):
                    pass

            # Merge approved fields into reviewed_data
            reviewed_data.update(approved_fields)

            if dry_run:
                print(f"[DRY RUN] Would update {sku} (queue_id={queue_id}):")
                for field, value in approved_fields.items():
                    original = extracted_data.get(field, '(none)')
                    print(f"  • {field}: '{original}' → '{value}'")
            else:
                # Update database
                db.update_processing_queue_reviewed_data(queue_id, reviewed_data)

                print(f"✅ Updated {sku} (queue_id={queue_id}):")
                for field, value in approved_fields.items():
                    original = extracted_data.get(field, '(none)')
                    print(f"  • {field}: '{original}' → '{value}'")

            updated_count += 1

        except Exception as e:
            print(f"❌ Error updating queue_id {queue_id}: {e}")
            error_count += 1

    # Summary
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Summary:")
    print(f"  ✅ Updated: {updated_count}")
    print(f"  ❌ Errors: {error_count}")

    if dry_run:
        print(f"\n💡 Run without --dry-run to apply changes")
    else:
        print(f"\n✅ Import complete!")
        print(f"\nNext steps:")
        print(f"1. Use reviewed data when pushing to Shopify")
        print(f"2. Reviewed fields are stored in processing_queue.reviewed_data")
        print(f"3. Original extracted fields remain in processing_queue.extracted_data")


def merge_reviewed_and_extracted(queue_id: int) -> dict:
    """
    Helper function to merge reviewed and extracted data
    Reviewed data takes precedence over extracted data

    Args:
        queue_id: Processing queue ID

    Returns:
        Merged dict of field_name -> value
    """
    db = get_supplier_db()
    item = db.get_processing_queue_item(queue_id)

    if not item:
        return {}

    # Start with extracted data
    merged = {}
    if item.get('extracted_data'):
        try:
            merged = json.loads(item['extracted_data'])
        except (json.JSONDecodeError, TypeError):
            pass

    # Override with reviewed data (if exists)
    if item.get('reviewed_data'):
        try:
            reviewed = json.loads(item['reviewed_data'])
            merged.update(reviewed)  # Reviewed values take precedence
        except (json.JSONDecodeError, TypeError):
            pass

    return merged


def main():
    parser = argparse.ArgumentParser(
        description='Import reviewed fields from CSV'
    )
    parser.add_argument(
        'csv_file',
        help='Path to reviewed CSV file'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be updated without making changes'
    )

    args = parser.parse_args()

    print("╔════════════════════════════════════════════════════════════╗")
    print("║  Import Reviewed Fields                                    ║")
    print("╚════════════════════════════════════════════════════════════╝\n")

    try:
        import_review_queue(
            csv_file=args.csv_file,
            dry_run=args.dry_run
        )
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
