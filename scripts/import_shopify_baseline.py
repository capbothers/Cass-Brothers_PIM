#!/usr/bin/env python3
"""
Import Shopify Baseline CSV into SQLite Database

Reads shopify_baseline.csv and imports all rows into the shopify_products
table using the SupplierDatabase class.

Usage:
    python scripts/import_shopify_baseline.py
    python scripts/import_shopify_baseline.py --csv shopify_baseline.csv
    python scripts/import_shopify_baseline.py --db supplier_products.db
"""

import os
import sys
import csv
import argparse
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from core.supplier_db import SupplierDatabase


def main():
    parser = argparse.ArgumentParser(description='Import Shopify baseline CSV into SQLite')
    parser.add_argument('--csv', default='shopify_baseline.csv',
                       help='Path to Shopify baseline CSV (default: shopify_baseline.csv)')
    parser.add_argument('--db', default='supplier_products.db',
                       help='SQLite database path (default: supplier_products.db)')
    parser.add_argument('--batch-size', type=int, default=1000,
                       help='Number of rows to import per batch (default: 1000)')
    parser.add_argument('--clear', action='store_true',
                       help='Clear existing shopify_products data before import')

    args = parser.parse_args()

    csv_path = os.path.join(REPO_ROOT, args.csv)
    db_path = os.path.join(REPO_ROOT, args.db)

    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found.")
        print("Run scripts/export_shopify_products.py first to create the baseline CSV.")
        sys.exit(1)

    print("=" * 70)
    print("  Import Shopify Baseline into SQLite")
    print("=" * 70)
    print(f"\nCSV:      {csv_path}")
    print(f"Database: {db_path}")

    # Count rows first
    with open(csv_path, 'r', encoding='utf-8') as f:
        row_count = sum(1 for _ in f) - 1  # minus header
    print(f"Rows:     {row_count:,}")

    # Initialize database
    db = SupplierDatabase(db_path=db_path)

    # Clear existing data if requested
    if args.clear:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.execute('DELETE FROM shopify_products')
        conn.commit()
        conn.close()
        print("\nCleared existing shopify_products data.")

    # Read CSV and import in batches
    print(f"\nImporting in batches of {args.batch_size}...")

    total_imported = 0
    total_skipped = 0
    batch = []
    batch_num = 0
    start_time = time.time()

    # Fields to exclude from raw_json to save space (body_html can be huge)
    EXCLUDE_FROM_RAW = {'body_html'}

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            # Strip body_html from the row dict to save DB space
            # (body_html_length is already stored separately)
            clean_row = {k: v for k, v in row.items() if k not in EXCLUDE_FROM_RAW}
            batch.append(clean_row)

            if len(batch) >= args.batch_size:
                batch_num += 1
                result = db.import_shopify_baseline_rows(batch)
                total_imported += result['imported']
                total_skipped += result['skipped']
                processed = total_imported + total_skipped
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                print(f"  Batch {batch_num}: {processed:>6,} / {row_count:,}  "
                      f"({processed * 100 / row_count:.1f}%)  "
                      f"[{rate:.0f} rows/sec]", end='\r')
                batch = []

        # Import remaining rows
        if batch:
            batch_num += 1
            result = db.import_shopify_baseline_rows(batch)
            total_imported += result['imported']
            total_skipped += result['skipped']

    elapsed = time.time() - start_time
    print(f"\n\nDone in {elapsed:.1f}s")

    # Print stats
    stats = db.get_shopify_baseline_stats()
    print(f"\n{'=' * 70}")
    print("IMPORT SUMMARY")
    print(f"{'=' * 70}")
    print(f"Rows imported:     {total_imported:,}")
    print(f"Rows skipped:      {total_skipped:,}")
    print(f"\nDatabase stats:")
    print(f"  Total rows:      {stats['total_rows']:,}")
    print(f"  Distinct SKUs:   {stats['distinct_skus']:,}")
    print(f"  Distinct vendors: {stats['distinct_vendors']:,}")
    print(f"  Last imported:   {stats['last_imported_at']}")


if __name__ == "__main__":
    main()
