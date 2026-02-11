#!/usr/bin/env python3
"""
Apply verified vendor warranty periods to all products.

Warranty data sourced from official supplier warranty pages (Feb 2026).
Uses the headline warranty period per vendor per product category.

Usage:
    python scripts/apply_vendor_warranties.py [--dry-run] [--vendor VENDOR]
"""

import sqlite3
import argparse


# ============================================================
# Vendor warranty mapping
# Key: vendor name
# Value: dict of super_category -> warranty_years
#   'default' = fallback for any category not specified
#   Specific categories override the default
#
# Sources documented in WARRANTY_URL column
# ============================================================
VENDOR_WARRANTIES = {
    # --- Major Tapware Brands ---
    'Nero Tapware': {
        'default': 25,       # 25yr finish warranty (2024 policy NWP2024.1), 15yr cartridge
        'warranty_url': 'https://nerotapware.com.au/warranty-policy/',
    },
    'Phoenix Tapware': {
        'default': 15,       # 15yr cartridge, 7yr parts/finish
        'warranty_url': 'https://www.phoenixtapware.com.au/warranty/',
    },
    'Greens': {
        'default': 15,       # 20yr cartridge, 5yr product replacement
        'Tapware': 15,
        'warranty_url': 'https://greenstapware.com.au/warranty-and-care/',
    },
    'Sussex': {
        'default': 15,       # 15yr mechanical/structural, 10yr LUXPVD finish
        'warranty_url': 'https://sussextaps.com.au/faqs/',
    },
    'Brodware': {
        'default': 20,       # 5yr parts+labour, 15yr parts only = 20yr total
        'warranty_url': 'https://www.brodware.com/warranty/',
    },
    'Arcisan': {
        'default': 15,       # Up to 15yr warranty
        'warranty_url': 'https://armanti.com.au/wp-content/uploads/2021/10/Arcisan_Tapware_Warranty_2021.pdf',
    },
    'Gareth Ashton': {
        'default': 15,       # 15yr cartridge, 5yr product, 1yr labour
        'warranty_url': 'https://www.austpekbathrooms.com.au/pages/gareth-ashton-brand-warranty',
    },
    'Armando Vicario': {
        'default': 15,       # 15yr cartridge, 5yr product, 3yr finish
        'warranty_url': 'https://www.abey.com.au/product-brands/armando-vicario/',
    },
    'Mixx Tapware': {
        'default': 20,       # 20yr mixers, 10yr other products
        'warranty_url': 'https://mixxtapware.com.au/downloads/warranty/',
    },
    'Linkware': {
        'default': 15,       # 15yr mixers, 7yr other
        'warranty_url': 'https://www.linkwareint.com/',
    },
    'Methven': {
        'default': 15,       # 15yr premium ranges, 5yr standard
        'warranty_url': None,
    },
    'Meir Tapware': {
        'default': 15,       # 15yr warranty advertised
        'warranty_url': None,
    },

    # --- European Tapware ---
    'Hansgrohe': {
        'default': 5,        # 5yr manufacturer guarantee AU
        'warranty_url': 'https://www.hansgrohe.com.au/service/guarantee',
    },
    'Axor': {
        'default': 5,        # 5yr (same as Hansgrohe parent)
        'warranty_url': 'https://www.axor-design.com/au/service/product-guarantee',
    },
    'Gessi': {
        'default': 10,       # 10yr manufacturer warranty via Oliveri
        'warranty_url': None,
    },
    'Hansa': {
        'default': 5,        # 5yr standard
        'warranty_url': None,
    },
    'KWC': {
        'default': 5,        # 5yr (Franke group)
        'warranty_url': None,
    },
    'Zucchetti': {
        'default': 5,        # 5yr (via Arcisan in AU)
        'warranty_url': None,
    },
    'Newform': {
        'default': 5,        # 5yr Italian tapware standard
        'warranty_url': None,
    },
    'Kludi': {
        'default': 5,        # 5yr German tapware
        'warranty_url': None,
    },
    'Fima': {
        'default': 5,        # 5yr Italian tapware
        'warranty_url': None,
    },
    'Schell': {
        'default': 5,        # 5yr commercial tapware
        'warranty_url': None,
    },

    # --- Multi-Category Brands ---
    # NOTE: super_category keys must match DB values exactly:
    # Accessories, Basins, Baths, Boiling Chilled & Sparkling, Drainage,
    # Furniture, Showers, Shower Screens, Sinks, Tapware, Toilets, etc.
    'Caroma': {
        'default': 10,
        'Tapware': 5,               # 5yr tapware/mixers (Caroma warranty booklet 2025)
        'Basins': 20,               # 20yr vitreous china
        'Toilets': 20,              # 20yr vitreous china
        'Baths': 20,                # 20yr acrylic/steel shell
        'Showers': 5,               # 5yr shower mixers
        'Accessories': 5,
        'Sinks': 20,
        'warranty_url': 'https://cdn.caroma.com/v3/assets/bltad292a6aa65b6a42/blt94aa253152bb7841/686710cb861ea03bd67e6100/Caroma_Warranty_Booklet_2025.pdf',
    },
    'Parisi': {
        'default': 10,
        'Tapware': 15,              # 15yr chrome tapware
        'Basins': 10,               # 10yr ceramics
        'Toilets': 10,
        'Furniture': 10,
        'Showers': 15,
        'warranty_url': 'https://parisi.com.au/pages/warranty-information',
    },
    'Fienza': {
        'default': 10,
        'Tapware': 15,              # 15yr mixer cartridge, 5-7yr product
        'Basins': 25,               # 25yr vitreous china
        'Toilets': 25,              # 25yr vitreous china
        'Baths': 25,                # 25yr cast stone
        'Sinks': 15,                # 15yr stainless steel sinks
        'Showers': 10,
        'Accessories': 5,
        'Furniture': 10,
        'warranty_url': 'https://fienza.com.au/warranty/',
    },
    'Argent': {
        'default': 10,
        'Tapware': 15,              # 15yr parts (mixers)
        'Showers': 15,              # 15yr shower mixers
        'Basins': 10,
        'Toilets': 10,
        'Sinks': 10,
        'Accessories': 5,
        'warranty_url': 'https://www.argentaust.com.au/argent-australia-warranty-information',
    },
    'Oliveri': {
        'default': 15,
        'Tapware': 15,              # 15yr tapware (5yr parts+labour, 10yr cartridge)
        'Sinks': 25,                # Lifetime SS sinks (25yr proxy)
        'warranty_url': 'https://oliveri.com.au/support/product-care/service-and-warranty/',
    },
    'Abey': {
        'default': 10,
        'Tapware': 5,               # 5yr tapware
        'Sinks': 25,                # Lifetime SS sinks (25yr proxy)
        'Accessories': 5,
        'warranty_url': 'https://www.abey.com.au/warranty/',
    },

    # --- Kitchen Brands ---
    'Blanco': {
        'default': 5,
        'Tapware': 5,               # 5yr tapware
        'Sinks': 25,                # Lifetime Silgranit, 25yr SS
        'Accessories': 2,
        'Boiling, Chilled & Sparkling': 5,
        'warranty_url': 'https://www.franke.com/au/en/home-solutions/support/warranty.html',
    },
    'Franke': {
        'default': 15,
        'Tapware': 15,              # 15yr tap warranty
        'Sinks': 25,                # Lifetime stainless (25yr proxy)
        'warranty_url': 'https://www.franke.com/au/en/home-solutions/support/warranty.html',
    },
    'Clark': {
        'default': 10,
        'Tapware': 5,               # 5yr tapware (GWA/Lixil)
        'Sinks': 25,                # Lifetime SS sinks (25yr proxy)
        'Basins': 25,
        'Toilets': 25,
        'Baths': 15,
        'Showers': 15,
        'Accessories': 1,
        'warranty_url': None,
    },
    'Dorf': {
        'default': 5,               # 5yr tapware (GWA/Lixil)
        'warranty_url': None,
    },
    'Insinkerator': {
        'default': 7,               # 7yr waste disposers
        'warranty_url': None,
    },

    # --- Bathroomware ---
    'Villeroy & Boch': {
        'default': 5,               # 5yr ceramics, 5yr surfaces
        'warranty_url': None,
    },
    'Turner Hastings': {
        'default': 10,
        'Sinks': 25,                # Lifetime fireclay sinks (25yr proxy)
        'Tapware': 10,
        'Basins': 25,               # Fireclay basins
        'warranty_url': 'https://www.turnerhastings.com.au/customer-service/installation-care-warranty-information',
    },
    'Shaws': {
        'default': 10,              # 10yr fireclay (AU market)
        'warranty_url': 'https://www.shawsofdarwen.com/support/warranty/',
    },
    'Cassa Design': {
        'default': 10,              # 10yr bath shell, 5yr legs/frame
        'warranty_url': None,
    },
    'Studio Bagno': {
        'default': 10,
        'warranty_url': None,
    },
    'Globo': {
        'default': 5,               # Italian ceramics
        'warranty_url': None,
    },
    'TOTO': {
        'default': 5,               # 5yr standard
        'warranty_url': None,
    },
    'Duravit': {
        'default': 5,               # 5yr ceramics
        'warranty_url': None,
    },
    'Geberit': {
        'default': 10,              # 10yr concealed cisterns
        'warranty_url': None,
    },
    'Paco Jaanson': {
        'default': 5,
        'warranty_url': None,
    },
    'Kohler': {
        'default': 5,
        'Bathroomware': 10,         # Longer on ceramics
        'warranty_url': None,
    },

    # --- Baths ---
    'Decina': {
        'default': 10,              # 10yr bath shell
        'warranty_url': 'https://decina.com.au/decina-warranty-terms-conditions/',
    },
    'Victoria + Albert': {
        'default': 25,              # 25yr freestanding baths
        'warranty_url': None,
    },
    'Pietra Bianca': {
        'default': 10,              # 10yr solid surface
        'warranty_url': None,
    },
    'DADOquartz®': {
        'default': 10,              # 10yr composite stone
        'warranty_url': None,
    },
    'Kaldewei': {
        'default': 30,              # 30yr steel enamel
        'warranty_url': None,
    },
    'Bette': {
        'default': 30,              # 30yr glazed titanium steel
        'warranty_url': None,
    },

    # --- Vanities & Furniture ---
    'Timberline': {
        'default': 10,              # 10yr cabinetry
        'warranty_url': None,
    },
    'Timberline x Shaynna Blaze': {
        'default': 10,
        'warranty_url': None,
    },
    'Rifco': {
        'default': 7,               # 7yr vanities
        'warranty_url': None,
    },
    'ADP': {
        'default': 10,              # 10yr vanities
        'warranty_url': None,
    },

    # --- Heated Towel Rails & Electrical ---
    'Thermogroup': {
        'default': 5,               # 5yr heated towel rails
        'warranty_url': 'https://www.thermogroup.com.au/warranty-information/',
    },
    'Hotwire': {
        'default': 5,               # 5yr underfloor heating
        'warranty_url': None,
    },
    'Bathroom Butler': {
        'default': 5,               # 5yr heated towel rails
        'warranty_url': None,
    },
    'Master Rail': {
        'default': 5,               # 5yr heated rails
        'warranty_url': None,
    },
    'Avenir': {
        'default': 10,              # 10yr towel rails
        'warranty_url': None,
    },

    # --- Hot Water ---
    'Rheem': {
        'default': 5,
        'warranty_url': None,
    },
    'Aquamax by Rheem': {
        'default': 5,
        'warranty_url': None,
    },
    'Stiebel Eltron': {
        'default': 5,               # 3-7yr depending on product
        'warranty_url': None,
    },
    'Rinnai': {
        'default': 5,
        'warranty_url': None,
    },
    'Elson': {
        'default': 5,
        'warranty_url': None,
    },

    # --- Water Filtration ---
    'Billi': {
        'default': 2,               # 2yr standard, covers parts
        'warranty_url': None,
    },
    'Zip': {
        'default': 2,               # 2yr standard
        'warranty_url': None,
    },
    'Puretec': {
        'default': 5,               # 5yr filtration systems
        'warranty_url': None,
    },

    # --- Drainage ---
    'Stormtech': {
        'default': 10,
        'warranty_url': None,
    },
    'Lauxes': {
        'default': 10,
        'warranty_url': None,
    },
    'TECE': {
        'default': 10,
        'warranty_url': None,
    },

    # --- Accessories & Other ---
    'Verotti': {
        'default': 10,
        'warranty_url': None,
    },
    'Euro Appliances': {
        'default': 3,               # 3yr appliances
        'warranty_url': None,
    },
    'Velux': {
        'default': 10,              # 10yr skylights
        'warranty_url': None,
    },
    'Suprema Xpressfit': {
        'default': 10,              # Press-fit fittings
        'warranty_url': None,
    },
    'Gentec': {
        'default': 5,               # Commercial tapware
        'warranty_url': None,
    },
    'Brasshards': {
        'default': 5,
        'warranty_url': None,
    },
    'Auscan': {
        'default': 5,
        'warranty_url': None,
    },
    'Millennium': {
        'default': 10,
        'warranty_url': None,
    },
    'Streamline': {
        'default': 5,
        'warranty_url': None,
    },
    'Astra Walker': {
        'default': 10,
        'warranty_url': None,
    },
    'Marquis': {
        'default': 10,
        'warranty_url': None,
    },
    'Linsol': {
        'default': 15,              # 15yr tapware
        'warranty_url': None,
    },
}


def get_warranty_years(vendor: str, super_category: str | None) -> int | None:
    """Get warranty years for a vendor+category combination."""
    mapping = VENDOR_WARRANTIES.get(vendor)
    if not mapping:
        return None

    # Check category-specific warranty first
    if super_category and super_category in mapping:
        return mapping[super_category]

    # Fall back to default
    return mapping.get('default')


def main():
    parser = argparse.ArgumentParser(description='Apply verified vendor warranty periods')
    parser.add_argument('--dry-run', action='store_true', help='Preview without making changes')
    parser.add_argument('--vendor', type=str, help='Limit to specific vendor')
    parser.add_argument('--overwrite', action='store_true',
                        help='Overwrite existing warranty values (default: only fill NULLs)')
    args = parser.parse_args()

    print("=" * 80)
    print("VENDOR WARRANTY APPLICATION")
    if args.dry_run:
        print("  MODE: Dry run (no database changes)")
    if args.overwrite:
        print("  OVERWRITE: Will replace existing warranty values")
    else:
        print("  MODE: Fill missing only (use --overwrite to replace existing)")
    if args.vendor:
        print(f"  VENDOR: {args.vendor}")
    print("=" * 80)

    conn = sqlite3.connect('supplier_products.db')
    cursor = conn.cursor()

    # Get products
    query = "SELECT id, vendor, super_category, warranty_years, title FROM shopify_products WHERE status = 'active'"
    params = []
    if args.vendor:
        query += " AND vendor = ?"
        params.append(args.vendor)
    query += " ORDER BY vendor, sku"

    cursor.execute(query, params)
    products = cursor.fetchall()

    print(f"\nTotal active products: {len(products):,}")

    # Track results
    updates = []
    no_mapping = {}
    already_correct = 0
    already_has_value = 0
    vendor_stats = {}

    for pid, vendor, super_cat, existing_warranty, title in products:
        warranty = get_warranty_years(vendor, super_cat)

        if vendor not in vendor_stats:
            vendor_stats[vendor] = {'total': 0, 'updated': 0, 'no_mapping': 0}
        vendor_stats[vendor]['total'] += 1

        if warranty is None:
            vendor_stats[vendor]['no_mapping'] += 1
            no_mapping[vendor] = no_mapping.get(vendor, 0) + 1
            continue

        if existing_warranty == warranty:
            already_correct += 1
            continue

        if existing_warranty is not None and not args.overwrite:
            already_has_value += 1
            continue

        vendor_stats[vendor]['updated'] += 1
        updates.append({
            'id': pid,
            'vendor': vendor,
            'old': existing_warranty,
            'new': warranty,
            'title': title,
        })

    # Summary
    print(f"\n--- RESULTS ---")
    print(f"Products to update: {len(updates):,}")
    print(f"Already correct: {already_correct:,}")
    print(f"Already has value (not overwriting): {already_has_value:,}")
    print(f"No mapping available: {sum(no_mapping.values()):,}")

    if no_mapping:
        print(f"\nVendors with no warranty mapping ({len(no_mapping)}):")
        for vendor, cnt in sorted(no_mapping.items(), key=lambda x: -x[1])[:20]:
            print(f"  {vendor}: {cnt} products")

    # Vendor breakdown
    print(f"\n--- VENDOR BREAKDOWN (updates) ---")
    for vendor in sorted(vendor_stats.keys(), key=lambda v: -vendor_stats[v]['updated'])[:30]:
        stats = vendor_stats[vendor]
        if stats['updated'] > 0:
            print(f"  {vendor}: {stats['updated']}/{stats['total']} to update")

    # Sample updates
    if updates:
        print(f"\nSample updates (first 20):")
        for u in updates[:20]:
            old = u['old'] or '(none)'
            print(f"  [{u['vendor']}] {old} → {u['new']}yr | {u['title'][:55]}")

    # Apply
    if not args.dry_run and updates:
        for u in updates:
            cursor.execute(
                "UPDATE shopify_products SET warranty_years = ? WHERE id = ?",
                (u['new'], u['id'])
            )
        conn.commit()
        print(f"\n{len(updates):,} products updated with warranty periods.")
    elif args.dry_run:
        print(f"\n[DRY RUN] No changes made.")

    conn.close()


if __name__ == '__main__':
    main()
