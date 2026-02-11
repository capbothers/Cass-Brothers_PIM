#!/usr/bin/env python3
"""
Standardize installation_type values for Tapware products.

Standard values for Tapware:
- Hob Mounted (bench/deck/countertop/basin mounted)
- Wall Mounted
- Floor Mounted (freestanding)
- In-Wall (concealed/recessed)
- Ceiling Mounted

Usage:
    python scripts/standardize_installation_types.py [--dry-run]
"""

import sqlite3
import argparse


# ============================================================
# Installation type standardization mappings for Tapware
# ============================================================

TAPWARE_INSTALLATION_MAPPINGS = {
    # Hob Mounted variants (bench/deck/countertop)
    'deck mounted': 'Hob Mounted',
    'deck mount': 'Hob Mounted',
    'hob mounted': 'Hob Mounted',
    'hob mounted, fixed position': 'Hob Mounted',
    'bench mount': 'Hob Mounted',
    'bench mounted': 'Hob Mounted',
    'countertop': 'Hob Mounted',
    'countertop mounted': 'Hob Mounted',
    'basin mounted': 'Hob Mounted',
    'basin mount': 'Hob Mounted',
    'sink mounted': 'Hob Mounted',
    'bar mount': 'Hob Mounted',
    'bath hob mount': 'Hob Mounted',
    'surface mounted': 'Hob Mounted',

    # Wall Mounted variants
    'wall mounted': 'Wall Mounted',
    'wall mount': 'Wall Mounted',
    'wall mounted, freestanding': 'Wall Mounted',

    # Floor Mounted variants
    'floor mounted': 'Floor Mounted',
    'floor standing': 'Floor Mounted',
    'freestanding': 'Floor Mounted',

    # In-Wall variants
    'in-wall': 'In-Wall',
    'in-wall rough-in body': 'In-Wall',
    'concealed': 'In-Wall',
    'recessed': 'In-Wall',
    'push-fit': 'In-Wall',

    # Ceiling Mounted
    'ceiling mounted': 'Ceiling Mounted',
}

# Values to clear (junk/invalid)
JUNK_VALUES = [
    'n/a', 'na', 'none', 'null', '-', '?', 'unknown',
    'not specified', 'not provided', 'no installation type provided',
    'value', 'fixed position',
    # Product types (not installation types)
    'basin mixer', 'sink mixer', 'single hole kitchen mixer',
    'pull-down', 'pull-out',
    # Other invalid
    'designed for basins', 'as 1428.1:2021 accessible compliance',
    'glass mounting',
]


def standardize_installation_type(value: str) -> str | None:
    """
    Standardize an installation_type value.
    Returns the standard value, or None if it should be cleared.
    """
    if not value:
        return None

    normalized = value.lower().strip()

    # Check if it's junk
    if normalized in JUNK_VALUES:
        return None

    # Check if we have a mapping
    if normalized in TAPWARE_INSTALLATION_MAPPINGS:
        return TAPWARE_INSTALLATION_MAPPINGS[normalized]

    # Return as-is if it's already a standard value
    standard_values = {'Hob Mounted', 'Wall Mounted', 'Floor Mounted', 'In-Wall', 'Ceiling Mounted'}
    if value in standard_values:
        return value

    # Unknown value - return None to clear
    return None


def main():
    parser = argparse.ArgumentParser(description='Standardize Tapware installation types')
    parser.add_argument('--dry-run', action='store_true', help='Preview without making changes')
    args = parser.parse_args()

    conn = sqlite3.connect('supplier_products.db')
    cursor = conn.cursor()

    # Get all Tapware products with installation_type
    cursor.execute("""
        SELECT id, sku, title, installation_type
        FROM shopify_products
        WHERE status = 'active'
        AND super_category = 'Tapware'
        AND installation_type IS NOT NULL
        ORDER BY installation_type
    """)

    products = cursor.fetchall()

    print("=" * 80)
    print("STANDARDIZE TAPWARE INSTALLATION TYPES")
    if args.dry_run:
        print("  MODE: Dry run (no database changes)")
    print("=" * 80)
    print(f"\nTapware products with installation_type: {len(products)}")

    # Track changes
    changes = []
    clears = []
    unchanged = 0
    change_counts = {}

    for row in products:
        pid, sku, title, old_value = row

        new_value = standardize_installation_type(old_value)

        if new_value is None and old_value:
            # Clearing junk value
            clears.append({
                'id': pid,
                'sku': sku,
                'old': old_value,
            })
        elif new_value != old_value:
            # Standardizing value
            key = f"{old_value} → {new_value}"
            change_counts[key] = change_counts.get(key, 0) + 1
            changes.append({
                'id': pid,
                'sku': sku,
                'old': old_value,
                'new': new_value,
            })
        else:
            unchanged += 1

    # Summary
    print(f"\n--- CHANGES ---")
    print(f"Values to standardize: {len(changes)}")
    print(f"Junk values to clear: {len(clears)}")
    print(f"Already correct: {unchanged}")

    if change_counts:
        print(f"\nStandardization mappings:")
        for key, cnt in sorted(change_counts.items(), key=lambda x: -x[1]):
            print(f"  {key}: {cnt}")

    if clears:
        # Group clears by old value
        clear_counts = {}
        for c in clears:
            clear_counts[c['old']] = clear_counts.get(c['old'], 0) + 1
        print(f"\nJunk values being cleared:")
        for val, cnt in sorted(clear_counts.items(), key=lambda x: -x[1]):
            print(f"  '{val}': {cnt}")

    # Apply changes
    if not args.dry_run:
        for ch in changes:
            cursor.execute("""
                UPDATE shopify_products
                SET installation_type = ?
                WHERE id = ?
            """, (ch['new'], ch['id']))

        for cl in clears:
            cursor.execute("""
                UPDATE shopify_products
                SET installation_type = NULL
                WHERE id = ?
            """, (cl['id'],))

        conn.commit()
        print(f"\n{len(changes)} values standardized, {len(clears)} junk values cleared.")
    else:
        print(f"\n[DRY RUN] No changes made.")

    conn.close()


if __name__ == '__main__':
    main()
