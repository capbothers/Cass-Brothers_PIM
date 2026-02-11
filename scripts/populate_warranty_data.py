#!/usr/bin/env python3
"""
Populate warranty_url and warranty_years for all products by vendor.
Uses a manually researched mapping of vendor → warranty page URL.
"""

import sqlite3
import sys

DB_PATH = "supplier_products.db"

# Vendor → (warranty_url, default_warranty_years)
# warranty_years is the GENERAL/default warranty for the brand.
# Many brands have different warranties for different product types,
# so this is a baseline that can be refined per-product later.
VENDOR_WARRANTY_MAP = {
    "Parisi": (
        "https://parisi.com.au/pages/warranty-information",
        None  # Varies by product type
    ),
    "Nero Tapware": (
        "https://nerotapware.com.au/warranty-policy/",
        25  # 25yr replacement on finishes & cartridges
    ),
    "Caroma": (
        "https://www.caroma.com/au/caroma-warranties/",
        None  # Varies: tapware 15yr, ceramics 25yr lifetime
    ),
    "Phoenix Tapware": (
        "https://www.phoenixtapware.com.au/warranty/",
        15  # 15yr cartridge, 7yr product/parts
    ),
    "Villeroy & Boch": (
        "https://www.argentaust.com.au/argent-australia-warranty-information",
        10  # 10yr toilet seats, 5yr ceramics
    ),
    "Thermogroup": (
        "https://www.thermogroup.com.au/warranty/",
        None  # Lifetime on underfloor, 3yr thermostats
    ),
    "Argent": (
        "https://www.argentaust.com.au/argent-australia-warranty-information",
        None  # Varies by product
    ),
    "Cassa Design": (
        "https://www.cassadesign.com.au/",
        None  # 5-25yr depending on product
    ),
    "Oliveri": (
        "https://oliveri.com.au/support/product-care/service-and-warranty/",
        15  # 15yr tapware (5yr P&L + 10yr cartridge)
    ),
    "Fienza": (
        "https://fienza.com.au/warranty/",
        None  # Varies: 15yr cartridges, 25yr cast stone
    ),
    "Greens": (
        "https://greenstapware.com.au/warranty-and-care/",
        20  # 20yr cartridge warranty
    ),
    "Zip": (
        "https://www.zipwater.com/warranty",
        5  # 3yr parts/labour, 5yr internal tank
    ),
    "Gareth Ashton": (
        "https://www.abey.com.au/warranty/",
        15  # 15yr cartridge (distributed by Abey)
    ),
    "Studio Bagno": (
        "https://studiobagno.com.au/",
        10  # 10yr replacement warranty
    ),
    "Avenir": (
        "https://www.avenir.com.au/",
        10  # 10yr warranty on all products
    ),
    "Brodware": (
        "https://www.brodware.com/warranty/",
        20  # 5yr P&L + 15yr parts only = 20yr total
    ),
    "Abey": (
        "https://www.abey.com.au/warranty/",
        None  # Varies by product type
    ),
    "Sussex": (
        "https://sussextaps.com.au/wp-content/uploads/2022/06/Sussex_Warranty.pdf",
        15  # Up to 15yr tapware
    ),
    "Turner Hastings": (
        "https://www.turnerhastings.com.au/customer-service/installation-care-warranty-information",
        None  # Lifetime on fireclay/TitanCast, varies others
    ),
    "Hansgrohe": (
        "https://www.hansgrohe.com.au/service/guarantee",
        5  # 5yr guarantee
    ),
    "Franke": (
        "https://www.franke.com/au/en/home-solutions/support/warranty.html",
        50  # 50yr Fragranite sinks
    ),
    "Victoria + Albert": (
        "https://vandabaths.com/en-au/our-material/our-guarantee/",
        25  # 25yr QUARRYCAST guarantee
    ),
    "Puretec": (
        "https://www.puretec.com.au/puretec-warranty-statement",
        10  # Up to 10yr on systems
    ),
    "Timberline": (
        "https://timberline.com.au/wp-content/uploads/2023/03/TBP2505-1-Website-Downloads_Warranty-1.pdf",
        10  # 5-20yr depending on product
    ),
    "Kaldewei": (
        "https://www.bathe.net.au/warranties/support/",
        30  # 30yr quality guarantee
    ),
    "Decina": (
        "https://decina.com.au/decina-warranty-terms-conditions/",
        10  # 10yr bath shell, 5yr pump/fittings
    ),
    "Globo": (
        "https://www.bathe.net.au/warranties/",
        None  # Varies by product
    ),
    "Blanco": (
        "https://www.blanco.com/au-en/",
        None  # Lifetime domestic, 5yr multi-res, 3yr commercial
    ),
    "Pietra Bianca": (
        "https://pietrabianca.com.au/",
        5  # 5yr residential, 3yr commercial
    ),
    "Rifco": (
        "https://www.rifco.com.au/",
        7  # 7yr vanity, 10yr Caesarstone/Corian tops
    ),
    "Velux": (
        "https://www.velux.com.au/service-and-warranty/velux-warranty",
        10  # 10yr skylights, 3yr accessories
    ),
    "Bathroom Butler": (
        "https://www.bathroombutler.com/au/",
        None  # Contact for specific warranty period
    ),
    "Clark": (
        "https://www.caroma.com/au/caroma-warranties/",
        None  # Lifetime warranty on sinks/tubs (Clark brand)
    ),
    "Verotti": (
        "https://www.austpekbathrooms.com.au/pages/verotti-brand-warranty",
        None  # Varies: 25yr shower screens, 10yr toilets
    ),
    "Mixx Tapware": (
        "https://mixxtapware.com.au/downloads/warranty/",
        20  # 20yr warranty incl 5yr P&L
    ),
    "Shaws": (
        "https://www.shawsofdarwen.com/media/yonlxvxs/shaws-of-darwen-warranty-01-2025.pdf",
        None  # Lifetime on fireclay sinks
    ),
    "Euro Appliances": (
        "https://www.euroappliances.au/warranty",
        3  # 3yr parts and labour
    ),
    "Armando Vicario": (
        "https://www.abey.com.au/warranty/",
        15  # 15yr cartridge (distributed by Abey)
    ),
    "Billi": (
        "https://www.billi.com.au/warranty-registration/",
        1  # 1yr full warranty on taps
    ),
    "Gessi": (
        "https://www.abey.com.au/warranty/",
        None  # Distributed by Abey/Oliveri
    ),
    "Arcisan": (
        "https://www.streamlineproducts.com.au/brands/arcisan",
        15  # Up to 15yr warranty
    ),
    "ADP": (
        "https://www.adpaustralia.com.au/",
        10  # 10yr cabinets, 1yr tops/accessories
    ),
    "Rinnai": (
        "https://www.rinnai.com.au/support-resources/warranty-information/",
        None  # Varies by product (HW, heaters, etc.)
    ),
    "Linkware": (
        "https://www.linkwareint.com/",
        15  # 15yr mixers, 7yr tapware
    ),
    "Geberit": (
        "https://www.geberit.com.au/services/warranty/",
        15  # Up to 15yr concealed cisterns
    ),
    "TOTO": (
        "https://bandh.com.au/toto-australia-warranty/",
        None  # Varies by product
    ),
    "Rheem": (
        "https://www.rheem.com.au/rheem/help/warranties",
        12  # Up to 12yr on electric HW cylinders
    ),
    "Insinkerator": (
        "https://www.insinkerator.com.au/home-full-service-limited-warranty",
        None  # 1-10yr depending on model
    ),
    "Marquis": (
        None,
        None
    ),
    "Newform": (
        None,
        None
    ),
    "Suprema Xpressfit": (
        None,
        None
    ),
    "Gentec": (
        None,
        None
    ),
    "Stormtech": (
        "https://www.stormtech.com.au/",
        None
    ),
    "DADOquartz\u00ae": (
        None,
        10  # 10yr warranty
    ),
    "Hotwire": (
        "https://www.hotwireheating.com.au/",
        None
    ),
    "Concrete Studio": (
        None,
        None
    ),
    "Master Rail": (
        None,
        None
    ),
    "Ledin Australia": (
        None,
        None
    ),
    "Elson": (
        None,
        None
    ),
    "Expella": (
        "https://www.expella.com.au/",
        None
    ),
    "TECE": (
        None,
        None
    ),
    "Bette": (
        "https://www.bette.de/en/",
        30  # 30yr guarantee
    ),
    "Bounty Brassware": (
        None,
        None
    ),
    "Haron": (
        None,
        None
    ),
    "Meir Tapware": (
        "https://www.meir.com.au/",
        15  # 15yr warranty
    ),
    "Kohler": (
        "https://www.kohler.com.au/",
        None
    ),
    "Rainware": (
        None,
        None
    ),
    "Ventair": (
        None,
        None
    ),
    "Stiebel Eltron": (
        "https://www.stiebel-eltron.com.au/",
        None
    ),
    "Dorf": (
        "https://www.dorf.com.au/",
        None
    ),
    "Hansa": (
        None,
        None
    ),
    "Kaskade": (
        None,
        None
    ),
    "Zucchetti": (
        None,
        None
    ),
    "Reln": (
        None,
        None
    ),
    "IXL": (
        None,
        None
    ),
    "KWC": (
        None,
        None
    ),
    "Paco Jaanson": (
        None,
        None
    ),
}


def main():
    dry_run = "--dry-run" in sys.argv

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    total_url_updated = 0
    total_years_updated = 0

    for vendor, (warranty_url, warranty_years) in VENDOR_WARRANTY_MAP.items():
        if warranty_url is None and warranty_years is None:
            continue

        # Count products for this vendor that need updating
        cursor.execute(
            "SELECT COUNT(*) FROM shopify_products WHERE vendor = ? AND status = 'active'",
            (vendor,)
        )
        count = cursor.fetchone()[0]

        if count == 0:
            continue

        updates = []

        if warranty_url:
            cursor.execute(
                "SELECT COUNT(*) FROM shopify_products WHERE vendor = ? AND status = 'active' AND (warranty_url IS NULL OR warranty_url = '')",
                (vendor,)
            )
            url_count = cursor.fetchone()[0]
            if url_count > 0:
                if not dry_run:
                    cursor.execute(
                        "UPDATE shopify_products SET warranty_url = ? WHERE vendor = ? AND status = 'active' AND (warranty_url IS NULL OR warranty_url = '')",
                        (warranty_url, vendor)
                    )
                total_url_updated += url_count
                updates.append(f"warranty_url for {url_count} products")

        if warranty_years is not None:
            cursor.execute(
                "SELECT COUNT(*) FROM shopify_products WHERE vendor = ? AND status = 'active' AND (warranty_years IS NULL OR warranty_years = 0)",
                (vendor,)
            )
            years_count = cursor.fetchone()[0]
            if years_count > 0:
                if not dry_run:
                    cursor.execute(
                        "UPDATE shopify_products SET warranty_years = ? WHERE vendor = ? AND status = 'active' AND (warranty_years IS NULL OR warranty_years = 0)",
                        (warranty_years, vendor)
                    )
                total_years_updated += years_count
                updates.append(f"warranty_years={warranty_years} for {years_count} products")

        if updates:
            prefix = "[DRY RUN] " if dry_run else ""
            print(f"{prefix}{vendor} ({count} active): {', '.join(updates)}")

    if not dry_run:
        conn.commit()

    conn.close()

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Summary:")
    print(f"  warranty_url updated: {total_url_updated} products")
    print(f"  warranty_years updated: {total_years_updated} products")


if __name__ == "__main__":
    main()
