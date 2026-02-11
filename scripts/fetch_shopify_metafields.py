#!/usr/bin/env python3
"""
Fetch current Shopify metafields for a given super_category.
Saves results to JSON for comparison with PIM data.

Usage:
    python scripts/fetch_shopify_metafields.py --category Tapware
    python scripts/fetch_shopify_metafields.py --category Sinks
    python scripts/fetch_shopify_metafields.py --category all
"""

import os, sys, sqlite3, json, time, argparse
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import importlib.util
spec = importlib.util.spec_from_file_location("shopify_fetcher", os.path.join(REPO_ROOT, "core", "shopify_fetcher.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

from dotenv import load_dotenv
load_dotenv(os.path.join(REPO_ROOT, '.env'))


def main():
    parser = argparse.ArgumentParser(description='Fetch Shopify metafields for a category')
    parser.add_argument('--category', required=True, help='Super category or "all"')
    parser.add_argument('--output', help='Output JSON file (auto-generated if not specified)')
    args = parser.parse_args()

    shopify = mod.get_shopify_fetcher()

    conn = sqlite3.connect(os.path.join(REPO_ROOT, 'supplier_products.db'))
    cursor = conn.cursor()

    if args.category == 'all':
        query = "SELECT product_id, sku, vendor, title, super_category FROM shopify_products WHERE status='active' ORDER BY super_category, vendor, sku"
        cursor.execute(query)
    else:
        query = "SELECT product_id, sku, vendor, title, super_category FROM shopify_products WHERE status='active' AND super_category=? ORDER BY vendor, sku"
        cursor.execute(query, (args.category,))
    
    products = cursor.fetchall()
    conn.close()

    output_file = args.output or f"shopify_{args.category.lower().replace(' ', '_')}_metafields.json"

    print(f"Fetching metafields for {len(products)} {args.category} products from Shopify...")
    print(f"Estimated time: {len(products) * 0.5 / 60:.1f} minutes")
    print(f"Output: {output_file}")
    print()

    results = []
    errors = 0
    products_with_any = 0

    for i, (product_id, sku, vendor, title, super_cat) in enumerate(products):
        if i > 0 and i % 200 == 0:
            print(f"  Progress: {i}/{len(products)} ({products_with_any} with metafields, {errors} errors)")

        try:
            shopify._rate_limit()
            url = f"{shopify.base_url}/products/{product_id}/metafields.json"
            params = {'namespace': 'product_specifications', 'limit': 250}
            response = shopify.session.get(url, params=params)
            response.raise_for_status()

            metafields = {}
            for mf in response.json().get('metafields', []):
                key = mf.get('key', '')
                value = mf.get('value', '')
                mf_type = mf.get('type', '')
                if key and value:
                    metafields[key] = {'value': value, 'type': mf_type}

            if metafields:
                products_with_any += 1

            results.append({
                'product_id': product_id,
                'sku': sku,
                'vendor': vendor,
                'title': title,
                'super_category': super_cat,
                'metafields': metafields,
            })
        except Exception as e:
            errors += 1
            if errors <= 10:
                print(f"  Error for {sku}: {e}")
            results.append({
                'product_id': product_id,
                'sku': sku,
                'vendor': vendor,
                'title': title,
                'super_category': super_cat,
                'metafields': {},
                'error': str(e),
            })

    # Save results
    with open(os.path.join(REPO_ROOT, output_file), 'w') as f:
        json.dump(results, f, indent=2)

    # Summary
    from collections import Counter
    all_keys = Counter()
    for item in results:
        for k in item['metafields']:
            all_keys[k] += 1

    print(f"\n{'='*70}")
    print(f"SHOPIFY METAFIELD FETCH COMPLETE - {args.category}")
    print(f"{'='*70}")
    print(f"Total products: {len(products)}")
    print(f"Products with metafields: {products_with_any}")
    print(f"Errors: {errors}")
    print(f"\nMetafield keys found:")
    for key, count in all_keys.most_common():
        pct = count / len(products) * 100
        print(f"  {key:<40} {count:>6} ({pct:.1f}%)")
    print(f"\nResults saved to: {output_file}")


if __name__ == '__main__':
    main()
