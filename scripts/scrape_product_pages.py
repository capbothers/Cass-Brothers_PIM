#!/usr/bin/env python3
"""
Scrape Product Pages from Discovered URLs

Reads product URLs from the discovered_urls table (supplier_data.db),
fetches each page, extracts product data (SKU, name, images, specs),
and stores results in the supplier_products table (supplier_products.db).

Extraction strategies (tried in order):
1. Shopify JSON endpoint (/products/{handle}.json)
2. JSON-LD structured data (schema.org Product)
3. Open Graph meta tags + HTML parsing

Usage:
    python scripts/scrape_product_pages.py
    python scripts/scrape_product_pages.py --vendor "Parisi"
    python scripts/scrape_product_pages.py --vendor "Fienza" --limit 20
    python scripts/scrape_product_pages.py --unscraped-only --limit 100
"""

import os
import sys
import re
import json
import time
import sqlite3
import argparse
import requests
from datetime import datetime
from urllib.parse import urlparse, urljoin
from typing import Dict, List, Optional, Any
from html.parser import HTMLParser

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-AU,en;q=0.9',
}

# Common SKU patterns in Australian bathroom/kitchen suppliers
SKU_PATTERNS = [
    # Alphanumeric with dots/dashes: PM.001, CLA-IB-150-GW, JOL60F
    r'\b([A-Z]{2,5}[\.\-][A-Z0-9][\w\.\-]{2,20})\b',
    # Model codes: 3 letters + digits
    r'\b([A-Z]{3}\d{2,6}[A-Z]?)\b',
    # Codes with slashes: 68-1234
    r'\b(\d{2,3}-\d{4,6})\b',
]
SKU_RE = [re.compile(p) for p in SKU_PATTERNS]


class ProductData:
    """Container for extracted product data."""

    def __init__(self):
        self.sku = ''
        self.name = ''
        self.description = ''
        self.price = ''
        self.currency = 'AUD'
        self.image_url = ''
        self.images = []
        self.specs = {}
        self.brand = ''
        self.category = ''
        self.url = ''
        self.source = ''  # shopify_json, json_ld, html_parse

    def to_dict(self) -> dict:
        return {
            'sku': self.sku,
            'name': self.name,
            'description': self.description[:500] if self.description else '',
            'price': self.price,
            'currency': self.currency,
            'image_url': self.image_url,
            'images': self.images[:10],
            'specs': self.specs,
            'brand': self.brand,
            'category': self.category,
            'url': self.url,
            'source': self.source,
        }

    def is_valid(self) -> bool:
        """A product is valid if it has at least a name or SKU."""
        return bool(self.name or self.sku)


# ============================================================
# Extraction Strategy 1: Shopify JSON API
# ============================================================

def try_shopify_json(url: str, timeout: int = 15) -> Optional[ProductData]:
    """
    Try to fetch product data from Shopify's JSON endpoint.
    Works for URLs like /products/{handle} -> /products/{handle}.json
    """
    parsed = urlparse(url)
    path = parsed.path.rstrip('/')

    # Must match /products/{handle} pattern
    if '/products/' not in path:
        return None

    # Build JSON URL
    json_url = f"{parsed.scheme}://{parsed.netloc}{path}.json"

    try:
        resp = requests.get(json_url, timeout=timeout, headers=HEADERS)
        if resp.status_code != 200:
            return None

        data = resp.json()
        product = data.get('product', {})
        if not product:
            return None

        pd = ProductData()
        pd.source = 'shopify_json'
        pd.name = product.get('title', '')
        pd.brand = product.get('vendor', '')
        pd.category = product.get('product_type', '')
        pd.url = url

        # Get description (strip HTML)
        body = product.get('body_html', '')
        if body:
            pd.description = strip_html(body)

        # Get images
        images = product.get('images', [])
        if images:
            pd.image_url = images[0].get('src', '')
            pd.images = [img.get('src', '') for img in images if img.get('src')]

        # Get SKU and price from first variant
        variants = product.get('variants', [])
        if variants:
            first = variants[0]
            pd.sku = first.get('sku', '')
            pd.price = first.get('price', '')

            # If multiple variants, collect all SKUs
            if len(variants) > 1:
                all_skus = [v.get('sku', '') for v in variants if v.get('sku')]
                if all_skus:
                    pd.specs['all_skus'] = all_skus
                    pd.specs['variant_count'] = len(variants)

        # Extract specs from tags
        tags = product.get('tags', '')
        if isinstance(tags, list):
            tags = ', '.join(tags)
        if tags:
            pd.specs['tags'] = tags

        return pd if pd.is_valid() else None

    except (requests.RequestException, json.JSONDecodeError, KeyError):
        return None


# ============================================================
# Extraction Strategy 2: JSON-LD structured data
# ============================================================

def try_json_ld(html: str, url: str) -> Optional[ProductData]:
    """Extract product data from JSON-LD structured data in HTML."""
    # Find all JSON-LD blocks
    pattern = r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
    matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)

    for match in matches:
        try:
            data = json.loads(match.strip())
        except json.JSONDecodeError:
            continue

        # Handle @graph arrays
        if isinstance(data, list):
            for item in data:
                result = _parse_jsonld_product(item, url)
                if result:
                    return result
        elif isinstance(data, dict):
            if data.get('@graph'):
                for item in data['@graph']:
                    result = _parse_jsonld_product(item, url)
                    if result:
                        return result
            else:
                result = _parse_jsonld_product(data, url)
                if result:
                    return result

    return None


def _parse_jsonld_product(data: dict, url: str) -> Optional[ProductData]:
    """Parse a single JSON-LD object looking for Product type."""
    item_type = data.get('@type', '')

    # Handle type as list: ["Product", "IndividualProduct"]
    if isinstance(item_type, list):
        types = [t.lower() for t in item_type]
    else:
        types = [item_type.lower()]

    if 'product' not in types:
        return None

    pd = ProductData()
    pd.source = 'json_ld'
    pd.url = url
    pd.name = data.get('name', '')
    pd.description = data.get('description', '')
    if pd.description:
        pd.description = strip_html(pd.description)

    # Brand
    brand = data.get('brand', {})
    if isinstance(brand, dict):
        pd.brand = brand.get('name', '')
    elif isinstance(brand, str):
        pd.brand = brand

    # SKU
    pd.sku = data.get('sku', '') or data.get('mpn', '') or data.get('gtin', '')

    # Images
    img = data.get('image', '')
    if isinstance(img, list):
        pd.images = [i if isinstance(i, str) else i.get('url', '') for i in img]
        pd.image_url = pd.images[0] if pd.images else ''
    elif isinstance(img, dict):
        pd.image_url = img.get('url', '') or img.get('contentUrl', '')
        pd.images = [pd.image_url] if pd.image_url else []
    elif isinstance(img, str):
        pd.image_url = img
        pd.images = [img] if img else []

    # Offers (price)
    offers = data.get('offers', {})
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if isinstance(offers, dict):
        pd.price = str(offers.get('price', ''))
        pd.currency = offers.get('priceCurrency', 'AUD')

    # Category
    pd.category = data.get('category', '')

    # Additional properties
    for prop in data.get('additionalProperty', []):
        if isinstance(prop, dict) and prop.get('name') and prop.get('value'):
            pd.specs[prop['name']] = prop['value']

    return pd if pd.is_valid() else None


# ============================================================
# Extraction Strategy 3: HTML + Meta tag parsing
# ============================================================

def try_html_parse(html: str, url: str) -> Optional[ProductData]:
    """Extract product data from HTML meta tags and common patterns."""
    pd = ProductData()
    pd.source = 'html_parse'
    pd.url = url

    # Open Graph tags
    og_title = extract_meta(html, 'og:title')
    og_image = extract_meta(html, 'og:image')
    og_desc = extract_meta(html, 'og:description')
    og_price = extract_meta(html, 'product:price:amount') or extract_meta(html, 'og:price:amount')
    og_currency = extract_meta(html, 'product:price:currency') or 'AUD'

    pd.name = og_title or extract_title(html)
    pd.description = og_desc or ''
    pd.image_url = og_image or ''
    pd.price = og_price or ''
    pd.currency = og_currency

    if pd.image_url:
        pd.images = [pd.image_url]

    # Try to extract SKU from meta tags
    sku_meta = extract_meta(html, 'product:sku') or extract_meta(html, 'product:retailer_item_id')
    if sku_meta:
        pd.sku = sku_meta

    # Try to find SKU in visible text using multiple strategies
    if not pd.sku:
        pd.sku = extract_sku_from_html(html)

    # Try brand from meta
    brand_meta = extract_meta(html, 'product:brand') or extract_meta(html, 'og:site_name')
    if brand_meta:
        pd.brand = brand_meta

    return pd if pd.is_valid() else None


# ============================================================
# HTML Helpers
# ============================================================

class HTMLStripper(HTMLParser):
    """Strip HTML tags and return plain text."""

    def __init__(self):
        super().__init__()
        self.result = []
        self.skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip = True

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip = False

    def handle_data(self, data):
        if not self.skip:
            self.result.append(data)

    def get_text(self):
        return ' '.join(self.result)


def strip_html(html: str) -> str:
    """Remove HTML tags and return clean text."""
    stripper = HTMLStripper()
    try:
        stripper.feed(html)
        text = stripper.get_text()
    except Exception:
        text = re.sub(r'<[^>]+>', ' ', html)
    # Collapse whitespace
    return re.sub(r'\s+', ' ', text).strip()


def extract_meta(html: str, property_name: str) -> str:
    """Extract content from a meta tag by property or name attribute."""
    # Try property attribute first (Open Graph style)
    pattern = rf'<meta\s+(?:[^>]*?)property=["\'](?:{re.escape(property_name)})["\'][^>]*?content=["\']([^"\']*)["\']'
    match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()

    # Try content before property
    pattern = rf'<meta\s+(?:[^>]*?)content=["\']([^"\']*)["\'][^>]*?property=["\'](?:{re.escape(property_name)})["\']'
    match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()

    # Try name attribute
    pattern = rf'<meta\s+(?:[^>]*?)name=["\'](?:{re.escape(property_name)})["\'][^>]*?content=["\']([^"\']*)["\']'
    match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()

    return ''


def extract_sku_from_html(html: str) -> str:
    """
    Extract SKU/product code from HTML using multiple strategies.
    Returns the first valid SKU found, or empty string.
    """
    # Strategy 1: data-specifications-product-code attribute (Sussex, etc.)
    spec_code_match = re.search(
        r'data-specifications-product-code=["\']([A-Z0-9][\w\.\-\/]{2,25})["\']',
        html, re.IGNORECASE
    )
    if spec_code_match:
        return spec_code_match.group(1).strip()

    # Strategy 2: WooCommerce sku class - <span class="sku">CLA-IB-150-GW</span>
    woo_match = re.search(
        r'class=["\'][^"\']*\bsku\b[^"\']*["\'][^>]*>([A-Z0-9][\w\.\-\/]{2,25})<',
        html, re.IGNORECASE
    )
    if woo_match:
        return woo_match.group(1).strip()

    # Strategy 3: product-code class - <span class="product-code">RBMS200RH-V</span>
    pc_match = re.search(
        r'class=["\'][^"\']*\bproduct-code\b[^"\']*["\'][^>]*>([A-Z0-9][\w\.\-\/]{2,25})<',
        html, re.IGNORECASE
    )
    if pc_match:
        return pc_match.group(1).strip()

    # Strategy 4: data-sku or data-product_sku attributes
    data_match = re.search(
        r'data-(?:product[_-])?sku=["\']([A-Z0-9][\w\.\-\/]{2,25})["\']',
        html, re.IGNORECASE
    )
    if data_match:
        return data_match.group(1).strip()

    # Strategy 5: "product number" header followed by value (Linsol pattern)
    # <h3>product number</h3><span class='description'>CLA-IB-150-GW</span>
    pn_match = re.search(
        r'product\s*number</h\d>\s*<span[^>]*>([A-Z0-9][\w\.\-\/]{2,25})<',
        html, re.IGNORECASE
    )
    if pn_match:
        return pn_match.group(1).strip()

    # Strategy 6: Labeled text patterns in various HTML structures
    # "SKU:", "Model:", "Product Code:", "Product Number:", "Item Code:", etc.
    label_patterns = [
        # Label followed by closing tag, then value in next element
        r'(?:SKU|Model\s*(?:No|Number)?|Product\s*(?:Code|Number|No)|Item\s*(?:Code|Number)|Part\s*(?:No|Number)|Article\s*(?:No|Number))\s*</(?:h\d|th|td|dt|span|div|p|label|strong)[^>]*>\s*<(?:span|td|dd|div|p)[^>]*>\s*([A-Z0-9][\w\.\-\/]{2,25})',
        # Label with colon directly followed by value
        r'(?:SKU|Model\s*(?:No|Number)?|Product\s*(?:Code|Number|No)|Item\s*(?:Code|Number)|Part\s*(?:No|Number)|Article\s*(?:No|Number))\s*[:]\s*</?\w[^>]*>\s*([A-Z0-9][\w\.\-\/]{2,25})',
        r'(?:SKU|Model\s*(?:No|Number)?|Product\s*(?:Code|Number|No)|Item\s*(?:Code|Number)|Part\s*(?:No|Number)|Article\s*(?:No|Number))\s*[:]\s*([A-Z0-9][\w\.\-\/]{2,25})',
    ]
    for pattern in label_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            # Filter out common false positives
            if candidate.lower() not in ('not', 'none', 'na', 'n', 'tba', 'tbc',
                                          'available', 'applicable', 'specified'):
                return candidate

    return ''


def extract_title(html: str) -> str:
    """Extract <title> tag content."""
    match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
    if match:
        title = match.group(1).strip()
        # Clean common suffixes like "| Brand Name" or "- Brand Name"
        title = re.split(r'\s*[\|–—-]\s*(?!.*[\|–—-])', title)[0].strip()
        return title
    return ''


# ============================================================
# Main Scraper Logic
# ============================================================

def scrape_product_url(url: str, timeout: int = 15) -> Optional[ProductData]:
    """
    Scrape a single product URL using multiple extraction strategies.
    Returns ProductData or None if extraction fails.
    """
    # Strategy 1: Try Shopify JSON (fast, structured, no HTML parsing needed)
    result = try_shopify_json(url, timeout)
    if result and result.sku:
        return result

    # Fetch the HTML page
    try:
        resp = requests.get(url, timeout=timeout, headers=HEADERS, allow_redirects=True)
        if resp.status_code != 200:
            return None
        html = resp.text
    except requests.RequestException:
        return None

    # Strategy 2: JSON-LD structured data
    result = try_json_ld(html, url)
    if result and result.is_valid():
        # If JSON-LD had no SKU, try to find one in HTML
        if not result.sku:
            sku = extract_sku_from_html(html)
            if sku:
                result.sku = sku
        return result

    # Strategy 3: HTML + meta tag parsing
    result = try_html_parse(html, url)
    if result and result.is_valid():
        return result

    return None


def get_discovered_urls(db_path: str, vendor: str = None,
                        unscraped_only: bool = False,
                        limit: int = 0) -> List[Dict[str, Any]]:
    """Read product URLs from the discovered_urls table."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = "SELECT * FROM discovered_urls WHERE url_type = 'product'"
    params = []

    if vendor:
        query += " AND vendor_name = ?"
        params.append(vendor)

    if unscraped_only:
        query += " AND scraped_at IS NULL"

    query += " ORDER BY vendor_name, id"

    if limit > 0:
        query += " LIMIT ?"
        params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def mark_url_scraped(db_path: str, url_id: int, sku: str = None):
    """Mark a discovered URL as scraped."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE discovered_urls
        SET scraped_at = CURRENT_TIMESTAMP, sku_extracted = ?
        WHERE id = ?
    ''', (sku, url_id))
    conn.commit()
    conn.close()


def store_product(db_path: str, vendor: str, product: ProductData,
                  source_url: str) -> bool:
    """Store extracted product data in supplier_products table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Ensure tables exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS supplier_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT UNIQUE NOT NULL,
            supplier_name TEXT NOT NULL,
            product_url TEXT NOT NULL,
            product_name TEXT,
            image_url TEXT,
            spec_sheet_url TEXT,
            last_scraped_at TIMESTAMP,
            detected_collection TEXT,
            confidence_score REAL,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Add extra columns if they don't exist
    for col, col_type in [('price', 'TEXT'), ('description', 'TEXT'),
                          ('specs_json', 'TEXT'), ('extraction_source', 'TEXT'),
                          ('all_images_json', 'TEXT')]:
        try:
            cursor.execute(f"ALTER TABLE supplier_products ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    sku = product.sku
    if not sku:
        # Generate a pseudo-SKU from URL if none found
        slug = urlparse(source_url).path.rstrip('/').split('/')[-1]
        sku = f"__{vendor.upper()[:3]}_{slug[:30]}"

    try:
        cursor.execute('''
            INSERT INTO supplier_products
            (sku, supplier_name, product_url, product_name, image_url,
             price, description, specs_json, extraction_source, all_images_json,
             last_scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(sku) DO UPDATE SET
                product_url = excluded.product_url,
                product_name = excluded.product_name,
                image_url = excluded.image_url,
                price = excluded.price,
                description = excluded.description,
                specs_json = excluded.specs_json,
                extraction_source = excluded.extraction_source,
                all_images_json = excluded.all_images_json,
                last_scraped_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
        ''', (
            sku, vendor, source_url, product.name, product.image_url,
            product.price, product.description[:1000] if product.description else '',
            json.dumps(product.specs) if product.specs else '',
            product.source,
            json.dumps(product.images[:10]) if product.images else '',
        ))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        conn.close()
        return False


def main():
    parser = argparse.ArgumentParser(description='Scrape product pages from discovered URLs')
    parser.add_argument('--vendor', '-v', help='Only scrape a specific vendor')
    parser.add_argument('--limit', '-l', type=int, default=0,
                       help='Limit number of URLs to scrape (0=all)')
    parser.add_argument('--unscraped-only', '-u', action='store_true',
                       help='Only scrape URLs not yet scraped')
    parser.add_argument('--discovery-db', default='supplier_data.db',
                       help='SQLite database with discovered_urls (default: supplier_data.db)')
    parser.add_argument('--product-db', default='supplier_products.db',
                       help='SQLite database for supplier_products (default: supplier_products.db)')
    parser.add_argument('--delay', type=float, default=0.5,
                       help='Delay between requests in seconds (default: 0.5)')
    parser.add_argument('--timeout', type=int, default=15,
                       help='Request timeout in seconds (default: 15)')

    args = parser.parse_args()

    discovery_db = os.path.join(REPO_ROOT, args.discovery_db)
    product_db = os.path.join(REPO_ROOT, args.product_db)

    if not os.path.exists(discovery_db):
        print(f"Error: {discovery_db} not found.")
        print("Run scripts/crawl_supplier_sitemaps.py first.")
        sys.exit(1)

    # Get URLs to scrape
    urls = get_discovered_urls(
        discovery_db,
        vendor=args.vendor,
        unscraped_only=args.unscraped_only,
        limit=args.limit,
    )

    if not urls:
        print("No URLs to scrape. Try different filters or run crawl_supplier_sitemaps.py first.")
        sys.exit(0)

    # Group by vendor for display
    vendor_counts = {}
    for u in urls:
        v = u['vendor_name']
        vendor_counts[v] = vendor_counts.get(v, 0) + 1

    print("=" * 70)
    print("  Scrape Product Pages")
    print("=" * 70)
    print(f"\nURLs to scrape: {len(urls)}")
    print(f"Vendors: {len(vendor_counts)}")
    print(f"Discovery DB: {discovery_db}")
    print(f"Product DB:   {product_db}")
    print(f"Delay: {args.delay}s, Timeout: {args.timeout}s")

    if len(vendor_counts) <= 10:
        print("\nVendor breakdown:")
        for v, c in sorted(vendor_counts.items(), key=lambda x: -x[1]):
            print(f"  {v:<35} {c:>5} URLs")

    # Scrape loop
    total = len(urls)
    success = 0
    failed = 0
    no_sku = 0
    skipped = 0
    current_vendor = None
    vendor_success = 0
    vendor_total = 0
    start_time = time.time()

    for i, url_row in enumerate(urls, 1):
        url = url_row['url']
        vendor = url_row['vendor_name']
        url_id = url_row['id']

        # Print vendor header when vendor changes
        if vendor != current_vendor:
            if current_vendor:
                print(f"    => {current_vendor}: {vendor_success}/{vendor_total} extracted")
            current_vendor = vendor
            vendor_success = 0
            vendor_total = 0
            print(f"\n[{vendor}] ({vendor_counts[vendor]} URLs)")

        vendor_total += 1
        elapsed = time.time() - start_time
        rate = i / elapsed if elapsed > 0 else 0

        # Progress indicator
        print(f"  [{i}/{total}] {rate:.1f}/s ", end='', flush=True)

        # Scrape the URL
        product = scrape_product_url(url, timeout=args.timeout)

        if product and product.is_valid():
            # Store in supplier_products DB
            stored = store_product(product_db, vendor, product, url)

            # Mark as scraped in discovery DB
            mark_url_scraped(discovery_db, url_id, product.sku)

            product.sku = str(product.sku) if product.sku else ''
            product.name = str(product.name) if product.name else ''
            sku_display = product.sku[:20] if product.sku else '(no SKU)'
            name_display = product.name[:35] if product.name else '?'

            if product.sku:
                print(f"OK  {sku_display:<20} {name_display} [{product.source}]")
                success += 1
                vendor_success += 1
            else:
                print(f"~   (no SKU) {name_display} [{product.source}]")
                no_sku += 1
                vendor_success += 1
        else:
            mark_url_scraped(discovery_db, url_id, None)
            print(f"FAIL {url[:60]}")
            failed += 1

        # Rate limiting
        time.sleep(args.delay)

    # Final vendor summary
    if current_vendor:
        print(f"    => {current_vendor}: {vendor_success}/{vendor_total} extracted")

    # Print summary
    elapsed = time.time() - start_time
    print(f"\n{'=' * 70}")
    print("SCRAPE SUMMARY")
    print(f"{'=' * 70}")
    print(f"Total URLs:        {total}")
    print(f"With SKU:          {success}")
    print(f"Without SKU:       {no_sku}")
    print(f"Failed:            {failed}")
    print(f"Time:              {elapsed:.1f}s ({total / elapsed:.1f} URLs/sec)" if elapsed > 0 else "")

    # Product DB stats
    if os.path.exists(product_db):
        conn = sqlite3.connect(product_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM supplier_products")
        total_products = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT supplier_name) FROM supplier_products")
        total_vendors = cursor.fetchone()[0]
        conn.close()
        print(f"\nProduct DB totals:")
        print(f"  Total products:  {total_products}")
        print(f"  Total vendors:   {total_vendors}")


if __name__ == "__main__":
    main()
