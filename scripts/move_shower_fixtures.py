#!/usr/bin/env python3
"""
Move shower fixtures from Shower Tapware to Showers collection.

Shower Tapware should only contain:
- Shower Mixers
- Diverters

Everything else (rails, showerheads, handpieces, arms, shower systems)
belongs in the Showers collection.

Usage:
    python scripts/move_shower_fixtures.py [--dry-run]
"""

import sqlite3
import argparse
from datetime import datetime


# Keywords that indicate a shower fixture (not tapware)
SHOWER_FIXTURE_KEYWORDS = [
    # Rails
    'shower rail', 'rail shower', 'twin rail', 'sliding rail',
    'shower on rail', 'slider bar', 'slide rail', 'water through rail',
    # Showerheads
    'showerhead', 'shower head', 'shower rose', 'overhead shower',
    'ceiling shower', 'rain shower', 'rose',
    # Hand showers
    'hand shower', 'handpiece', 'hand piece', 'handshower',
    # Arms
    'shower arm', 'ceiling arm', 'wall arm', 'dropper', 'ceiling dropper',
    # Systems/Sets
    'shower system', 'twin shower', 'dual shower', 'shower set',
    # Components
    'bracket', 'elbow', 'douche', 'all directional',
    'adjustable swivel', 'flow control',
]

# Sub-categories that indicate shower fixtures
FIXTURE_SUBCATS = [
    'Shower Rail', 'Rail Shower', 'Twin Rail Shower', 'Rail Showers',
    'Twin Rail Showers', 'Sliding Rail', 'Rail', 'Twin Rail',
    'Water Through Rail', 'Shower Rails',
    'Hand Shower', 'Hand Showers', 'Hand Piece',
    'Shower Arm', 'Shower Arm & Rose', 'Wall Arm', 'Ceiling Dropper',
    'Overhead Shower', 'Ceiling Shower', 'Ceiling Showers', 'Ceiling Mount',
    'Shower Set', 'Shower System', 'Twin Shower', 'Dual Shower',
]

# Derive appropriate sub-category for Showers collection
SHOWERS_SUBCAT_RULES = [
    ('Rail Shower', ['shower rail', 'rail shower', 'twin rail', 'sliding rail', 'slider bar', 'slide rail', 'water through rail']),
    ('Showerhead', ['showerhead', 'shower head', 'shower rose', 'overhead shower', 'ceiling shower', 'rain shower']),
    ('Hand Shower', ['hand shower', 'handpiece', 'hand piece', 'handshower']),
    ('Shower Arm', ['shower arm', 'ceiling arm', 'wall arm', 'dropper', 'ceiling dropper']),
    ('Shower System', ['shower system', 'twin shower', 'dual shower', 'shower set']),
    ('Shower Accessories', ['bracket', 'elbow', 'douche', 'all directional', 'adjustable swivel', 'flow control']),
]


def should_move(title: str, subcat: str) -> bool:
    """Check if product should move to Showers collection."""
    t = title.lower()

    # Don't move if it's clearly a mixer or diverter
    if any(kw in t for kw in ['mixer', 'diverter', 'valve', 'stop tap']):
        return False

    # Move if sub-category indicates fixture
    if subcat and subcat in FIXTURE_SUBCATS:
        return True

    # Move if title contains fixture keywords
    return any(kw in t for kw in SHOWER_FIXTURE_KEYWORDS)


def derive_showers_subcat(title: str) -> str | None:
    """Derive appropriate sub-category for Showers collection."""
    t = title.lower()
    for subcat, keywords in SHOWERS_SUBCAT_RULES:
        if any(kw in t for kw in keywords):
            return subcat
    return None


def main():
    parser = argparse.ArgumentParser(description='Move shower fixtures to Showers collection')
    parser.add_argument('--dry-run', action='store_true', help='Preview without making changes')
    args = parser.parse_args()

    conn = sqlite3.connect('supplier_products.db')
    cursor = conn.cursor()

    # Get Shower Tapware products
    cursor.execute("""
        SELECT id, sku, title, product_category_type
        FROM shopify_products
        WHERE status = 'active'
        AND super_category = 'Tapware'
        AND primary_category = 'Shower Tapware'
        ORDER BY sku
    """)

    products = cursor.fetchall()

    print("=" * 80)
    print("MOVE SHOWER FIXTURES TO SHOWERS COLLECTION")
    if args.dry_run:
        print("  MODE: Dry run (no database changes)")
    print("=" * 80)
    print(f"\nShower Tapware products: {len(products)}")

    # Find products to move
    to_move = []
    subcat_counts = {}

    for row in products:
        pid, sku, title, old_subcat = row

        if should_move(title, old_subcat):
            new_subcat = derive_showers_subcat(title)

            # Track counts
            key = new_subcat or '(none)'
            subcat_counts[key] = subcat_counts.get(key, 0) + 1

            to_move.append({
                'id': pid,
                'sku': sku,
                'title': title,
                'old_subcat': old_subcat,
                'new_subcat': new_subcat,
            })

    print(f"\nProducts to move: {len(to_move)}")

    if subcat_counts:
        print(f"\nNew sub-category distribution:")
        for key, cnt in sorted(subcat_counts.items(), key=lambda x: -x[1]):
            print(f"  {key}: {cnt}")

    if to_move:
        print(f"\nSample products (first 20):")
        for item in to_move[:20]:
            print(f"  {item['sku']}: {item['title'][:55]}")
            print(f"    → Showers / {item['new_subcat'] or '(none)'}")

    # Apply changes
    if not args.dry_run and to_move:
        now = datetime.now().isoformat()
        for item in to_move:
            cursor.execute("""
                UPDATE shopify_products
                SET super_category = 'Showers',
                    primary_category = 'Showers',
                    product_category_type = ?,
                    enriched_at = ?,
                    enriched_confidence = MAX(COALESCE(enriched_confidence, 0), 0.90)
                WHERE id = ?
            """, (item['new_subcat'], now, item['id']))

        conn.commit()
        print(f"\n{len(to_move)} products moved to Showers collection.")
    elif args.dry_run:
        print(f"\n[DRY RUN] No changes made.")

    conn.close()


if __name__ == '__main__':
    main()
