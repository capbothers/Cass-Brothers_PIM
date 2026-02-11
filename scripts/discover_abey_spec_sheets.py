"""
Discover Spec Sheets for Abey Products

Standalone script to find and store spec sheet URLs for all Abey products
in the supplier_products table.

Usage:
    python scripts/discover_abey_spec_sheets.py
    python scripts/discover_abey_spec_sheets.py --limit 50
    python scripts/discover_abey_spec_sheets.py --rescrape --days 30
    python scripts/discover_abey_spec_sheets.py --dry-run
"""

import sys
import os
import argparse
import time
from datetime import datetime
import importlib.util

# Import modules by path to avoid __init__.py issues
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _import_module_from_path(module_name: str, relative_path: str):
    """Import a module by file path to avoid loading core/__init__.py."""
    module_path = os.path.join(REPO_ROOT, relative_path)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

supplier_db_module = _import_module_from_path("supplier_db", os.path.join("core", "supplier_db.py"))
spec_sheet_scraper_module = _import_module_from_path("spec_sheet_scraper", os.path.join("core", "spec_sheet_scraper.py"))

get_supplier_db = supplier_db_module.get_supplier_db
get_spec_sheet_scraper = spec_sheet_scraper_module.get_spec_sheet_scraper


def get_abey_products(db, limit: int = None, rescrape: bool = False, days_old: int = 30):
    """
    Get Abey products that need spec sheet discovery

    Args:
        db: SupplierDatabase instance
        limit: Max products to return
        rescrape: If True, include products that were scraped >days_old ago
        days_old: Days since last scrape to consider for rescrape

    Returns:
        List of product dicts
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if rescrape:
        # Get products that haven't been scraped recently
        query = '''
            SELECT * FROM supplier_products
            WHERE supplier_name LIKE '%abey%'
              AND (last_scraped_at IS NULL
                   OR last_scraped_at < datetime('now', '-' || ? || ' days'))
            ORDER BY last_scraped_at ASC NULLS FIRST
        '''
        params = [days_old]
    else:
        # Get products without spec sheet URLs
        query = '''
            SELECT * FROM supplier_products
            WHERE supplier_name LIKE '%abey%'
              AND (spec_sheet_url IS NULL OR spec_sheet_url = '')
            ORDER BY updated_at DESC
        '''
        params = []

    if limit:
        query += ' LIMIT ?'
        params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def discover_spec_sheets(dry_run: bool = False, limit: int = None,
                        rescrape: bool = False, days_old: int = 30,
                        rate_limit: float = 1.0):
    """
    Main discovery function

    Args:
        dry_run: If True, don't save to database
        limit: Max products to process
        rescrape: If True, re-scrape products scraped >days_old ago
        days_old: Days threshold for rescraping
        rate_limit: Seconds between requests

    Returns:
        Dict with statistics
    """
    db = get_supplier_db()
    scraper = get_spec_sheet_scraper()

    print("╔════════════════════════════════════════════════════════════╗")
    print("║  Abey Spec Sheet Discovery                                ║")
    print("╚════════════════════════════════════════════════════════════╝\n")

    # Get products to process
    products = get_abey_products(db, limit=limit, rescrape=rescrape, days_old=days_old)

    if not products:
        print("✅ No Abey products need spec sheet discovery")
        return {
            'total': 0,
            'found': 0,
            'not_found': 0,
            'errors': 0
        }

    print(f"Found {len(products)} Abey products to process")
    if dry_run:
        print("🔍 DRY RUN MODE - No database changes will be made\n")
    else:
        print()

    stats = {
        'total': len(products),
        'found': 0,
        'not_found': 0,
        'errors': 0,
        'found_skus': [],
        'not_found_skus': []
    }

    # Process each product
    for i, product in enumerate(products, 1):
        sku = product['sku']
        product_url = product['product_url']

        print(f"[{i}/{len(products)}] {sku}...", end=" ", flush=True)

        try:
            # Discover spec sheet with Abey hint
            spec_sheet_url = scraper.find_spec_sheet_url(product_url, supplier_hint='abey.com.au')

            if spec_sheet_url:
                print(f"✅ Found: {spec_sheet_url[:60]}...")
                stats['found'] += 1
                stats['found_skus'].append(sku)

                if not dry_run:
                    db.update_spec_sheet_url(sku, spec_sheet_url)
            else:
                print(f"⚠️  Not found")
                stats['not_found'] += 1
                stats['not_found_skus'].append(sku)

                if not dry_run:
                    # Update timestamp even if not found
                    db.update_spec_sheet_url(sku, '')

            # Rate limiting
            if i < len(products):
                time.sleep(rate_limit)

        except Exception as e:
            print(f"❌ Error: {e}")
            stats['errors'] += 1

    # Print summary
    print("\n" + "=" * 60)
    print("DISCOVERY SUMMARY")
    print("=" * 60)
    print(f"Total Products: {stats['total']}")
    print(f"✅ Spec Sheets Found: {stats['found']} ({stats['found']/stats['total']*100:.1f}%)")
    print(f"⚠️  Not Found: {stats['not_found']} ({stats['not_found']/stats['total']*100:.1f}%)")
    print(f"❌ Errors: {stats['errors']}")

    if stats['found_skus']:
        print(f"\nSample found SKUs (first 5):")
        for sku in stats['found_skus'][:5]:
            print(f"  • {sku}")

    if stats['not_found_skus'] and len(stats['not_found_skus']) <= 10:
        print(f"\nSKUs without spec sheets:")
        for sku in stats['not_found_skus']:
            print(f"  • {sku}")

    if dry_run:
        print(f"\n💡 This was a dry run. Run without --dry-run to save results.")
    else:
        print(f"\n💾 Results saved to database (spec_sheet_url + last_scraped_at updated)")

    print("\n📋 Next Steps:")
    if stats['found'] > 0:
        print("  1. Run pilot to test extraction:")
        print("     python scripts/run_pilot.py --supplier abey.com.au --limit 10")
    if stats['not_found'] > 0:
        print("  2. Manually check products without spec sheets")
        print("  3. Consider updating scraper patterns if success rate is low")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description='Discover and store spec sheet URLs for Abey products'
    )
    parser.add_argument(
        '--limit', '-l',
        type=int,
        default=None,
        help='Max products to process (default: all)'
    )
    parser.add_argument(
        '--rescrape',
        action='store_true',
        help='Re-scrape products scraped more than --days ago'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=30,
        help='Days threshold for re-scraping (default: 30)'
    )
    parser.add_argument(
        '--rate-limit',
        type=float,
        default=1.0,
        help='Seconds between requests (default: 1.0)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview without saving to database'
    )

    args = parser.parse_args()

    try:
        stats = discover_spec_sheets(
            dry_run=args.dry_run,
            limit=args.limit,
            rescrape=args.rescrape,
            days_old=args.days,
            rate_limit=args.rate_limit
        )

        # Exit code based on success rate
        success_rate = stats['found'] / stats['total'] if stats['total'] > 0 else 0
        if success_rate < 0.5:
            print(f"\n⚠️  Warning: Low success rate ({success_rate:.1%})")
            print("   Consider reviewing scraper patterns for Abey")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n⚠️  Discovery interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
