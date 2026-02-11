#!/usr/bin/env python3
"""
Scrape supplier websites for missing sink dimensions.

Fetches product pages from supplier websites, extracts dimension data
using Claude Haiku, and updates the PIM database.

Usage:
    python scripts/scrape_sink_dimensions.py --dry-run
    python scripts/scrape_sink_dimensions.py --vendor Oliveri --dry-run
    python scripts/scrape_sink_dimensions.py --vendor "Meir Tapware"
"""

import json
import time
import argparse
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

DB_PATH = 'supplier_products.db'

# Fields we want to extract/fill (must exist in shopify_products table)
DIMENSION_FIELDS = [
    'overall_width_mm', 'overall_depth_mm', 'overall_height_mm',
    'number_of_bowls', 'overall_length_mm',
    'has_overflow', 'number_of_tap_holes', 'material',
    'installation_type', 'weight_kg',
]

# Haiku pricing (per million tokens)
HAIKU_INPUT_PRICE = 0.25
HAIKU_OUTPUT_PRICE = 1.25


def get_sinks_missing_dimensions(vendor: str = None) -> List[Dict]:
    """Get sinks missing dimension data that have scrapeable URLs."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
        SELECT sp.id, sp.sku, sp.title, sp.vendor, sp.super_category,
               sp.overall_width_mm, sp.overall_depth_mm, sp.overall_height_mm,
               sp.number_of_bowls, sp.overall_length_mm,
               sp.has_overflow, sp.number_of_tap_holes, sp.material,
               sp.installation_type, sp.weight_kg,
               su.product_url
        FROM shopify_products sp
        JOIN supplier_products su ON sp.sku = su.sku
        WHERE sp.status = 'active'
        AND sp.super_category = 'Sinks'
        AND (sp.overall_width_mm IS NULL OR sp.overall_width_mm = '')
        AND (sp.overall_depth_mm IS NULL OR sp.overall_depth_mm = '')
        AND (sp.overall_height_mm IS NULL OR sp.overall_height_mm = '')
        AND su.product_url IS NOT NULL AND su.product_url != ''
    """
    params = []

    if vendor:
        query += " AND sp.vendor = ?"
        params.append(vendor)

    # Skip vendors known to be blocked
    query += """
        AND sp.vendor NOT IN ('Phoenix Tapware')
        AND su.product_url NOT LIKE '%caroma.com%'
    """

    query += " ORDER BY sp.vendor, sp.sku"

    cursor.execute(query, params)
    products = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return products


def fetch_page_text(url: str, timeout: int = 15) -> Optional[str]:
    """Fetch a URL and return cleaned text content."""
    try:
        response = requests.get(url, timeout=timeout, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # Remove scripts and styles
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()

        # Try to find product-specific content
        product_div = soup.find(['div', 'section', 'main'], class_=lambda x: x and any(
            term in str(x).lower()
            for term in ['product', 'woocommerce', 'entry-content', 'item', 'spec']
        ))

        if product_div:
            text = product_div.get_text(separator='\n', strip=True)
        else:
            text = soup.get_text(separator='\n', strip=True)

        # Truncate to avoid huge payloads
        return text[:6000]

    except requests.RequestException as e:
        return None


def extract_dimensions_llm(client: Anthropic, page_text: str, product_title: str) -> Tuple[Dict, float]:
    """Use Claude Haiku to extract sink dimensions from page text."""

    prompt = f"""Extract sink/basin dimensions and specifications from this product page.

PRODUCT: {product_title}

Return ONLY a JSON object with these fields (use null if not found):
{{
    "overall_width_mm": <integer, the total width of the sink in mm>,
    "overall_depth_mm": <integer, the front-to-back depth in mm>,
    "overall_height_mm": <integer, the total height/depth of the bowl in mm>,
    "number_of_bowls": <integer, 1 or 2 or 3>,
    "overall_length_mm": <integer, for sinks with drainers, total length including drainer>,
    "has_overflow": <boolean, true/false>,
    "number_of_tap_holes": <integer, 0-3>,
    "material": <string, e.g. "Stainless Steel", "Granite Composite", etc.>,
    "installation_type": <string, e.g. "Topmount", "Undermount", "Topmount, Undermount">,
    "weight_kg": <decimal, weight in kg>
}}

IMPORTANT RULES:
1. "Cut out template" dimensions = the sink's OVERALL dimensions (width x depth)
2. If a sink has a drainer, overall_length_mm = total length including drainer, overall_width_mm = just the bowl area width
3. For sinks WITHOUT drainers, overall_width_mm = total width, no overall_length_mm needed
4. Bowl dimensions are INTERNAL measurements (smaller than overall)
5. Convert any cm measurements to mm (multiply by 10)
6. Only include fields where you have confident data from the page
7. Return {{}} if no specifications found

PAGE CONTENT:
{page_text}"""

    try:
        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )

        input_tokens = message.usage.input_tokens
        output_tokens = message.usage.output_tokens
        cost = (input_tokens / 1_000_000 * HAIKU_INPUT_PRICE +
                output_tokens / 1_000_000 * HAIKU_OUTPUT_PRICE)

        response_text = message.content[0].text.strip()

        # Extract JSON from response
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()
        else:
            first_brace = response_text.find('{')
            last_brace = response_text.rfind('}')
            if first_brace >= 0 and last_brace > first_brace:
                response_text = response_text[first_brace:last_brace + 1]

        extracted = json.loads(response_text)
        return extracted, cost

    except (json.JSONDecodeError, Exception) as e:
        return {'error': str(e)}, 0.0


def update_product(conn: sqlite3.Connection, product_id: int, specs: Dict, existing: Dict) -> int:
    """Update a product with extracted specs. Only fills gaps (doesn't overwrite).
    Returns count of fields updated."""
    cursor = conn.cursor()
    updates = []
    values = []
    updated_count = 0

    for field in DIMENSION_FIELDS:
        new_val = specs.get(field)
        if new_val is None or new_val == '' or new_val == 'null':
            continue

        # Only fill gaps - don't overwrite existing data
        existing_val = existing.get(field)
        if existing_val is not None and existing_val != '' and existing_val != 'None':
            continue

        # Validate numeric fields
        if field.endswith('_mm') or field in ('weight_kg', 'number_of_bowls', 'number_of_tap_holes'):
            try:
                new_val = float(new_val) if field == 'weight_kg' else int(float(new_val))
                if new_val <= 0:
                    continue
                # Sanity checks
                if field.endswith('_mm') and (new_val < 10 or new_val > 5000):
                    continue
                if field == 'weight_kg' and (new_val < 0.1 or new_val > 200):
                    continue
                if field == 'number_of_bowls' and new_val not in (1, 2, 3):
                    continue
                if field == 'number_of_tap_holes' and new_val not in (0, 1, 2, 3):
                    continue
            except (ValueError, TypeError):
                continue
        elif field == 'has_overflow':
            if isinstance(new_val, bool):
                new_val = 1 if new_val else 0
            elif isinstance(new_val, str):
                new_val = 1 if new_val.lower() in ('true', 'yes', '1') else 0
            else:
                try:
                    new_val = int(new_val)
                except (ValueError, TypeError):
                    continue
        elif field in ('material', 'installation_type'):
            new_val = str(new_val).strip()
            if not new_val or new_val.lower() in ('none', 'null', 'n/a'):
                continue

        updates.append(f"{field} = ?")
        values.append(new_val)
        updated_count += 1

    if updates:
        values.append(product_id)
        sql = f"UPDATE shopify_products SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(sql, values)

    return updated_count


def main():
    parser = argparse.ArgumentParser(description='Scrape supplier websites for sink dimensions')
    parser.add_argument('--dry-run', action='store_true', help='Preview without database changes')
    parser.add_argument('--vendor', type=str, help='Filter by vendor name')
    parser.add_argument('--limit', type=int, default=0, help='Limit number of products to scrape')
    args = parser.parse_args()

    print("=" * 70)
    print("  SINK DIMENSION SCRAPER")
    if args.dry_run:
        print("  MODE: Dry run (no database changes)")
    print("=" * 70)

    # Get products
    products = get_sinks_missing_dimensions(vendor=args.vendor)
    if args.limit:
        products = products[:args.limit]

    print(f"\nProducts to scrape: {len(products)}")

    # Vendor breakdown
    vendors = {}
    for p in products:
        v = p['vendor']
        vendors[v] = vendors.get(v, 0) + 1
    for v, c in sorted(vendors.items(), key=lambda x: -x[1]):
        print(f"  {v}: {c}")

    if not products:
        print("No products to scrape.")
        return

    # Initialize Anthropic client
    client = Anthropic()

    # Stats
    total_cost = 0.0
    total_fields_updated = 0
    success_count = 0
    fail_count = 0
    skip_count = 0

    conn = sqlite3.connect(DB_PATH) if not args.dry_run else None

    results = []

    for i, product in enumerate(products):
        sku = product['sku']
        title = product['title']
        url = product['product_url']
        vendor = product['vendor']

        print(f"\n[{i+1}/{len(products)}] {vendor} | {sku} | {title[:50]}")

        # Fetch page
        page_text = fetch_page_text(url)
        if not page_text:
            print(f"  SKIP: Could not fetch {url}")
            skip_count += 1
            continue

        # Extract with LLM
        specs, cost = extract_dimensions_llm(client, page_text, title)
        total_cost += cost

        if 'error' in specs:
            print(f"  ERROR: {specs['error']}")
            fail_count += 1
            continue

        if not specs:
            print(f"  EMPTY: No specs extracted")
            fail_count += 1
            continue

        # Filter to dimension fields only
        dim_specs = {k: v for k, v in specs.items() if k in DIMENSION_FIELDS and v is not None}

        if not dim_specs:
            print(f"  EMPTY: No dimension data in response")
            fail_count += 1
            continue

        # Show what was found
        dims_str = ', '.join(f"{k}={v}" for k, v in dim_specs.items())
        print(f"  FOUND: {dims_str}")

        result = {
            'sku': sku,
            'title': title,
            'vendor': vendor,
            'url': url,
            'specs': dim_specs,
            'cost': cost,
        }

        # Update database
        if not args.dry_run:
            fields_updated = update_product(conn, product['id'], dim_specs, product)
            result['fields_updated'] = fields_updated
            total_fields_updated += fields_updated
            if fields_updated:
                print(f"  UPDATED: {fields_updated} fields")
        else:
            # Count how many would be new
            would_update = sum(
                1 for f in dim_specs
                if product.get(f) is None or product.get(f) == '' or product.get(f) == 'None'
            )
            result['fields_would_update'] = would_update
            total_fields_updated += would_update

        results.append(result)
        success_count += 1

        # Brief delay between API calls
        time.sleep(0.3)

    # Commit
    if conn:
        conn.commit()
        conn.close()

    # Summary
    print(f"\n{'=' * 70}")
    print(f"SCRAPING COMPLETE")
    print(f"{'=' * 70}")
    print(f"Total products: {len(products)}")
    print(f"Success: {success_count}")
    print(f"Failed: {fail_count}")
    print(f"Skipped (fetch error): {skip_count}")
    print(f"Total fields {'would be ' if args.dry_run else ''}updated: {total_fields_updated}")
    print(f"Total LLM cost: ${total_cost:.4f}")

    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_file = f'sink_scrape_results_{timestamp}.json'
    with open(results_file, 'w') as f:
        json.dump({
            'timestamp': timestamp,
            'dry_run': args.dry_run,
            'vendor_filter': args.vendor,
            'stats': {
                'total': len(products),
                'success': success_count,
                'failed': fail_count,
                'skipped': skip_count,
                'fields_updated': total_fields_updated,
                'cost': total_cost,
            },
            'results': results,
        }, f, indent=2)
    print(f"\nResults saved: {results_file}")


if __name__ == '__main__':
    main()
