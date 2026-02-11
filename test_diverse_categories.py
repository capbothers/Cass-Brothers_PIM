#!/usr/bin/env python3
"""Test enrichment on diverse product categories"""
import sys
import os
sys.path.insert(0, '/workspaces/Cass-Brothers_PIM')
os.chdir('/workspaces/Cass-Brothers_PIM')

from scripts.enrich_shopify_products import ShopifyEnrichmentPipeline
import sqlite3
from dotenv import load_dotenv

load_dotenv()

# Diverse SKUs from different categories
target_skus = [
    # Basin Mixers/Taps
    'S2.01-1HH60.46',  # Parisi basin mixer
    '116-7813-00',  # Phoenix basin/bath mixer
    '1.9902.30.0.01',  # Brodware basin mixer
    '228103BN',  # Fienza basin mixer
    '65812Q.02.013',  # Newform basin mixer
    # Toilets
    '766910W + 237088CO',  # Caroma toilet
    'NRCR0001GM',  # Nero toilet backrest
    # Vanities
    'DX9T7__5',  # Rifco vanity
    'BIL-V-600-C-STU-W',  # Timberline vanity
    'DX6LX__3',  # Rifco vanity
    'LOTV480LLIBW',  # Timberline Lottie vanity
    # Baths
    'SBM137-S',  # DADOquartz bath
    'S2.02WF190',  # Parisi bath spout
    # Showers
    'MO168013HMB',  # Oliveri shower head
    'GS896-12',  # Phoenix shower shelf
    '900069',  # Armando Vicario shower
    'VS2800-31-1',  # Phoenix shower mixer
    'RO36341BN',  # Oliveri shower set
]

# Get products
conn = sqlite3.connect('supplier_products.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Build query with proper parameter placeholders
placeholders = ','.join('?' * len(target_skus))
query = f"""
SELECT
    sp.id as shopify_id,
    sp.sku,
    sp.title,
    p.product_url as supplier_url,
    p.supplier_name
FROM shopify_products sp
LEFT JOIN supplier_products p ON sp.sku = p.sku
WHERE sp.sku IN ({placeholders})
"""

cursor.execute(query, target_skus)
products = [dict(row) for row in cursor.fetchall()]
conn.close()

print(f"\n{'='*80}")
print(f"DIVERSE CATEGORY TEST: {len(products)} Products")
print(f"{'='*80}\n")

# Initialize enricher
enricher = ShopifyEnrichmentPipeline()

# Process each product
success_count = 0
fail_count = 0

for i, product in enumerate(products, 1):
    print(f"[{i}/{len(products)}] Processing {product['sku']}...")
    print(f"  Title: {product['title'][:60]}...")

    result = enricher.process_product(product)

    if result.get('success'):
        success_count += 1
        print(f"  ✓ {result['classification']}: {result.get('specs_count', 0)} specs, confidence {result.get('confidence', 0):.2f}")
    else:
        fail_count += 1
        print(f"  ✗ Failed: {result.get('error', 'Unknown error')}")

print(f"\n{'='*80}")
print("TEST COMPLETE")
print(f"{'='*80}\n")
print(f"Success: {success_count}/{len(products)} ({success_count/len(products)*100:.0f}%)")
print(f"Failed: {fail_count}/{len(products)}")
