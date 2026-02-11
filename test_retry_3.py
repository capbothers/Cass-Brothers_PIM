#!/usr/bin/env python3
"""Quick test to retry 3 specific products"""
import sys
import os
sys.path.insert(0, '/workspaces/Cass-Brothers_PIM')
os.chdir('/workspaces/Cass-Brothers_PIM')

from scripts.enrich_shopify_products import ShopifyEnrichmentPipeline
import sqlite3
from dotenv import load_dotenv

load_dotenv()

# Get the 3 products
conn = sqlite3.connect('supplier_products.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

target_skus = ['FRA540', '1X3440I', '1ISX100L']

query = """
SELECT
    sp.id as shopify_id,
    sp.sku,
    sp.title,
    p.product_url as supplier_url,
    p.supplier_name
FROM shopify_products sp
LEFT JOIN supplier_products p ON sp.sku = p.sku
WHERE sp.sku IN (?, ?, ?)
"""

cursor.execute(query, target_skus)
products = [dict(row) for row in cursor.fetchall()]
conn.close()

print(f"\n{'='*80}")
print("RETRY TEST: 3 Previously Failed Products")
print(f"{'='*80}\n")

# Initialize enricher
enricher = ShopifyEnrichmentPipeline()

# Process each product
for i, product in enumerate(products, 1):
    print(f"[{i}/3] Processing {product['sku']}...")

    result = enricher.process_product(product)

    if result.get('success'):
        print(f"  ✓ {result['classification']}: {result.get('specs_count', 0)} specs, confidence {result.get('confidence', 0):.2f}")
    else:
        print(f"  ✗ Failed: {result.get('error', 'Unknown error')}")

print(f"\n{'='*80}")
print("RETRY TEST COMPLETE")
print(f"{'='*80}\n")
