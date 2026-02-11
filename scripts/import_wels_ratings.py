#!/usr/bin/env python3
"""
Import WELS (Water Efficiency Labelling and Standards) ratings from government register.

Matches products by SKU against WELS model codes and variant codes, then imports
star ratings and water consumption values.

Supports: Tapware (Tap Equipment), Showers, Toilets (Lavatory Equipment)

Usage:
    python scripts/import_wels_ratings.py [--dry-run] [--vendor VENDOR] [--category CATEGORY]
"""

import sqlite3
import argparse
import csv
import re
from datetime import datetime


# ============================================================
# Mapping: our super_category → WELS product type(s)
# ============================================================
CATEGORY_TO_WELS_TYPE = {
    'Tapware': ['Tap Equipment'],
    'Showers': ['Showers'],
    'Toilets': ['Lavatory Equipment'],
}

# ============================================================
# Brand mapping: Our vendor names → WELS brand names
# ============================================================
VENDOR_TO_WELS_BRAND = {
    'Nero Tapware': 'NERO',
    'Phoenix Tapware': 'PHOENIX',
    'Parisi': 'PARISI BATHROOMWARE',
    'Caroma': 'CAROMA',
    'Greens': 'GREENS',
    'Brodware': 'BRODWARE',
    'Hansgrohe': 'HANSGROHE',
    'Abey': 'ABEY',
    'Argent': 'ARGENT',
    'Clark': 'DORF CLARK IND',
    'Dorf': 'DORF',
    'Gentec': 'GENTEC',
    'Methven': 'METHVEN',
    'Linkware': 'LINKWARE',
    'Oliveri': 'OLIVERI',
    'Fienza': 'FIENZA',
    'Sussex': 'SUSSEX',
    'Kohler': 'KOHLER',
    'Blanco': 'BLANCO',
    'Franke': 'FRANKE',
    'KWC': 'KWC',
    'Hansa': 'HANSA',
    'Zucchetti': 'ZUCCHETTI',
    # Shower-specific vendors
    'Verotti': 'VEROTTI',
    'Auscan': 'AUSCAN',
    'Rainware': 'RAINWARE',
    'Armando Vicario': '?"?"',  # Not in WELS, matched by SKU
    'Mixx Tapware': '?"?"',
    'Gareth Ashton': '?"?"',
    'Axor': 'AXOR',
    'Flexispray': 'FLEXISPRAY',
    # Toilet-specific vendors
    'Villeroy & Boch': 'VILLEROY & BOCH',
    'TOTO': 'TOTO',
    'Arcisan': 'ARCISAN',
    'Haron': 'HARON',
    'Turner Hastings': 'TURNER HASTINGS',
    'Studio Bagno': '?"?"',
    'Globo': 'GLOBO',
    'Geberit': 'GEBERIT',
    'TECE': 'TECE',
    'Duravit': 'DURAVIT',
    'Decina': '?"?"',
}


def parse_star_rating(star_rating_str: str) -> int | None:
    """
    Parse star rating from WELS format.

    Handles:
    - Simple integers: "4" → 4
    - Shower format: "3 (> 7.5 but <= 9.0)" → 3
    - Bonus format: "3 (> 4.5 but <= 6.0 plus bonus..." → 3
    - "Not Star Rated" → None
    """
    if not star_rating_str or star_rating_str == 'Not Star Rated':
        return None

    # Extract leading integer
    match = re.match(r'^(\d+)', star_rating_str)
    if match:
        return int(match.group(1))
    return None


def load_wels_data(csv_path: str, product_types: list[str] | None = None) -> dict:
    """
    Load WELS register CSV and build lookup dictionaries.

    Args:
        csv_path: Path to WELS register CSV
        product_types: List of WELS product types to load (e.g. ['Tap Equipment', 'Showers'])
                      If None, loads all types.

    Returns dict with:
    - by_model: {model_code: {star_rating, water_consumption, brand, product_type}}
    - by_variant: {variant_code: {star_rating, water_consumption, brand, product_type}}
    """
    by_model = {}
    by_variant = {}

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        header = next(reader)  # Skip header

        for row in reader:
            if len(row) < 14:
                continue

            # Column indices (0-based)
            brand = row[2].strip().upper()  # Column 3: Brand
            product_type = row[3].strip()    # Column 4: Product type
            model_code = row[5].strip()      # Column 6: Model code
            variant_codes = row[6].strip()   # Column 7: Variant model codes
            star_rating_str = row[11].strip()  # Column 12: Star rating
            water_consumption_str = row[12].strip()  # Column 13: Water consumption

            # Filter by product type
            if product_types and product_type not in product_types:
                continue

            # Parse star rating (handles extended format for Showers)
            star_rating = parse_star_rating(star_rating_str)
            if star_rating is None:
                continue

            # Parse water consumption
            try:
                water_consumption = float(water_consumption_str)
            except (ValueError, TypeError):
                water_consumption = None

            record = {
                'star_rating': star_rating,
                'water_consumption': water_consumption,
                'brand': brand,
                'product_type': product_type,
            }

            # Index by model code
            if model_code:
                # Normalize: uppercase, remove spaces
                key = model_code.upper().replace(' ', '')
                by_model[key] = record

            # Index by variant codes (can be comma-separated)
            if variant_codes:
                # Split by comma and index each variant
                for variant in variant_codes.split(','):
                    variant = variant.strip()
                    if variant and not variant.startswith('Colour') and not variant.startswith('Handle'):
                        # Normalize
                        key = variant.upper().replace(' ', '')
                        by_variant[key] = record

    return {'by_model': by_model, 'by_variant': by_variant}


# Color suffix patterns - these are stripped to find base model
# WELS registers one model per product, ratings apply to all color variants
COLOR_SUFFIXES = [
    '.BB',   # Brushed Brass
    '.BN',   # Brushed Nickel
    '.GM',   # Gun Metal
    '.MB',   # Matte Black
    '.RG',   # Rose Gold
    '.RG1',  # Brushed Rose Gold
    '.SN',   # Satin Nickel
    '.W',    # White
    '.CP',   # Chrome Plated
    '-B',    # Black
    '-MB',   # Matte Black
    '-BB',   # Brushed Brass
    '-BN',   # Brushed Nickel
    '-GM',   # Gunmetal
    '-RG',   # Rose Gold
    '-SN',   # Satin Nickel
    '-CH',   # Chrome
    '-MBK',  # Matte Black
    '/BB',   # Brushed Brass
    '/BN',   # Brushed Nickel
    '/GM',   # Gunmetal
    '/MB',   # Matte Black
]


def strip_color_suffix(sku: str) -> str:
    """Strip color suffix from SKU to get base model."""
    sku_upper = sku.upper()
    for suffix in COLOR_SUFFIXES:
        if sku_upper.endswith(suffix.upper()):
            return sku[:-len(suffix)]
    return sku


def phoenix_color_to_xx(sku: str) -> str | None:
    """
    Convert Phoenix color-coded SKU to XX pattern used in WELS.
    Phoenix uses: 151-7815-12-1 (color code 12) → 151-7815-XX-1 (WELS pattern)
    Color codes: 00=Chrome, 10=Matte Black, 12=Brushed Gold, 40=Brushed Nickel, etc.
    """
    # Pattern: digits-digits-digits-digits (e.g., 151-7815-12-1)
    match = re.match(r'^(\d+-\d+-)\d{2}(-\d+)$', sku)
    if match:
        return f"{match.group(1)}XX{match.group(2)}"

    # Pattern: letters+digits-XX-digits (e.g., VS2814-10-1 → VS2814-XX-1)
    match = re.match(r'^([A-Z]+\d+-)\d{2}(-\d+)$', sku)
    if match:
        return f"{match.group(1)}XX{match.group(2)}"

    return None


def strip_phoenix_color_code(sku: str) -> list[str]:
    """
    Strip Phoenix color codes to get base model.
    Returns multiple possible base codes.

    Formats:
    - VS7901-10 → VS7901
    - V786 CHR → V786
    - VS067 MB → VS067
    - 113-7110-00 → 113-7110
    - 151-7700-12 → 151-7700
    """
    bases = []
    sku_upper = sku.upper()

    # Pattern: XXNNNN-CC (e.g., VS7901-10 → VS7901)
    match = re.match(r'^([A-Z]+\d+)-\d{2}$', sku_upper)
    if match:
        bases.append(match.group(1))

    # Pattern: XXNNNN SPACE COLOR (e.g., V786 CHR → V786)
    match = re.match(r'^([A-Z]+\d+)\s+(CHR|MB|BN|BB|GM|RG|SN|W)$', sku_upper)
    if match:
        bases.append(match.group(1))

    # Pattern: NNN-NNNN-CC (e.g., 113-7110-00 → 113-7110)
    match = re.match(r'^(\d+-\d+)-\d{2}$', sku_upper)
    if match:
        bases.append(match.group(1))

    return bases


def match_sku_to_wels(sku: str, vendor: str, wels_data: dict) -> dict | None:
    """
    Try to match a product SKU to WELS data.

    Matching strategy:
    1. Direct match against model codes
    2. Direct match against variant codes
    3. SKU with suffix variations (e.g., 99583C5A vs 99583C5AF)
    4. Strip color suffixes (e.g., AX01310.BB → AX01310)
    """
    if not sku:
        return None

    # Normalize SKU
    sku_upper = sku.upper().replace(' ', '')

    # Try direct model code match
    if sku_upper in wels_data['by_model']:
        return wels_data['by_model'][sku_upper]

    # Try direct variant code match
    if sku_upper in wels_data['by_variant']:
        return wels_data['by_variant'][sku_upper]

    # Try without trailing 'F' (Lead Free suffix)
    if sku_upper.endswith('F'):
        sku_no_f = sku_upper[:-1]
        if sku_no_f in wels_data['by_model']:
            return wels_data['by_model'][sku_no_f]
        if sku_no_f in wels_data['by_variant']:
            return wels_data['by_variant'][sku_no_f]

    # Try adding 'F' suffix
    sku_with_f = sku_upper + 'F'
    if sku_with_f in wels_data['by_model']:
        return wels_data['by_model'][sku_with_f]
    if sku_with_f in wels_data['by_variant']:
        return wels_data['by_variant'][sku_with_f]

    # Try without trailing 'A' (variant suffix)
    if sku_upper.endswith('A'):
        sku_no_a = sku_upper[:-1]
        if sku_no_a in wels_data['by_model']:
            return wels_data['by_model'][sku_no_a]
        if sku_no_a in wels_data['by_variant']:
            return wels_data['by_variant'][sku_no_a]

    # Try adding 'A' suffix
    sku_with_a = sku_upper + 'A'
    if sku_with_a in wels_data['by_model']:
        return wels_data['by_model'][sku_with_a]
    if sku_with_a in wels_data['by_variant']:
        return wels_data['by_variant'][sku_with_a]

    # Try stripping color suffix (ratings apply to all color variants)
    base_sku = strip_color_suffix(sku_upper)
    if base_sku != sku_upper:
        # Recurse with base SKU
        return match_sku_to_wels(base_sku, vendor, wels_data)

    # Try Phoenix XX pattern (e.g., 151-7815-12-1 → 151-7815-XX-1)
    xx_pattern = phoenix_color_to_xx(sku_upper)
    if xx_pattern:
        if xx_pattern in wels_data['by_model']:
            return wels_data['by_model'][xx_pattern]
        if xx_pattern in wels_data['by_variant']:
            return wels_data['by_variant'][xx_pattern]

    # Try Phoenix color code stripping (e.g., VS7901-10 → VS7901)
    phoenix_bases = strip_phoenix_color_code(sku_upper)
    for base in phoenix_bases:
        if base in wels_data['by_model']:
            return wels_data['by_model'][base]
        if base in wels_data['by_variant']:
            return wels_data['by_variant'][base]

    # Try Brodware format: drop last segment (e.g., 1.6700.00.2.01 → 1.6700.00.2)
    if re.match(r'^\d+\.\d+\.\d+\.\d+\.\d+$', sku_upper):
        base = '.'.join(sku_upper.split('.')[:-1])
        if base in wels_data['by_model']:
            return wels_data['by_model'][base]
        if base in wels_data['by_variant']:
            return wels_data['by_variant'][base]

    # Try compound SKU: "PAN_SKU + SEAT_SKU" → try PAN_SKU only
    # Common in toilet suites where WELS rates the pan/cistern
    if '+' in sku_upper:
        first_part = sku_upper.split('+')[0].strip()
        if first_part:
            return match_sku_to_wels(first_part, vendor, wels_data)

    return None


def process_category(cursor, category: str, wels_data: dict, vendor_filter: str | None) -> dict:
    """
    Process a single super_category against WELS data.

    Returns dict with matches, no_match, already_has_rating, vendor_stats, rating_distribution.
    """
    query = """
        SELECT id, sku, title, vendor, wels_rating, flow_rate_lpm
        FROM shopify_products
        WHERE status = 'active' AND super_category = ?
    """
    params = [category]

    if vendor_filter:
        query += " AND vendor = ?"
        params.append(vendor_filter)

    query += " ORDER BY vendor, sku"

    cursor.execute(query, params)
    products = cursor.fetchall()

    matches = []
    no_match = []
    already_has_rating = 0
    vendor_stats = {}
    rating_distribution = {}

    for row in products:
        pid, sku, title, vendor, existing_rating, flow_rate = row

        if vendor not in vendor_stats:
            vendor_stats[vendor] = {'total': 0, 'matched': 0}
        vendor_stats[vendor]['total'] += 1

        wels_match = match_sku_to_wels(sku, vendor, wels_data)

        if wels_match:
            vendor_stats[vendor]['matched'] += 1
            star_rating = wels_match['star_rating']
            water_consumption = wels_match['water_consumption']

            rating_distribution[star_rating] = rating_distribution.get(star_rating, 0) + 1

            if existing_rating and existing_rating == star_rating:
                already_has_rating += 1
            else:
                matches.append({
                    'id': pid,
                    'sku': sku,
                    'title': title,
                    'vendor': vendor,
                    'old_rating': existing_rating,
                    'new_rating': star_rating,
                    'water_consumption': water_consumption,
                    'flow_rate_db': flow_rate,
                })
        else:
            no_match.append({
                'sku': sku,
                'title': title,
                'vendor': vendor,
            })

    return {
        'total': len(products),
        'matches': matches,
        'no_match': no_match,
        'already_has_rating': already_has_rating,
        'vendor_stats': vendor_stats,
        'rating_distribution': rating_distribution,
    }


def main():
    parser = argparse.ArgumentParser(description='Import WELS ratings from government register')
    parser.add_argument('--dry-run', action='store_true', help='Preview without making changes')
    parser.add_argument('--vendor', type=str, help='Limit to specific vendor')
    parser.add_argument('--category', type=str, choices=['Tapware', 'Showers', 'Toilets', 'all'],
                        default='all', help='Category to process (default: all)')
    parser.add_argument('--wels-file', type=str, default='Wels/Publicregister-AllModels.csv',
                        help='Path to WELS CSV file')
    args = parser.parse_args()

    # Determine which categories to process
    if args.category == 'all':
        categories = ['Tapware', 'Showers', 'Toilets']
    else:
        categories = [args.category]

    print("=" * 80)
    print("WELS RATING IMPORT")
    if args.dry_run:
        print("  MODE: Dry run (no database changes)")
    if args.vendor:
        print(f"  VENDOR: {args.vendor}")
    print(f"  CATEGORIES: {', '.join(categories)}")
    print("=" * 80)

    # Determine which WELS product types to load
    wels_types = []
    for cat in categories:
        wels_types.extend(CATEGORY_TO_WELS_TYPE.get(cat, []))

    # Load WELS data
    print(f"\nLoading WELS data from {args.wels_file}...")
    print(f"  Product types: {', '.join(wels_types)}")
    wels_data = load_wels_data(args.wels_file, wels_types)
    print(f"  Model codes indexed: {len(wels_data['by_model']):,}")
    print(f"  Variant codes indexed: {len(wels_data['by_variant']):,}")

    # Connect to database
    conn = sqlite3.connect('supplier_products.db')
    cursor = conn.cursor()

    total_updated = 0

    for category in categories:
        print(f"\n{'=' * 60}")
        print(f"  {category.upper()}")
        print(f"{'=' * 60}")

        result = process_category(cursor, category, wels_data, args.vendor)
        matches = result['matches']
        no_match = result['no_match']
        already = result['already_has_rating']
        vendor_stats = result['vendor_stats']
        rating_dist = result['rating_distribution']

        print(f"\n{category} products to process: {result['total']:,}")

        # Summary
        print(f"\n--- MATCHING RESULTS ---")
        print(f"Products matched: {len(matches) + already}")
        print(f"  - New/updated ratings: {len(matches)}")
        print(f"  - Already correct: {already}")
        print(f"Products not matched: {len(no_match)}")

        if rating_dist:
            print(f"\nWELS rating distribution:")
            for rating in sorted(rating_dist.keys(), reverse=True):
                print(f"  {rating}-star: {rating_dist[rating]}")

        # Vendor breakdown
        print(f"\n--- VENDOR BREAKDOWN ---")
        for vendor in sorted(vendor_stats.keys(), key=lambda v: -vendor_stats[v]['total'])[:20]:
            stats = vendor_stats[vendor]
            pct = stats['matched'] / stats['total'] * 100 if stats['total'] > 0 else 0
            print(f"  {vendor}: {stats['matched']}/{stats['total']} ({pct:.0f}%)")

        # Sample matches
        if matches:
            print(f"\nSample updates (first 15):")
            for m in matches[:15]:
                old = m['old_rating'] or '(none)'
                print(f"  {m['sku']}: {old} → {m['new_rating']}-star | {m['title'][:50]}")

        # Sample non-matches
        if no_match:
            print(f"\nSample non-matches (first 10):")
            for nm in no_match[:10]:
                print(f"  [{nm['vendor']}] {nm['sku']}: {nm['title'][:50]}")

        # Apply updates
        if not args.dry_run and matches:
            now = datetime.now().isoformat()
            for m in matches:
                cursor.execute("""
                    UPDATE shopify_products
                    SET wels_rating = ?,
                        enriched_at = COALESCE(enriched_at, ?)
                    WHERE id = ?
                """, (m['new_rating'], now, m['id']))
            total_updated += len(matches)

    if not args.dry_run and total_updated > 0:
        conn.commit()
        print(f"\n{'=' * 60}")
        print(f"TOTAL: {total_updated} products updated with WELS ratings.")
    elif args.dry_run:
        print(f"\n[DRY RUN] No changes made.")

    conn.close()


if __name__ == '__main__':
    main()
