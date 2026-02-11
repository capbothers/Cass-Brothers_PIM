#!/usr/bin/env python3
"""
Re-categorize Boiling/Chilled/Sparkling collection products.

Uses the boolean capability flags (is_boiling, is_chilled, is_sparkling, is_filtered, is_ambient)
to assign correct primary_category, product_category_type, and super_category.

These products should NOT be in "Kitchen Tapware" — they belong in BCS-specific categories.

Usage:
    python scripts/recategorize_bcs_products.py [--dry-run]
"""

import sqlite3
import argparse
from datetime import datetime


def derive_primary_category(b, c, s, f, a, is_accessory):
    """Derive primary_category from boolean capabilities.

    Priority: Boiling > Chilled > Sparkling > Filtered Only
    Accessories go to Kitchen Accessories.
    """
    if is_accessory:
        return 'Kitchen Accessories'
    if b:
        return 'Boiling Water Taps'
    if c:
        return 'Chilled Water Taps'
    if s:
        return 'Sparkling Water Taps'
    if f:
        return 'Filtered Water Taps'
    # Shouldn't happen — product has capabilities set but none are true
    return None


def derive_product_category_type(b, c, s, f, a, is_accessory):
    """Derive product_category_type from the combination of capabilities."""
    if is_accessory:
        return 'Accessories'

    caps = []
    if b:
        caps.append('Boiling')
    if c:
        caps.append('Chilled')
    if s:
        caps.append('Sparkling')

    if caps:
        if len(caps) == 3:
            return 'Boiling, Chilled & Sparkling'
        elif len(caps) == 2:
            return f'{caps[0]} & {caps[1]}'
        else:
            return caps[0]

    # No boiling/chilled/sparkling — filtered only
    if f:
        return 'Filtered Water'

    return None


def main():
    parser = argparse.ArgumentParser(description='Re-categorize BCS collection products')
    parser.add_argument('--dry-run', action='store_true', help='Preview without making changes')
    args = parser.parse_args()

    conn = sqlite3.connect('supplier_products.db')
    cursor = conn.cursor()

    # Get all products with capability flags set
    cursor.execute("""
        SELECT id, sku, title, vendor,
               is_boiling, is_chilled, is_sparkling, is_filtered, is_ambient,
               primary_category, product_category_type, super_category
        FROM shopify_products
        WHERE status = 'active' AND is_boiling IS NOT NULL
        ORDER BY vendor, sku
    """)

    products = cursor.fetchall()
    print("=" * 80)
    print("BCS PRODUCT RE-CATEGORIZATION")
    if args.dry_run:
        print("  MODE: Dry run (no database changes)")
    print("=" * 80)
    print(f"\nProducts with capability flags: {len(products)}")

    changes = []
    category_counts = {}
    subcat_counts = {}

    for row in products:
        pid, sku, title, vendor, b, c, s, f, a, old_cat, old_subcat, old_super = row

        is_accessory = (b == 0 and c == 0 and s == 0 and f == 0 and a == 0)

        new_cat = derive_primary_category(b, c, s, f, a, is_accessory)
        new_subcat = derive_product_category_type(b, c, s, f, a, is_accessory)
        new_super = 'Boiling, Chilled & Sparkling'

        if new_cat is None:
            continue

        # Track counts
        category_counts[new_cat] = category_counts.get(new_cat, 0) + 1
        if new_subcat:
            subcat_counts[new_subcat] = subcat_counts.get(new_subcat, 0) + 1

        # Check if anything changed
        changed = (old_cat != new_cat or old_subcat != new_subcat or old_super != new_super)
        if changed:
            changes.append({
                'id': pid,
                'sku': sku,
                'title': title,
                'vendor': vendor,
                'old_cat': old_cat,
                'new_cat': new_cat,
                'old_subcat': old_subcat,
                'new_subcat': new_subcat,
                'old_super': old_super,
                'new_super': new_super,
            })

    # Summary
    print(f"\nChanges needed: {len(changes)}")

    print(f"\nNew primary_category distribution:")
    for cat, cnt in sorted(category_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {cnt}")

    print(f"\nNew product_category_type distribution:")
    for subcat, cnt in sorted(subcat_counts.items(), key=lambda x: -x[1]):
        print(f"  {subcat}: {cnt}")

    # Show what's changing
    old_cat_counts = {}
    for ch in changes:
        key = f"{ch['old_cat']} → {ch['new_cat']}"
        old_cat_counts[key] = old_cat_counts.get(key, 0) + 1

    if old_cat_counts:
        print(f"\nCategory migrations:")
        for migration, cnt in sorted(old_cat_counts.items(), key=lambda x: -x[1]):
            print(f"  {migration}: {cnt}")

    # Show a few examples
    if changes:
        print(f"\nSample changes (first 10):")
        for ch in changes[:10]:
            print(f"  {ch['sku']} ({ch['vendor']}): {ch['title'][:55]}")
            print(f"    cat: {ch['old_cat']} → {ch['new_cat']}")
            print(f"    sub: {ch['old_subcat']} → {ch['new_subcat']}")

    # Apply changes
    if not args.dry_run and changes:
        now = datetime.now().isoformat()
        for ch in changes:
            cursor.execute("""
                UPDATE shopify_products
                SET primary_category = ?,
                    product_category_type = ?,
                    super_category = ?,
                    enriched_at = ?,
                    enriched_confidence = MAX(COALESCE(enriched_confidence, 0), 0.90)
                WHERE id = ?
            """, (ch['new_cat'], ch['new_subcat'], ch['new_super'], now, ch['id']))

        conn.commit()
        print(f"\n{len(changes)} products updated.")
    elif args.dry_run:
        print(f"\n[DRY RUN] No changes made.")

    conn.close()


if __name__ == '__main__':
    main()
