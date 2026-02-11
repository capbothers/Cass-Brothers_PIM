#!/usr/bin/env python3
"""
Standardize tapware sub-category names and identify misplaced products.

This script:
1. Normalizes inconsistent sub-category names (e.g., "Pull-out Mixer" → "Pull-Out Mixer")
2. Identifies shower fixtures that belong in Showers collection (not Shower Tapware)
3. Identifies accessories that don't belong in Tapware

Usage:
    python scripts/standardize_tapware_subcategories.py [--dry-run]
"""

import sqlite3
import argparse
from datetime import datetime


# ============================================================
# Sub-category standardization mappings
# Maps non-standard names → standard names
# ============================================================

SUBCAT_STANDARDIZATION = {
    # Kitchen Tapware - Pull-out variants
    'Pull-out Mixer': 'Pull-Out Mixer',
    'Pull-Out': 'Pull-Out Mixer',
    'Pull-out': 'Pull-Out Mixer',
    'Pull Out': 'Pull-Out Mixer',
    'Pull-out Mixers': 'Pull-Out Mixer',
    'Pull-Out Mixers': 'Pull-Out Mixer',
    'Pull-Out Spray': 'Pull-Out Mixer',
    'Pull-Down Mixer': 'Pull-Out Mixer',
    'Pull-Down': 'Pull-Out Mixer',
    'Pull-Down Sink Mixer': 'Pull-Out Mixer',
    'Pull-Down Kitchen Mixer': 'Pull-Out Mixer',
    'Gooseneck Pull-Out Mixer': 'Pull-Out Mixer',
    'Gooseneck Pull Out': 'Pull-Out Mixer',

    # Kitchen Tapware - Sink mixer variants
    'Kitchen Mixer': 'Sink Mixer',
    'Sink Mixers': 'Sink Mixer',
    'Specialty Sink Mixers': 'Sink Mixer',
    'Bar Sink Mixer': 'Sink Mixer',
    'Sidelever Mixer': 'Sink Mixer',
    'Sidelever': 'Sink Mixer',
    'Side Lever': 'Sink Mixer',
    'Single Lever': 'Sink Mixer',
    'Kitchen Set': 'Sink Mixer',

    # Kitchen Tapware - Gooseneck
    'Gooseneck': 'Gooseneck Mixer',

    # Kitchen Tapware - Mount types (these should probably be derived differently)
    'Bench Mount': 'Sink Mixer',
    'Countertop': 'Sink Mixer',
    'Countertop Mounted': 'Sink Mixer',
    'Deck Mounted': 'Sink Mixer',
    'Bar Mount': 'Sink Mixer',

    # Kitchen Tapware - Wall mounted
    'Wall Mounted': 'Wall Mixer',

    # Basin Tapware - Wall mixer variants
    'Wall Mixer': 'Wall Basin Mixer',
    'Wall Mount': 'Wall Basin Mixer',
    'Wall Mounted': 'Wall Basin Mixer',

    # Basin Tapware - Vessel
    'Vessel': 'Vessel Mixer',
    'Vessel Basin Mixer': 'Vessel Mixer',

    # Basin Tapware - Mount types
    'Bench Mount': 'Basin Mixer',

    # Basin Tapware - LLM garbage
    'Glass Mounting Kit': None,  # Accessory
    'Glass Mounting': None,  # Accessory
    'Universal Mixer Body': None,  # Component
    'Swivel Spout & Diverter': 'Basin Spout',
    'Straight Bath/Basin Spout': 'Basin Spout',
    'Straight Basin Spout': 'Basin Spout',
    'Wall Spout': 'Basin Spout',
    'Provincial': 'Basin Mixer',
    'Top Assemblies': 'Basin Set',
    '3 Piece Basin Set': 'Basin Set',
    'Accessible Compliant Mixers': 'Basin Mixer',
    'Recessed': 'Basin Mixer',
    'Wall Hung, Freestanding': None,  # Doesn't make sense
    'Bidet Mixer': 'Basin Mixer',  # Keep in Basin Tapware
    'Bar Tap': 'Basin Mixer',
    'Tall': 'Vessel Mixer',  # Tall mixers are typically vessel mixers

    # Bath Tapware - Spout variants
    'Bath Outlet': 'Bath Spout',
    'Bath Spouts': 'Bath Spout',
    'Spout': 'Bath Spout',
    'Wall Spout': 'Bath Spout',
    'Wall Basin/Bath Spout': 'Bath Spout',
    'Basin Spout': 'Bath Spout',  # In bath context

    # Bath Tapware - Mixer variants
    'Wall Mixer': 'Bath Mixer',
    'Wall Bath Mixer': 'Bath Mixer',
    'Bath Mixers': 'Bath Mixer',
    'Bath-Shower Mixer': 'Bath Mixer',
    'Wall Mounted': 'Bath Mixer',
    'Wall Mount': 'Bath Mixer',
    'Hob Mounted': 'Bath Mixer',
    'Recessed': 'Bath Mixer',
    'Basin-Bath Tap Set': 'Bath Mixer',
    'Wall Basin/Bath Set': 'Bath Mixer',
    'Wall Basin Bath Set': 'Bath Mixer',
    'Wall Set': 'Bath Mixer',
    'Bath Set': 'Bath Mixer',

    # Bath Tapware - Floor mounted variants
    'Freestanding': 'Floor Mounted',

    # Shower Tapware - Mixer variants
    'Wall Mixer': 'Shower Mixer',
    'Wall Mixers': 'Shower Mixer',
    'Wall Shower': 'Shower Mixer',
    'Shower Mixers': 'Shower Mixer',
    'Shower/Bath Mixer': 'Shower Mixer',
    'Bath-Shower Mixer': 'Shower Mixer',
    'Wall Mounted': 'Shower Mixer',
    'Exposed': 'Shower Mixer',
    'In-Wall': 'Shower Mixer',
    'In-Wall Rough-In Body': 'Shower Mixer',  # Component for mixer
    'Universal Wall Diverter Mixer Body': 'Diverter',

    # Shower Tapware - Diverter variants
    'Diverter Mixer': 'Diverter',
    'Diverter Mixers': 'Diverter',
    'Wall Diverter Mixer': 'Diverter',
    'Diverter Wall Mixer': 'Diverter',
    'Wall Diverter Mixer Trim Kit': 'Diverter',
    'Wall Diverter': 'Diverter',

    # Clear "None" values
    'None': None,
}

# Keywords that indicate product belongs in Showers collection, not Shower Tapware
SHOWER_FIXTURE_KEYWORDS = [
    'shower rail', 'rail shower', 'twin rail', 'sliding rail',
    'shower on rail', 'slider bar', 'slide rail',
    'showerhead', 'shower head', 'shower rose', 'overhead shower',
    'ceiling shower', 'hand shower', 'handpiece', 'hand piece',
    'shower arm', 'ceiling arm', 'wall arm', 'dropper',
    'shower system', 'twin shower', 'dual shower', 'shower set',
    'bracket', 'elbow', 'douche', 'all directional',
]

# Keywords that indicate product is an accessory, not tapware
ACCESSORY_KEYWORDS = [
    'bath feet', 'bath foot', 'wall stop', 'bath bend',
    'pop down', 'waste', 'plug', 'overflow',
]


def should_move_to_showers(title: str, primary_cat: str) -> bool:
    """Check if product should be in Showers collection instead of Shower Tapware."""
    if primary_cat != 'Shower Tapware':
        return False
    t = title.lower()
    # Don't move if it's clearly a mixer or diverter
    if any(kw in t for kw in ['mixer', 'diverter', 'valve', 'stop tap']):
        return False
    return any(kw in t for kw in SHOWER_FIXTURE_KEYWORDS)


def is_accessory(title: str) -> bool:
    """Check if product is an accessory that doesn't belong in Tapware."""
    t = title.lower()
    # Don't flag if it's clearly tapware
    if any(kw in t for kw in ['mixer', 'tap', 'spout', 'outlet', 'faucet']):
        return False
    return any(kw in t for kw in ACCESSORY_KEYWORDS)


def get_standard_subcat(old_subcat: str, primary_cat: str) -> str | None:
    """Get standardized sub-category name."""
    if not old_subcat or old_subcat == '':
        return None

    # Context-specific mappings
    # "Wall Mounted" means different things in different categories
    if old_subcat == 'Wall Mounted':
        if primary_cat == 'Kitchen Tapware':
            return 'Wall Mixer'
        elif primary_cat == 'Basin Tapware':
            return 'Wall Basin Mixer'
        elif primary_cat == 'Bath Tapware':
            return 'Bath Mixer'
        elif primary_cat == 'Shower Tapware':
            return 'Shower Mixer'

    if old_subcat == 'Wall Mixer':
        if primary_cat == 'Basin Tapware':
            return 'Wall Basin Mixer'
        elif primary_cat == 'Bath Tapware':
            return 'Bath Mixer'
        elif primary_cat == 'Shower Tapware':
            return 'Shower Mixer'

    if old_subcat == 'Bench Mount':
        if primary_cat == 'Kitchen Tapware':
            return 'Sink Mixer'
        elif primary_cat == 'Basin Tapware':
            return 'Basin Mixer'

    if old_subcat in ('Wall Spout', 'Basin Spout'):
        if primary_cat == 'Bath Tapware':
            return 'Bath Spout'

    return SUBCAT_STANDARDIZATION.get(old_subcat, old_subcat)


def main():
    parser = argparse.ArgumentParser(description='Standardize tapware sub-categories')
    parser.add_argument('--dry-run', action='store_true', help='Preview without making changes')
    args = parser.parse_args()

    conn = sqlite3.connect('supplier_products.db')
    cursor = conn.cursor()

    # Get all Tapware products
    cursor.execute("""
        SELECT id, sku, title, primary_category, product_category_type
        FROM shopify_products
        WHERE status = 'active' AND super_category = 'Tapware'
        ORDER BY primary_category, sku
    """)

    products = cursor.fetchall()

    print("=" * 80)
    print("TAPWARE SUB-CATEGORY STANDARDIZATION")
    if args.dry_run:
        print("  MODE: Dry run (no database changes)")
    print("=" * 80)
    print(f"\nTotal Tapware products: {len(products)}")

    # Track changes
    standardization_changes = []
    move_to_showers = []
    accessories = []
    standardization_counts = {}

    for row in products:
        pid, sku, title, primary_cat, old_subcat = row

        # Check if it's an accessory
        if is_accessory(title):
            accessories.append({
                'id': pid,
                'sku': sku,
                'title': title,
                'primary_cat': primary_cat,
            })
            continue

        # Check if it should move to Showers
        if should_move_to_showers(title, primary_cat):
            move_to_showers.append({
                'id': pid,
                'sku': sku,
                'title': title,
            })
            continue

        # Check if sub-category needs standardization
        new_subcat = get_standard_subcat(old_subcat, primary_cat)

        if old_subcat and new_subcat != old_subcat:
            key = f"{old_subcat} → {new_subcat or '(null)'}"
            standardization_counts[key] = standardization_counts.get(key, 0) + 1

            standardization_changes.append({
                'id': pid,
                'sku': sku,
                'title': title,
                'primary_cat': primary_cat,
                'old_subcat': old_subcat,
                'new_subcat': new_subcat,
            })

    # Summary
    print(f"\n--- STANDARDIZATION CHANGES ---")
    print(f"Products to standardize: {len(standardization_changes)}")

    if standardization_counts:
        print(f"\nChanges by type:")
        for key, cnt in sorted(standardization_counts.items(), key=lambda x: -x[1]):
            print(f"  {key}: {cnt}")

    print(f"\n--- PRODUCTS TO MOVE TO SHOWERS ---")
    print(f"Shower fixtures to move: {len(move_to_showers)}")
    if move_to_showers:
        print(f"\nSample (first 20):")
        for item in move_to_showers[:20]:
            print(f"  {item['sku']}: {item['title'][:60]}")

    print(f"\n--- ACCESSORIES ---")
    print(f"Accessories to remove from Tapware: {len(accessories)}")
    if accessories:
        print(f"\nSample:")
        for item in accessories[:10]:
            print(f"  {item['sku']}: {item['title'][:60]}")

    # Apply standardization changes only (not moves)
    if not args.dry_run and standardization_changes:
        for ch in standardization_changes:
            if ch['new_subcat'] is None:
                cursor.execute("""
                    UPDATE shopify_products
                    SET product_category_type = NULL
                    WHERE id = ?
                """, (ch['id'],))
            else:
                cursor.execute("""
                    UPDATE shopify_products
                    SET product_category_type = ?
                    WHERE id = ?
                """, (ch['new_subcat'], ch['id']))

        conn.commit()
        print(f"\n{len(standardization_changes)} products standardized.")
        print(f"\nNote: Use separate scripts to move shower fixtures and accessories.")
    elif args.dry_run:
        print(f"\n[DRY RUN] No changes made.")

    conn.close()


if __name__ == '__main__':
    main()
