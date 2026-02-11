#!/usr/bin/env python3
"""
Populate warranty_years by vendor + primary_category.
This fills in gaps where brands have different warranty periods for different product types.
Only updates products that don't already have warranty_years set.
"""

import sqlite3
import sys

DB_PATH = "supplier_products.db"

# (vendor, primary_category) → warranty_years
# Based on researched warranty schedules from each brand's website/PDF
CATEGORY_WARRANTY_MAP = {
    # === CAROMA ===
    # Ceramics (toilets, basins) ~lifetime/25yr, tapware 15yr, accessories varies
    ("Caroma", "Toilets"): 25,
    ("Caroma", "Basins"): 25,
    ("Caroma", "Baths"): 15,
    ("Caroma", "Basin Tapware"): 15,
    ("Caroma", "Bath Tapware"): 15,
    ("Caroma", "Kitchen Tapware"): 15,
    ("Caroma", "Shower Tapware"): 15,
    ("Caroma", "Showers"): 15,
    ("Caroma", "Bathroom Accessories"): 5,
    ("Caroma", "Kitchen Accessories"): 5,
    ("Caroma", "Kitchen Sinks"): 25,
    ("Caroma", "Laundry Sinks"): 25,

    # === PARISI ===
    # Ceramics/basins longer, tapware 15yr, vanities 5yr, accessories 2yr
    ("Parisi", "Toilets"): 15,
    ("Parisi", "Basins"): 15,
    ("Parisi", "Baths"): 10,
    ("Parisi", "Basin Tapware"): 15,
    ("Parisi", "Bath Tapware"): 15,
    ("Parisi", "Kitchen Tapware"): 15,
    ("Parisi", "Shower Tapware"): 15,
    ("Parisi", "Showers"): 10,
    ("Parisi", "Vanities"): 5,
    ("Parisi", "Bathroom Accessories"): 2,
    ("Parisi", "Kitchen Accessories"): 2,
    ("Parisi", "Kitchen Sinks"): 15,

    # === THERMOGROUP ===
    # Heated towel rails (most products) 7-10yr, mirrors 2-3yr
    ("Thermogroup", "Bathroom Accessories"): 10,  # Heated towel rails (stainless 10yr, plated 7yr)
    ("Thermogroup", "Vanities"): 5,
    ("Thermogroup", "Mirrors & Cabinets"): 3,
    ("Thermogroup", "Basins"): 5,

    # === FIENZA ===
    # Tapware 15yr (cartridge), baths 25yr cast stone, vanities 10yr, accessories 5yr
    ("Fienza", "Basin Tapware"): 15,
    ("Fienza", "Bath Tapware"): 15,
    ("Fienza", "Kitchen Tapware"): 15,
    ("Fienza", "Shower Tapware"): 15,
    ("Fienza", "Showers"): 10,
    ("Fienza", "Baths"): 25,
    ("Fienza", "Basins"): 10,
    ("Fienza", "Toilets"): 10,
    ("Fienza", "Vanities"): 10,
    ("Fienza", "Bathroom Accessories"): 5,

    # === ARGENT ===
    # Ceramics 10yr, tapware 2yr, flush valves 2yr
    ("Argent", "Toilets"): 10,
    ("Argent", "Basins"): 10,
    ("Argent", "Baths"): 10,
    ("Argent", "Basin Tapware"): 2,
    ("Argent", "Bath Tapware"): 2,
    ("Argent", "Kitchen Tapware"): 2,
    ("Argent", "Shower Tapware"): 2,
    ("Argent", "Showers"): 2,
    ("Argent", "Bathroom Accessories"): 2,
    ("Argent", "Kitchen Sinks"): 10,
    ("Argent", "Laundry Sinks"): 10,

    # === CASSA DESIGN ===
    # Baths 10yr shell/25yr stone, vanities 5yr, basins 5yr
    ("Cassa Design", "Baths"): 10,
    ("Cassa Design", "Vanities"): 5,
    ("Cassa Design", "Basins"): 5,

    # === TURNER HASTINGS ===
    # Lifetime on fireclay sinks, TitanCast baths/basins, toilets. Tapware 7yr
    ("Turner Hastings", "Kitchen Sinks"): 99,  # Lifetime
    ("Turner Hastings", "Baths"): 99,  # Lifetime (TitanCast)
    ("Turner Hastings", "Basins"): 99,  # Lifetime
    ("Turner Hastings", "Toilets"): 99,  # Lifetime
    ("Turner Hastings", "Vanities"): 10,
    ("Turner Hastings", "Basin Tapware"): 7,
    ("Turner Hastings", "Kitchen Tapware"): 7,
    ("Turner Hastings", "Filtered Water Taps"): 7,
    ("Turner Hastings", "Bathroom Accessories"): 5,

    # === ABEY ===
    # Stainless sinks 25yr, tapware varies (Gareth Ashton/AV 15yr cartridge)
    ("Abey", "Kitchen Sinks"): 25,
    ("Abey", "Laundry Sinks"): 25,
    ("Abey", "Kitchen Tapware"): 15,
    ("Abey", "Basin Tapware"): 15,
    ("Abey", "Basins"): 10,
    ("Abey", "Bathroom Accessories"): 5,
    ("Abey", "Kitchen Accessories"): 5,

    # === GLOBO (via Bathe) ===
    # Ceramics 10yr generally
    ("Globo", "Basins"): 10,
    ("Globo", "Toilets"): 10,

    # === BLANCO ===
    # Sinks lifetime domestic, tapware 5yr
    ("Blanco", "Kitchen Sinks"): 99,  # Lifetime domestic
    ("Blanco", "Laundry Sinks"): 99,
    ("Blanco", "Kitchen Tapware"): 5,
    ("Blanco", "Basin Tapware"): 5,
    ("Blanco", "Filtered Water Taps"): 5,
    ("Blanco", "Kitchen Accessories"): 2,

    # === BATHROOM BUTLER ===
    # Heated towel rails typically 5yr
    ("Bathroom Butler", "Bathroom Accessories"): 5,

    # === CLARK ===
    # Sinks lifetime, tapware 15yr, toilets 25yr, accessories 1yr
    ("Clark", "Kitchen Sinks"): 99,  # Lifetime
    ("Clark", "Laundry Sinks"): 99,  # Lifetime
    ("Clark", "Basins"): 25,
    ("Clark", "Toilets"): 25,
    ("Clark", "Baths"): 15,
    ("Clark", "Basin Tapware"): 15,
    ("Clark", "Bath Tapware"): 15,
    ("Clark", "Kitchen Tapware"): 15,
    ("Clark", "Shower Tapware"): 15,
    ("Clark", "Showers"): 15,
    ("Clark", "Vanities"): 10,
    ("Clark", "Shower Screens"): 10,
    ("Clark", "Bathroom Accessories"): 1,
    ("Clark", "Kitchen Accessories"): 1,

    # === VEROTTI ===
    # Shower screens 25yr (chrome fittings), toilets 10yr
    ("Verotti", "Shower Screens"): 25,
    ("Verotti", "Toilets"): 10,

    # === SHAWS ===
    # Fireclay sinks lifetime, tapware varies
    ("Shaws", "Kitchen Sinks"): 99,  # Lifetime fireclay
    ("Shaws", "Kitchen Tapware"): 5,
    ("Shaws", "Kitchen Accessories"): 1,
    ("Shaws", "Bathroom Accessories"): 1,

    # === GESSI ===
    # Generally 2yr parts
    ("Gessi", "Kitchen Tapware"): 2,

    # === RINNAI ===
    # Hot water 5-12yr, heaters 5yr, accessories 1yr
    ("Rinnai", "Hot Water Systems"): 10,
    ("Rinnai", "Bathroom Accessories"): 3,  # Heaters
    ("Rinnai", "Kitchen Accessories"): 3,
    ("Rinnai", "Hot Water Accessories"): 1,

    # === TOTO ===
    # Toilets generally 5yr ceramics, baths 5yr
    ("TOTO", "Toilets"): 5,
    ("TOTO", "Baths"): 5,
    ("TOTO", "Bathroom Accessories"): 2,

    # === INSINKERATOR ===
    # Waste disposers 3-8yr, taps 2yr
    ("Insinkerator", "Kitchen Sinks"): 7,  # Waste disposers (avg)
    ("Insinkerator", "Boiling Water Taps"): 2,
    ("Insinkerator", "Filtered Water Taps"): 2,
    ("Insinkerator", "Kitchen Accessories"): 2,
    ("Insinkerator", "Bathroom Accessories"): 2,
}


def main():
    dry_run = "--dry-run" in sys.argv

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    total_updated = 0

    for (vendor, category), years in CATEGORY_WARRANTY_MAP.items():
        cursor.execute(
            """SELECT COUNT(*) FROM shopify_products
               WHERE vendor = ? AND primary_category = ? AND status = 'active'
               AND (warranty_years IS NULL OR warranty_years = 0)""",
            (vendor, category)
        )
        count = cursor.fetchone()[0]

        if count == 0:
            continue

        if not dry_run:
            cursor.execute(
                """UPDATE shopify_products SET warranty_years = ?
                   WHERE vendor = ? AND primary_category = ? AND status = 'active'
                   AND (warranty_years IS NULL OR warranty_years = 0)""",
                (years, vendor, category)
            )

        total_updated += count
        prefix = "[DRY RUN] " if dry_run else ""
        print(f"{prefix}{vendor} / {category}: {count} products → {years}yr")

    if not dry_run:
        conn.commit()

    conn.close()

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Total warranty_years updated: {total_updated} products")


if __name__ == "__main__":
    main()
