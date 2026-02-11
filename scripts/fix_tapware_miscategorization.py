#!/usr/bin/env python3
"""
Fix miscategorized products in the Tapware collection.

Moves products that are obviously NOT tapware to their correct categories:
- Velux skylights → Skylights (super: Other)
- Basins → Basins (super: Basins)
- Accessories (wastes, traps, dress rings) → Bathroom Accessories
- Tools (hex keys) → Tools (super: Other)

Usage:
    python scripts/fix_tapware_miscategorization.py [--dry-run]
"""

import sqlite3
import argparse
from datetime import datetime


# ============================================================
# Miscategorization detection rules
# Products matching these patterns should NOT be in Tapware
# ============================================================

SKYLIGHT_KEYWORDS = ['velux', 'skylight', 'roof window']

BASIN_KEYWORDS = [
    'bench basin', 'pedestal basin', 'semi-recessed basin',
    'inset basin', 'under counter basin', 'above counter basin',
    'countertop basin', 'vessel basin', 'semi pedestal', 'corner basin',
    'oval basin', 'round basin', 'rectangular basin', 'square basin',
    'grey basin', 'white basin', 'black basin',  # Color + basin combos
]
# Note: "wall basin" removed - matches wall basin mixers/outlets which are tapware

# These are accessories, not tapware
ACCESSORY_KEYWORDS = [
    'waste', 'trap', 'dress ring', 'dome strainer',
    'plug and waste', 'pop up waste', 'click clack',
    'bath feet', 'bath foot', 'bath bend', 'wall stop',
    'glass mounting kit',  # Specific - don't use generic "mounting kit"
]

TOOL_KEYWORDS = ['hex key', 'tool set', 'allen key', 'wrench set', 'key set']


def detect_miscategorization(title: str, vendor: str) -> tuple[str, str, str] | None:
    """
    Detect if a product is miscategorized in Tapware.

    Returns (new_super_category, new_primary_category, new_product_category_type)
    or None if the product belongs in Tapware.
    """
    t = title.lower()
    v = vendor.lower() if vendor else ''

    # Skylights (Velux products)
    if 'velux' in v or any(kw in t for kw in SKYLIGHT_KEYWORDS):
        return ('Other', 'Skylights', None)

    # Tools
    if any(kw in t for kw in TOOL_KEYWORDS):
        return ('Other', 'Tools', None)

    # Basins (actual basin products, not basin tapware)
    # Must check these carefully - "basin mixer" is tapware, "bench basin" is not
    if any(kw in t for kw in BASIN_KEYWORDS):
        # Make sure it's not actually tapware
        if not any(tw in t for tw in ['mixer', 'tap', 'spout', 'outlet', 'diverter']):
            return ('Basins', 'Basins', None)

    # Accessories (wastes, traps, etc.)
    if any(kw in t for kw in ACCESSORY_KEYWORDS):
        # Make sure it's not part of a tapware product name
        if not any(tw in t for tw in ['mixer', 'tap', 'spout', 'outlet', 'diverter']):
            return ('Bathroom', 'Bathroom Accessories', 'Wastes & Traps')

    return None


def main():
    parser = argparse.ArgumentParser(description='Fix miscategorized Tapware products')
    parser.add_argument('--dry-run', action='store_true', help='Preview without making changes')
    args = parser.parse_args()

    conn = sqlite3.connect('supplier_products.db')
    cursor = conn.cursor()

    # Get all active Tapware products
    cursor.execute("""
        SELECT id, sku, title, vendor, super_category, primary_category, product_category_type
        FROM shopify_products
        WHERE status = 'active' AND super_category = 'Tapware'
        ORDER BY vendor, sku
    """)

    products = cursor.fetchall()

    print("=" * 80)
    print("TAPWARE MISCATEGORIZATION FIX")
    if args.dry_run:
        print("  MODE: Dry run (no database changes)")
    print("=" * 80)
    print(f"\nTotal Tapware products: {len(products)}")

    # Find miscategorized products
    changes = []
    category_counts = {}

    for row in products:
        pid, sku, title, vendor, old_super, old_cat, old_subcat = row

        result = detect_miscategorization(title, vendor)
        if result:
            new_super, new_cat, new_subcat = result

            # Track by new category
            key = f"{new_super} → {new_cat}"
            category_counts[key] = category_counts.get(key, 0) + 1

            changes.append({
                'id': pid,
                'sku': sku,
                'title': title,
                'vendor': vendor,
                'old_super': old_super,
                'old_cat': old_cat,
                'old_subcat': old_subcat,
                'new_super': new_super,
                'new_cat': new_cat,
                'new_subcat': new_subcat,
            })

    print(f"\nMiscategorized products found: {len(changes)}")

    if category_counts:
        print(f"\nBy new category:")
        for key, cnt in sorted(category_counts.items(), key=lambda x: -x[1]):
            print(f"  {key}: {cnt}")

    # Show samples by category
    if changes:
        print(f"\nSample products by category:")

        # Group by new category
        by_cat = {}
        for ch in changes:
            key = ch['new_cat']
            if key not in by_cat:
                by_cat[key] = []
            by_cat[key].append(ch)

        for cat, items in sorted(by_cat.items()):
            print(f"\n  {cat} ({len(items)} products):")
            for ch in items[:5]:
                print(f"    • {ch['sku']}: {ch['title'][:60]}")
            if len(items) > 5:
                print(f"    ... and {len(items) - 5} more")

    # Apply changes
    if not args.dry_run and changes:
        now = datetime.now().isoformat()
        for ch in changes:
            cursor.execute("""
                UPDATE shopify_products
                SET super_category = ?,
                    primary_category = ?,
                    product_category_type = ?,
                    enriched_at = ?,
                    enriched_confidence = MAX(COALESCE(enriched_confidence, 0), 0.95)
                WHERE id = ?
            """, (ch['new_super'], ch['new_cat'], ch['new_subcat'], now, ch['id']))

        conn.commit()
        print(f"\n{len(changes)} products recategorized.")
    elif args.dry_run:
        print(f"\n[DRY RUN] No changes made.")

    conn.close()


if __name__ == '__main__':
    main()
