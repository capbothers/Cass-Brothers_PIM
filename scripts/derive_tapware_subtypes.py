#!/usr/bin/env python3
"""
Derive product_category_type for tapware products from title keywords.

This fills in the ~75% of tapware products that have no sub-category.
Only updates products where product_category_type is NULL or empty.

Usage:
    python scripts/derive_tapware_subtypes.py [--dry-run] [--overwrite]
"""

import sqlite3
import argparse


# ============================================================
# Sub-category mappings per primary_category
# Order matters — first match wins
# ============================================================

KITCHEN_TAPWARE_RULES = [
    # Pull-out/pull-down variants (most specific first)
    ('Pull-Out Mixer', ['pull out', 'pull-out', 'pullout', 'pull down', 'pull-down', 'pulldown']),
    # Gooseneck (only if not pull-out)
    ('Gooseneck Mixer', ['gooseneck']),
    # Pot filler
    ('Pot Filler', ['pot filler']),
    # Sink/Kitchen mixer (fallback for mixers)
    ('Sink Mixer', ['sink mixer', 'kitchen mixer', 'bench mixer']),
]

BASIN_TAPWARE_RULES = [
    # Wall-mounted basin mixers
    ('Wall Basin Mixer', ['wall basin', 'wall mounted basin', 'wall mount basin', 'wall mixer', 'wall set', 'wall top assembl', 'wall outlet', 'wall tap set']),
    # Basin set (multiple pieces)
    ('Basin Set', ['basin set', 'basin tap set', 'pillar tap', '3 piece', 'top assembl', 'tap set']),
    # Basin/Bath outlet (versatile spouts)
    ('Basin Spout', ['basin spout', 'basin outlet', 'basin/bath outlet', 'basin & bath outlet', 'basin/bath spout']),
    # Laundry tap
    ('Laundry Tap', ['laundry', 'washing machine']),
    # Vessel mixer (tall, for countertop basins)
    ('Vessel Mixer', ['vessel mixer', 'vessel basin']),
    # Hob/bench mounted
    ('Hob Mixer', ['hob mixer', 'hob mounted', 'hob outlet']),
    # Basin mixer (fallback - catches "basin mixer", "swivel mixer", generic mixers)
    ('Basin Mixer', ['basin mixer', 'basin tap', 'mixer']),
]

SHOWER_TAPWARE_RULES = [
    # Diverter (routes water between outlets)
    ('Diverter', ['diverter']),
    # Shower mixer (fallback)
    ('Shower Mixer', ['shower mixer', 'wall mixer', 'shower wall', 'mixer']),
]

BATH_TAPWARE_RULES = [
    # Floor mounted / freestanding
    ('Floor Mounted', ['floor mounted', 'floor standing', 'freestanding', 'free standing']),
    # Diverter
    ('Diverter', ['diverter']),
    # Bath filler
    ('Bath Filler', ['bath filler']),
    # Bath spout (outlet only) - swivel spout is common bath terminology
    ('Bath Spout', ['bath spout', 'bath outlet', 'swivel spout', 'wall spout']),
    # Bath mixer - be specific to avoid catching basin mixers
    ('Bath Mixer', ['bath mixer', 'bath wall mixer', 'bath tap', 'bath-shower', 'bath/shower', 'shower/wall mixer', 'shower wall mixer']),
]

CATEGORY_RULES = {
    'Kitchen Tapware': KITCHEN_TAPWARE_RULES,
    'Basin Tapware': BASIN_TAPWARE_RULES,
    'Shower Tapware': SHOWER_TAPWARE_RULES,
    'Bath Tapware': BATH_TAPWARE_RULES,
}


def derive_subtype(title: str, primary_category: str) -> str | None:
    """Derive product_category_type from title based on primary_category rules."""
    rules = CATEGORY_RULES.get(primary_category)
    if not rules:
        return None

    t = title.lower()

    for subtype, keywords in rules:
        if any(kw in t for kw in keywords):
            return subtype

    return None


def main():
    parser = argparse.ArgumentParser(description='Derive tapware sub-categories from titles')
    parser.add_argument('--dry-run', action='store_true', help='Preview without making changes')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite existing sub-categories')
    args = parser.parse_args()

    conn = sqlite3.connect('supplier_products.db')
    cursor = conn.cursor()

    # Get tapware products
    if args.overwrite:
        # All tapware products
        cursor.execute("""
            SELECT id, sku, title, primary_category, product_category_type
            FROM shopify_products
            WHERE status = 'active' AND super_category = 'Tapware'
            ORDER BY primary_category, sku
        """)
    else:
        # Only products missing sub-category
        cursor.execute("""
            SELECT id, sku, title, primary_category, product_category_type
            FROM shopify_products
            WHERE status = 'active' AND super_category = 'Tapware'
            AND (product_category_type IS NULL OR product_category_type = '')
            ORDER BY primary_category, sku
        """)

    products = cursor.fetchall()

    print("=" * 80)
    print("TAPWARE SUB-CATEGORY DERIVATION")
    if args.dry_run:
        print("  MODE: Dry run (no database changes)")
    if args.overwrite:
        print("  MODE: Overwriting existing sub-categories")
    print("=" * 80)
    print(f"\nProducts to process: {len(products)}")

    # Track results
    changes = []
    subtype_counts = {}
    unmatched = []

    for row in products:
        pid, sku, title, primary_cat, old_subtype = row

        new_subtype = derive_subtype(title, primary_cat)

        if new_subtype:
            # Track counts
            key = f"{primary_cat} → {new_subtype}"
            subtype_counts[key] = subtype_counts.get(key, 0) + 1

            if old_subtype != new_subtype:
                changes.append({
                    'id': pid,
                    'sku': sku,
                    'title': title,
                    'primary_cat': primary_cat,
                    'old_subtype': old_subtype,
                    'new_subtype': new_subtype,
                })
        else:
            unmatched.append({
                'sku': sku,
                'title': title,
                'primary_cat': primary_cat,
            })

    # Summary
    print(f"\nSub-types derived: {len(products) - len(unmatched)}")
    print(f"Could not derive: {len(unmatched)}")
    print(f"Changes needed: {len(changes)}")

    print(f"\nSub-type distribution:")
    for key, cnt in sorted(subtype_counts.items(), key=lambda x: (-x[1], x[0])):
        print(f"  {key}: {cnt}")

    # Show unmatched samples
    if unmatched:
        print(f"\nUnmatched products (first 20):")
        for item in unmatched[:20]:
            print(f"  [{item['primary_cat']}] {item['title'][:70]}")

    # Show sample changes
    if changes:
        print(f"\nSample changes (first 15):")
        for ch in changes[:15]:
            print(f"  {ch['sku']}: {ch['title'][:55]}")
            print(f"    {ch['old_subtype'] or '(none)'} → {ch['new_subtype']}")

    # Apply changes
    if not args.dry_run and changes:
        for ch in changes:
            cursor.execute("""
                UPDATE shopify_products
                SET product_category_type = ?
                WHERE id = ?
            """, (ch['new_subtype'], ch['id']))

        conn.commit()
        print(f"\n{len(changes)} products updated.")
    elif args.dry_run:
        print(f"\n[DRY RUN] No changes made.")

    conn.close()


if __name__ == '__main__':
    main()
