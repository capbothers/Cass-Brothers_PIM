#!/usr/bin/env python3
"""
Extract enrichment data from Shopify product tags.

Many products have useful data encoded in tags like:
- colour:Chrome, colour: Matte Black
- Mounting:Hob Mounted Taps, Mounting:Wall Mounted Taps
- Type:Sink Mixers, Type:Basin Mixers
- Material:316 Stainless Steel

This script extracts these values and populates the corresponding
spec fields (colour_finish, installation_type, material) in the database.

Usage:
    python scripts/extract_enrichment_from_tags.py [--dry-run] [--collection COLLECTION]
"""

import sqlite3
import argparse
import re
from datetime import datetime


# ============================================================
# Tag extraction patterns
# ============================================================

# Colour tag patterns - normalize to standard colour_finish values
# Important: Keep "Brushed" prefix when present
COLOUR_MAPPINGS = {
    # Standard finishes - Chrome
    'chrome': 'Chrome',
    'polished chrome': 'Chrome',
    'brushed chrome': 'Brushed Chrome',

    # Nickel variants
    'brushed nickel': 'Brushed Nickel',
    'satin nickel': 'Brushed Nickel',
    'nickel': 'Nickel',

    # Black variants
    'matte black': 'Matte Black',
    'matt black': 'Matte Black',
    'black': 'Matte Black',
    'gloss black': 'Gloss Black',
    'glossy black': 'Gloss Black',

    # Gunmetal variants
    'gunmetal': 'Gunmetal',
    'gun metal': 'Gunmetal',
    'brushed gunmetal': 'Brushed Gunmetal',
    'brushed gun metal': 'Brushed Gunmetal',
    'brushed gun metal pvd': 'Brushed Gunmetal PVD',

    # Bronze variants
    'bronze': 'Bronze',
    'brushed bronze': 'Brushed Bronze',
    'brushed bronze pvd': 'Brushed Bronze PVD',

    # Gold variants
    'gold': 'Gold',
    'brushed gold': 'Brushed Gold',
    'rose gold': 'Rose Gold',
    'brushed rose gold': 'Brushed Rose Gold',

    # Brass variants
    'brass': 'Brass',
    'brushed brass': 'Brushed Brass',
    'aged brass': 'Aged Brass',
    'antique brass': 'Antique Brass',
    'satin brass': 'Satin Brass',

    # White variants
    'white': 'White',
    'matte white': 'Matte White',
    'matt white': 'Matte White',
    'gloss white': 'Gloss White',

    # Stainless Steel variants
    'stainless steel': 'Stainless Steel',
    'brushed stainless steel': 'Brushed Stainless Steel',

    # PVD finishes
    'pvd brushed nickel': 'PVD Brushed Nickel',
    'pvd matte black': 'PVD Matte Black',
    'pvd brushed bronze': 'PVD Brushed Bronze',
    'pvd brushed gold': 'PVD Brushed Gold',
    'pvd gun metal': 'PVD Gunmetal',
    'pvd gunmetal': 'PVD Gunmetal',

    # Other finishes
    'graphite': 'Graphite',
    'copper': 'Copper',
    'brushed copper': 'Brushed Copper',
    'pewter': 'Pewter',
}

# Mounting tag patterns - normalize to installation_type values
MOUNTING_MAPPINGS = {
    'hob mounted taps': 'Hob Mounted',
    'hob mounted': 'Hob Mounted',
    'deck mounted': 'Hob Mounted',
    'bench mounted': 'Hob Mounted',
    'countertop mounted': 'Hob Mounted',
    'wall mounted taps': 'Wall Mounted',
    'wall mounted': 'Wall Mounted',
    'wall mount': 'Wall Mounted',
    'floor mounted': 'Floor Mounted',
    'floor standing': 'Floor Mounted',
    'freestanding': 'Floor Mounted',
    'ceiling mounted': 'Ceiling Mounted',
    'in-wall': 'In-Wall',
    'concealed': 'In-Wall',
    'recessed': 'In-Wall',
}

# Material tag patterns
MATERIAL_MAPPINGS = {
    '316 stainless steel': '316 Stainless Steel',
    '316 marine grade stainless steel': '316 Stainless Steel',
    '304 stainless steel': '304 Stainless Steel',
    'stainless steel': 'Stainless Steel',
    'brass': 'Solid Brass',
    'solid brass': 'Solid Brass',
    'zinc alloy': 'Zinc Alloy',
    'ceramic': 'Ceramic',
    'abs': 'ABS Plastic',
    'plastic': 'Plastic',
}

# Values to skip (not actual materials)
MATERIAL_SKIP = [
    'lead free',
    'brasstaptype',
]


def extract_tag_value(tags: str, prefix: str) -> str | None:
    """Extract value from a tag with given prefix (e.g., 'colour:Chrome')."""
    if not tags:
        return None

    # Handle both "prefix:value" and "prefix: value" (with space)
    pattern = rf'{prefix}:\s*([^,]+)'
    match = re.search(pattern, tags, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


# Values that look like colours but are actually materials
COLOUR_IS_MATERIAL = [
    '316 marine grade stainless steel',
    '316 stainless steel',
    '304 stainless steel',
]


def normalize_colour(raw_value: str) -> tuple[str | None, str | None]:
    """
    Normalize colour value to standard format.
    Returns (colour, material) - material is set if the colour tag is actually a material.
    """
    if not raw_value:
        return None, None

    normalized = raw_value.lower().strip()

    # Check if this is actually a material, not a colour
    if normalized in COLOUR_IS_MATERIAL:
        material = MATERIAL_MAPPINGS.get(normalized, raw_value.title())
        return None, material

    return COLOUR_MAPPINGS.get(normalized, raw_value.title()), None


def normalize_mounting(raw_value: str) -> str | None:
    """Normalize mounting value to standard installation_type."""
    if not raw_value:
        return None

    normalized = raw_value.lower().strip()
    return MOUNTING_MAPPINGS.get(normalized)


def normalize_material(raw_value: str) -> str | None:
    """Normalize material value."""
    if not raw_value:
        return None

    normalized = raw_value.lower().strip()

    # Skip non-material values
    if any(skip in normalized for skip in MATERIAL_SKIP):
        return None

    return MATERIAL_MAPPINGS.get(normalized, raw_value.title())


def main():
    parser = argparse.ArgumentParser(description='Extract enrichment data from Shopify tags')
    parser.add_argument('--dry-run', action='store_true', help='Preview without making changes')
    parser.add_argument('--collection', type=str, help='Limit to specific super_category')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite existing values')
    args = parser.parse_args()

    conn = sqlite3.connect('supplier_products.db')
    cursor = conn.cursor()

    # Build query
    query = """
        SELECT id, sku, title, tags,
               colour_finish, installation_type, material
        FROM shopify_products
        WHERE status = 'active' AND tags IS NOT NULL AND tags != ''
    """
    params = []

    if args.collection:
        query += " AND super_category = ?"
        params.append(args.collection)

    query += " ORDER BY vendor, sku"

    cursor.execute(query, params)
    products = cursor.fetchall()

    print("=" * 80)
    print("EXTRACT ENRICHMENT FROM SHOPIFY TAGS")
    if args.dry_run:
        print("  MODE: Dry run (no database changes)")
    if args.collection:
        print(f"  COLLECTION: {args.collection}")
    if args.overwrite:
        print("  MODE: Overwriting existing values")
    print("=" * 80)
    print(f"\nProducts with tags: {len(products)}")

    # Track extractions
    colour_updates = []
    mounting_updates = []
    material_updates = []

    colour_values = {}
    mounting_values = {}
    material_values = {}

    for row in products:
        pid, sku, title, tags, existing_colour, existing_mounting, existing_material = row

        # Extract colour (may also return material if colour tag is actually a material)
        raw_colour = extract_tag_value(tags, 'colour')
        if raw_colour:
            colour, material_from_colour = normalize_colour(raw_colour)
            if colour:
                colour_values[colour] = colour_values.get(colour, 0) + 1
                if args.overwrite or not existing_colour:
                    colour_updates.append({
                        'id': pid,
                        'sku': sku,
                        'old': existing_colour,
                        'new': colour,
                    })
            # If the colour tag was actually a material, record it
            if material_from_colour:
                material_values[material_from_colour] = material_values.get(material_from_colour, 0) + 1
                if args.overwrite or not existing_material:
                    material_updates.append({
                        'id': pid,
                        'sku': sku,
                        'old': existing_material,
                        'new': material_from_colour,
                    })

        # Extract mounting/installation type
        raw_mounting = extract_tag_value(tags, 'Mounting')
        if raw_mounting:
            mounting = normalize_mounting(raw_mounting)
            if mounting:
                mounting_values[mounting] = mounting_values.get(mounting, 0) + 1
                if args.overwrite or not existing_mounting:
                    mounting_updates.append({
                        'id': pid,
                        'sku': sku,
                        'old': existing_mounting,
                        'new': mounting,
                    })

        # Extract material
        raw_material = extract_tag_value(tags, 'Material')
        if raw_material:
            material = normalize_material(raw_material)
            if material:
                material_values[material] = material_values.get(material, 0) + 1
                if args.overwrite or not existing_material:
                    material_updates.append({
                        'id': pid,
                        'sku': sku,
                        'old': existing_material,
                        'new': material,
                    })

    # Summary
    print(f"\n--- COLOUR EXTRACTION ---")
    print(f"Products with colour tags: {sum(colour_values.values())}")
    print(f"Updates to apply: {len(colour_updates)}")
    if colour_values:
        print(f"\nColour distribution (top 15):")
        for colour, cnt in sorted(colour_values.items(), key=lambda x: -x[1])[:15]:
            print(f"  {colour}: {cnt}")

    print(f"\n--- MOUNTING/INSTALLATION EXTRACTION ---")
    print(f"Products with mounting tags: {sum(mounting_values.values())}")
    print(f"Updates to apply: {len(mounting_updates)}")
    if mounting_values:
        print(f"\nMounting distribution:")
        for mounting, cnt in sorted(mounting_values.items(), key=lambda x: -x[1]):
            print(f"  {mounting}: {cnt}")

    print(f"\n--- MATERIAL EXTRACTION ---")
    print(f"Products with material tags: {sum(material_values.values())}")
    print(f"Updates to apply: {len(material_updates)}")
    if material_values:
        print(f"\nMaterial distribution:")
        for material, cnt in sorted(material_values.items(), key=lambda x: -x[1]):
            print(f"  {material}: {cnt}")

    # Show sample updates
    if colour_updates:
        print(f"\nSample colour updates (first 10):")
        for upd in colour_updates[:10]:
            old = upd['old'] or '(none)'
            print(f"  {upd['sku']}: {old} → {upd['new']}")

    # Apply updates
    if not args.dry_run:
        now = datetime.now().isoformat()

        for upd in colour_updates:
            cursor.execute("""
                UPDATE shopify_products
                SET colour_finish = ?,
                    enriched_at = COALESCE(enriched_at, ?)
                WHERE id = ?
            """, (upd['new'], now, upd['id']))

        for upd in mounting_updates:
            cursor.execute("""
                UPDATE shopify_products
                SET installation_type = ?,
                    enriched_at = COALESCE(enriched_at, ?)
                WHERE id = ?
            """, (upd['new'], now, upd['id']))

        for upd in material_updates:
            cursor.execute("""
                UPDATE shopify_products
                SET material = ?,
                    enriched_at = COALESCE(enriched_at, ?)
                WHERE id = ?
            """, (upd['new'], now, upd['id']))

        conn.commit()

        total = len(colour_updates) + len(mounting_updates) + len(material_updates)
        print(f"\n{total} updates applied:")
        print(f"  - {len(colour_updates)} colour_finish")
        print(f"  - {len(mounting_updates)} installation_type")
        print(f"  - {len(material_updates)} material")
    else:
        print(f"\n[DRY RUN] No changes made.")

    conn.close()


if __name__ == '__main__':
    main()
