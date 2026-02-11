#!/usr/bin/env python3
"""
Normalize material values in shopify_products.

Fixes:
1. Title Case all material values
2. Merge duplicates (fireclay/fire clay, nanogranite variants, etc.)
3. Fix misclassified materials (ceramic disc cartridges tagged as Ceramic, colours as materials)
4. Standardize multi-material combo ordering

Usage:
    python scripts/normalize_materials.py [--dry-run]
"""

import sqlite3
import argparse


# ============================================================
# Direct material mappings: old_value → new_value
# Applied first, handles exact matches (case-insensitive)
# ============================================================
MATERIAL_MAP = {
    # --- Title Case fixes (lowercase → Title Case) ---
    'vitreous china': 'Vitreous China',
    'acrylic': 'Acrylic',
    'wood': 'Wood',
    'nanogranite': 'Nanogranite',
    'stone': 'Stone',
    'solid surface': 'Solid Surface',
    'oak': 'Oak',
    'polyurethane': 'Polyurethane',
    'silgranit': 'Silgranit',
    'fibre-rock': 'Fibre-Rock',
    'abs': 'ABS',
    'glass': 'Glass',
    'natural oak': 'Oak',
    'walnut': 'Walnut',
    'natural walnut': 'Walnut',
    'bamboo': 'Bamboo',
    'multi-wood': 'Multi-Wood',
    'marble': 'Marble',
    'concrete': 'Concrete',
    'composite': 'Composite',
    'resin stone': 'Resin Stone',
    'steel': 'Steel',
    'timber': 'Wood',
    'aluminium': 'Aluminium',

    # --- Merge duplicates ---
    'fire clay': 'Fireclay',
    'fireclay': 'Fireclay',
    'fireclay ceramic': 'Fireclay',
    'composite nanogranite': 'Nanogranite',
    'nanogranite composite': 'Nanogranite',
    'composite granite stone': 'Granite Composite',
    'composite granite': 'Granite Composite',
    'granite composite': 'Granite Composite',
    'cast stone': 'Cast Stone',
    'cast stone solid surface': 'Cast Stone',
    'abs plastic': 'ABS',
    'natural stone': 'Stone',
    'solid stone': 'Stone',
    'engineered stone': 'Engineered Stone',
    'clearstone': 'Solid Surface',
    'stonetec': 'Solid Surface',
    'quaryl': 'Quaryl',
    'fibre-rock composite': 'Fibre-Rock',
    'fibron': 'Fibron',
    'duroplast': 'Duroplast',
    'moisture-resistant mdf': 'MDF',
    'powder coated steel': 'Steel',
    'powder coated metal': 'Steel',
    'galvanised steel': 'Steel',
    'mirror glass': 'Mirror Glass',

    # --- Colours stored as material → NULL ---
    'matte black': None,
    'matte white': None,
    'gun metal grey': None,
    'gunmetal': None,

    # --- Nonsense values ---
    'co2 cylinder': None,
    'aluminium foil': 'Aluminium',
    'mirrored': 'Mirror Glass',

    # --- Multi-material combo standardization ---
    # Standardize ordering: primary material first, alphabetical for ties
    'stainless steel, brass': 'Stainless Steel, Brass',
    'brass, stainless steel': 'Stainless Steel, Brass',
    'stainless steel, ABS': 'Stainless Steel, ABS',
    'stainless steel, abs, plastic': 'Stainless Steel, ABS',
    'stainless steel, ABS, brass': 'Stainless Steel, Brass, ABS',
    'stainless steel, brass, abs': 'Stainless Steel, Brass, ABS',
    'stainless steel, brass, ABS': 'Stainless Steel, Brass, ABS',
    'brass, abs': 'Brass, ABS',
    'brass, ABS': 'Brass, ABS',
    'stainless steel, polyurethane': 'Stainless Steel, Polyurethane',
    'stainless steel, frosted glass': 'Stainless Steel, Glass',
    'stainless steel, glass': 'Stainless Steel, Glass',
    'stainless steel, zinc': 'Stainless Steel, Zinc',
    'zinc, stainless steel': 'Stainless Steel, Zinc',
    'glass, chrome': 'Glass, Chrome',
    'glass, metal': 'Glass, Metal',
    'glass, brass': 'Glass, Brass',
    'glass, enamel': 'Glass, Enamel',
    'brass, glass': 'Glass, Brass',
    'brass, ceramic': 'Ceramic, Brass',
    'ceramic, brass': 'Ceramic, Brass',
    'ceramic, chrome': 'Ceramic, Chrome',
    'ceramic, porcelain': 'Vitreous China',
    'ceramic, porcelain, wood': 'Vitreous China, Wood',
    'chrome, brass': 'Brass, Chrome',
    'mirror, brass': 'Mirror Glass, Brass',
    'marble, wood': 'Marble, Wood',
    'wood, stone': 'Stone, Wood',
    'metal, plastic': 'Metal, Plastic',
    'fibre rock, bamboo': 'Fibre-Rock, Bamboo',

    # --- Furniture multi-material combos (Title Case) ---
    'porcelain, wood': 'Porcelain, Wood',
    'porcelain, multi-wood': 'Porcelain, Multi-Wood',
    'porcelain, wood veneer': 'Porcelain, Wood Veneer',
    'porcelain, walnut veneer': 'Porcelain, Walnut Veneer',
    'porcelain, natural veneer': 'Porcelain, Wood Veneer',
    'porcelain, wood, polyurethane': 'Porcelain, Wood',
    'porcelain, veneer, metal': 'Porcelain, Wood Veneer, Metal',
    'porcelain, stainless steel, oak': 'Porcelain, Stainless Steel, Oak',
    'porcelain, steel, oak': 'Porcelain, Stainless Steel, Oak',
    'multi-wood, polyurethane paint': 'Multi-Wood',
    'multi-wood with polyurethane paint': 'Multi-Wood',
    'multi-wood, ceramic': 'Multi-Wood, Ceramic',
    'oak, metal': 'Oak, Metal',
    'natural veneer, black metal': 'Wood Veneer, Metal',
    'natural veneer, black frame': 'Wood Veneer, Metal',
    'veneer, ceramic': 'Wood Veneer, Ceramic',
    'vitrified ceramic, mdf, e0 board': 'Vitreous China, MDF',
}


# ============================================================
# Category-specific overrides: fix misclassified materials
# (super_category, old_material) → new_material
# ============================================================
CATEGORY_OVERRIDES = {
    # Tapware: Ceramic/Porcelain = ceramic disc cartridges, body is brass
    ('Tapware', 'Ceramic'): 'Solid Brass',
    ('Tapware', 'Porcelain'): 'Solid Brass',
    ('Tapware', 'ceramic'): 'Solid Brass',
    ('Tapware', 'porcelain'): 'Solid Brass',

    # Showers: same issue with ceramic disc internals
    ('Showers', 'Ceramic'): 'Solid Brass',
    ('Showers', 'ceramic'): 'Solid Brass',

    # Basins: Ceramic/Porcelain → Vitreous China (industry standard term)
    ('Basins', 'Ceramic'): 'Vitreous China',
    ('Basins', 'Porcelain'): 'Vitreous China',
    ('Basins', 'ceramic'): 'Vitreous China',
    ('Basins', 'porcelain'): 'Vitreous China',

    # Toilets: Ceramic/Porcelain → Vitreous China
    ('Toilets', 'Ceramic'): 'Vitreous China',
    ('Toilets', 'Porcelain'): 'Vitreous China',
    ('Toilets', 'ceramic'): 'Vitreous China',
    ('Toilets', 'porcelain'): 'Vitreous China',
}


# ============================================================
# SKU-specific overrides for individual misclassified products
# ============================================================
SKU_OVERRIDES = {
    # Argent flush plate - plastic, not ceramic
    '922415RW': 'Plastic',
    '92241595': 'Plastic',
    # Billi taps incorrectly tagged Ceramic (white colour confused LLM)
    '913000RMW': 'Stainless Steel',
    '992800MW': 'Stainless Steel',
    # Cassa Design bath - acrylic, not ceramic
    'BT-AS1700RHMW': 'Acrylic',
}


def normalize_material(material: str, super_category: str, sku: str) -> str | None:
    """
    Normalize a material value.

    Returns the normalized value, or None to set NULL.
    Returns the original if no mapping found (shouldn't happen for known values).
    """
    if not material or material == 'None':
        return None

    # 1. SKU-specific overrides (highest priority)
    if sku in SKU_OVERRIDES:
        return SKU_OVERRIDES[sku]

    # 2. Category-specific overrides
    key = (super_category, material)
    if key in CATEGORY_OVERRIDES:
        return CATEGORY_OVERRIDES[key]

    # 3. Direct mapping (case-insensitive lookup)
    material_lower = material.lower().strip()
    for old_val, new_val in MATERIAL_MAP.items():
        if old_val.lower() == material_lower:
            return new_val

    # 4. If already Title Case and no mapping needed, return as-is
    return material


def main():
    parser = argparse.ArgumentParser(description='Normalize material values')
    parser.add_argument('--dry-run', action='store_true', help='Preview without making changes')
    args = parser.parse_args()

    print("=" * 80)
    print("MATERIAL NORMALIZATION")
    if args.dry_run:
        print("  MODE: Dry run (no database changes)")
    print("=" * 80)

    conn = sqlite3.connect('supplier_products.db')
    cursor = conn.cursor()

    # Get all products with material values
    cursor.execute("""
        SELECT id, sku, title, vendor, super_category, material
        FROM shopify_products
        WHERE status = 'active'
        AND material IS NOT NULL AND material != '' AND material != 'None'
        ORDER BY super_category, vendor, sku
    """)
    products = cursor.fetchall()

    print(f"\nProducts with material values: {len(products):,}")

    changes = []
    nulled = []
    unchanged = 0

    for row in products:
        pid, sku, title, vendor, super_cat, old_material = row
        new_material = normalize_material(old_material, super_cat, sku)

        if new_material is None and old_material is not None:
            nulled.append({
                'id': pid, 'sku': sku, 'title': title, 'vendor': vendor,
                'super_category': super_cat, 'old': old_material, 'new': '(NULL)',
            })
        elif new_material != old_material:
            changes.append({
                'id': pid, 'sku': sku, 'title': title, 'vendor': vendor,
                'super_category': super_cat, 'old': old_material, 'new': new_material,
            })
        else:
            unchanged += 1

    # Summary
    print(f"\n--- RESULTS ---")
    print(f"Unchanged: {unchanged}")
    print(f"Normalized: {len(changes)}")
    print(f"Set to NULL: {len(nulled)}")

    # Show changes grouped by transformation
    if changes:
        transform_counts = {}
        for c in changes:
            key = f"{c['old']} → {c['new']}"
            transform_counts[key] = transform_counts.get(key, 0) + 1

        print(f"\n--- TRANSFORMATIONS ---")
        for transform, count in sorted(transform_counts.items(), key=lambda x: -x[1]):
            print(f"  {transform} ({count})")

    if nulled:
        print(f"\n--- SET TO NULL ---")
        for n in nulled:
            print(f"  [{n['vendor']}] {n['sku']}: \"{n['old']}\" → NULL | {n['title'][:60]}")

    # Show sample changes
    if changes:
        print(f"\n--- SAMPLE CHANGES (first 20) ---")
        for c in changes[:20]:
            print(f"  [{c['vendor']}] \"{c['old']}\" → \"{c['new']}\" | {c['title'][:50]}")

    # Apply
    if not args.dry_run and (changes or nulled):
        for c in changes:
            cursor.execute("UPDATE shopify_products SET material = ? WHERE id = ?",
                           (c['new'], c['id']))
        for n in nulled:
            cursor.execute("UPDATE shopify_products SET material = NULL WHERE id = ?",
                           (n['id'],))

        conn.commit()
        print(f"\n{len(changes) + len(nulled)} products updated.")
    elif args.dry_run:
        print(f"\n[DRY RUN] No changes made.")

    conn.close()


if __name__ == '__main__':
    main()
