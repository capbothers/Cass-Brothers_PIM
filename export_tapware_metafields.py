#!/usr/bin/env python3
"""Export all tapware products with metafield values to CSV"""

import csv
import io
import sys
import os

# Add project root to path so we can import config
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

# Taps spreadsheet ID from .env.template
TAPS_SPREADSHEET_ID = os.environ.get('TAPS_SPREADSHEET_ID', '1jJ5thuNoxcITHkFAfFKPmUfaLYC3dSo2oppiN0s7i1U')

# Column mapping from TapsCollection config (collections.py lines 291-351)
# Maps field_name -> column_index (1-based)
COLUMN_MAPPING = {
    # System fields
    'url': 1,
    'variant_sku': 2,
    'title': 6,
    'vendor': 7,
    # Metafields (H-Y)
    'brand_name': 8,
    'range': 9,
    'style': 10,
    'mounting_type': 11,
    'colour_finish': 12,
    'material': 13,
    'warranty_years': 14,
    'spout_height_mm': 15,
    'spout_reach_mm': 16,
    'handle_type': 17,
    'handle_count': 18,
    'swivel_spout': 19,
    'cartridge_type': 20,
    'flow_rate': 21,
    'wels_rating': 22,
    'wels_registration_number': 23,
    'lead_free_compliance': 24,
    'application_location': 25,
}

# CSV output columns in desired order
CSV_COLUMNS = [
    'variant_sku',
    'title',
    'vendor',
    'brand_name',
    'range',
    'style',
    'mounting_type',
    'colour_finish',
    'material',
    'warranty_years',
    'spout_height_mm',
    'spout_reach_mm',
    'handle_type',
    'handle_count',
    'swivel_spout',
    'cartridge_type',
    'flow_rate',
    'wels_rating',
    'wels_registration_number',
    'lead_free_compliance',
    'application_location',
    'url',
]

# Friendly CSV header names
HEADER_NAMES = {
    'variant_sku': 'SKU',
    'title': 'Product Title',
    'vendor': 'Vendor',
    'brand_name': 'Brand',
    'range': 'Range',
    'style': 'Style',
    'mounting_type': 'Mounting / Installation Type',
    'colour_finish': 'Colour / Finish',
    'material': 'Material',
    'warranty_years': 'Warranty (Years)',
    'spout_height_mm': 'Spout Height (mm)',
    'spout_reach_mm': 'Spout Reach (mm)',
    'handle_type': 'Handle Type',
    'handle_count': 'Handle Count',
    'swivel_spout': 'Swivel Spout',
    'cartridge_type': 'Cartridge Type',
    'flow_rate': 'Flow Rate (L/min)',
    'wels_rating': 'WELS Rating',
    'wels_registration_number': 'WELS Registration Number',
    'lead_free_compliance': 'Lead Free Compliance',
    'application_location': 'Application / Location',
    'url': 'Supplier URL',
}


def fetch_taps_csv():
    """Fetch taps data from public Google Sheets CSV export"""
    csv_url = f"https://docs.google.com/spreadsheets/d/{TAPS_SPREADSHEET_ID}/export?format=csv&gid=0"
    print(f"Fetching taps data from Google Sheets...")

    response = requests.get(csv_url, timeout=60)
    response.raise_for_status()

    reader = csv.reader(response.text.splitlines())
    rows = list(reader)

    if len(rows) < 2:
        print("No data rows found!")
        return []

    print(f"Found {len(rows) - 1} rows (excluding header)")

    products = []
    for row_data in rows[1:]:
        # Pad row if needed
        while len(row_data) < max(COLUMN_MAPPING.values()):
            row_data.append('')

        # Map columns to field names
        product = {}
        for field, col_index in COLUMN_MAPPING.items():
            value = row_data[col_index - 1] if col_index <= len(row_data) else ''
            product[field] = value.strip() if value else ''

        # Only include rows with meaningful data (has SKU or title)
        if product.get('variant_sku') or product.get('title'):
            products.append(product)

    print(f"Extracted {len(products)} products with data")
    return products


def write_csv(products, output_path):
    """Write products to CSV file"""
    headers = [HEADER_NAMES.get(col, col) for col in CSV_COLUMNS]

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        for product in products:
            row = [product.get(col, '') for col in CSV_COLUMNS]
            writer.writerow(row)

    print(f"CSV written to: {output_path}")
    print(f"Total products: {len(products)}")


if __name__ == '__main__':
    output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tapware_metafields_export.csv')

    products = fetch_taps_csv()
    if products:
        write_csv(products, output_file)
    else:
        print("No products found. The sheet may not be publicly accessible.")
        print("If so, set GOOGLE_CREDENTIALS_JSON in your .env and use the Flask app's export endpoint instead.")
