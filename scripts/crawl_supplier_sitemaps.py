#!/usr/bin/env python3
"""
Crawl Supplier Sitemaps to Discover Product URLs

Reads supplier_urls.csv and for each reachable supplier with a sitemap:
1. Fetches the sitemap (handles sitemap indexes recursively)
2. Extracts product-like URLs
3. Stores discovered URLs in the SQLite database and outputs a summary CSV

Usage:
    python scripts/crawl_supplier_sitemaps.py
    python scripts/crawl_supplier_sitemaps.py --vendor "Abey"
    python scripts/crawl_supplier_sitemaps.py --limit 10
"""

import os
import sys
import csv
import re
import time
import sqlite3
import requests
import argparse
from datetime import datetime
from urllib.parse import urlparse
from xml.etree import ElementTree as ET
from typing import List, Dict, Optional, Set

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

# URL patterns that indicate a product page
PRODUCT_PATTERNS = [
    r'/products?/',
    r'/p/',
    r'/catalogue/',
    r'/item/',
    r'/shop/',
    r'/collection[s]?/.+/.+',  # e.g. /collections/basins/product-name
]
PRODUCT_RE = re.compile('|'.join(PRODUCT_PATTERNS), re.IGNORECASE)

# URL patterns to exclude (not product pages)
EXCLUDE_PATTERNS = [
    r'/cart',
    r'/account',
    r'/login',
    r'/blog/',
    r'/news/',
    r'/contact',
    r'/about',
    r'/faq',
    r'/terms',
    r'/privacy',
    r'/policy',
    r'/sitemap',
    r'/feed',
    r'/wp-content/',
    r'/wp-admin/',
    r'/tag/',
    r'/category/',
    r'\.(jpg|jpeg|png|gif|svg|pdf|css|js)$',
]
EXCLUDE_RE = re.compile('|'.join(EXCLUDE_PATTERNS), re.IGNORECASE)

# XML namespace for sitemaps
NS = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}


def fetch_sitemap(url: str, timeout: int = 20) -> Optional[str]:
    """Fetch sitemap XML content."""
    try:
        resp = requests.get(url, timeout=timeout, headers=HEADERS)
        if resp.status_code == 200:
            return resp.text
    except Exception as e:
        print(f"    Error fetching {url}: {e}")
    return None


def parse_sitemap(xml_text: str, base_url: str, depth: int = 0, max_depth: int = 3) -> List[str]:
    """
    Parse sitemap XML and return all URLs.
    Handles sitemap indexes by recursively fetching sub-sitemaps.
    """
    if depth > max_depth:
        return []

    urls = []

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    tag = root.tag.lower()

    # Sitemap index - contains links to other sitemaps
    if 'sitemapindex' in tag:
        for sitemap in root.findall('.//sm:sitemap/sm:loc', NS):
            sub_url = sitemap.text.strip() if sitemap.text else ''
            if sub_url:
                time.sleep(0.3)
                sub_xml = fetch_sitemap(sub_url)
                if sub_xml:
                    urls.extend(parse_sitemap(sub_xml, base_url, depth + 1, max_depth))
        # Also try without namespace (some sitemaps don't use it)
        if not urls:
            for sitemap in root.findall('.//sitemap/loc'):
                sub_url = sitemap.text.strip() if sitemap.text else ''
                if sub_url:
                    time.sleep(0.3)
                    sub_xml = fetch_sitemap(sub_url)
                    if sub_xml:
                        urls.extend(parse_sitemap(sub_xml, base_url, depth + 1, max_depth))

    # URL set - contains actual page URLs
    elif 'urlset' in tag:
        for url_elem in root.findall('.//sm:url/sm:loc', NS):
            url = url_elem.text.strip() if url_elem.text else ''
            if url:
                urls.append(url)
        # Try without namespace
        if not urls:
            for url_elem in root.findall('.//url/loc'):
                url = url_elem.text.strip() if url_elem.text else ''
                if url:
                    urls.append(url)

    return urls


def is_product_url(url: str) -> bool:
    """Check if a URL looks like a product page."""
    if EXCLUDE_RE.search(url):
        return False
    if PRODUCT_RE.search(url):
        return True
    return False


def classify_urls(urls: List[str]) -> Dict[str, List[str]]:
    """Classify sitemap URLs into product and non-product."""
    product_urls = []
    other_urls = []

    for url in urls:
        if is_product_url(url):
            product_urls.append(url)
        else:
            other_urls.append(url)

    return {
        'product': product_urls,
        'other': other_urls,
    }


def init_db(db_path: str):
    """Create the discovered_urls table if it doesn't exist."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS discovered_urls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_name TEXT NOT NULL,
            url TEXT NOT NULL,
            url_type TEXT DEFAULT 'product',
            sitemap_source TEXT,
            discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            scraped_at TIMESTAMP,
            sku_extracted TEXT,
            UNIQUE(vendor_name, url)
        )
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_disc_vendor ON discovered_urls(vendor_name)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_disc_type ON discovered_urls(url_type)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_disc_scraped ON discovered_urls(scraped_at)
    ''')

    conn.commit()
    conn.close()


def store_urls(db_path: str, vendor_name: str, urls: List[str],
               url_type: str, sitemap_source: str) -> int:
    """Store discovered URLs in the database. Returns count of new URLs inserted."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    inserted = 0
    for url in urls:
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO discovered_urls
                (vendor_name, url, url_type, sitemap_source)
                VALUES (?, ?, ?, ?)
            ''', (vendor_name, url, url_type, sitemap_source))
            if cursor.rowcount > 0:
                inserted += 1
        except Exception:
            pass

    conn.commit()
    conn.close()
    return inserted


def read_supplier_urls(csv_path: str) -> List[Dict[str, str]]:
    """Read supplier_urls.csv and return rows with sitemaps."""
    suppliers = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('has_sitemap') == 'True' and row.get('sitemap_url'):
                suppliers.append(row)
    return suppliers


def main():
    parser = argparse.ArgumentParser(description='Crawl supplier sitemaps for product URLs')
    parser.add_argument('--vendor', '-v', help='Only crawl a specific vendor')
    parser.add_argument('--limit', '-l', type=int, default=0,
                       help='Limit number of suppliers to crawl (0=all)')
    parser.add_argument('--input', '-i', default='supplier_urls.csv',
                       help='Input supplier URLs CSV')
    parser.add_argument('--db', default='supplier_data.db',
                       help='SQLite database path')

    args = parser.parse_args()

    csv_path = os.path.join(REPO_ROOT, args.input)
    db_path = os.path.join(REPO_ROOT, args.db)

    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found. Run discover_supplier_urls.py first.")
        sys.exit(1)

    # Init database
    init_db(db_path)

    # Read suppliers with sitemaps
    suppliers = read_supplier_urls(csv_path)

    if args.vendor:
        suppliers = [s for s in suppliers if s['vendor_name'].lower() == args.vendor.lower()]
        if not suppliers:
            print(f"No supplier found matching '{args.vendor}' with a sitemap.")
            sys.exit(1)

    if args.limit > 0:
        suppliers = suppliers[:args.limit]

    print("=" * 70)
    print("  Crawl Supplier Sitemaps")
    print("=" * 70)
    print(f"\nSuppliers with sitemaps: {len(suppliers)}")
    print(f"Database: {db_path}\n")

    total_product_urls = 0
    total_other_urls = 0
    results = []

    for i, supplier in enumerate(suppliers, 1):
        vendor = supplier['vendor_name']
        sitemap_url = supplier['sitemap_url']
        product_count = supplier.get('product_count', '?')

        print(f"[{i}/{len(suppliers)}] {vendor:<35} ({product_count:>5} Shopify products)")
        print(f"    Sitemap: {sitemap_url}")

        # Fetch sitemap
        xml_text = fetch_sitemap(sitemap_url)
        if not xml_text:
            print(f"    FAILED to fetch sitemap")
            results.append({
                'vendor_name': vendor,
                'sitemap_url': sitemap_url,
                'total_urls': 0,
                'product_urls': 0,
                'other_urls': 0,
                'new_urls': 0,
                'status': 'fetch_failed',
            })
            continue

        # Parse sitemap (recursively follows sitemap indexes)
        all_urls = parse_sitemap(xml_text, sitemap_url)
        print(f"    Found {len(all_urls)} total URLs in sitemap")

        if not all_urls:
            results.append({
                'vendor_name': vendor,
                'sitemap_url': sitemap_url,
                'total_urls': 0,
                'product_urls': 0,
                'other_urls': 0,
                'new_urls': 0,
                'status': 'no_urls',
            })
            continue

        # Classify URLs
        classified = classify_urls(all_urls)
        product_urls = classified['product']
        other_urls = classified['other']

        # Store product URLs
        new_product = store_urls(db_path, vendor, product_urls, 'product', sitemap_url)
        # Also store non-product URLs (might find products in them later)
        new_other = store_urls(db_path, vendor, other_urls, 'page', sitemap_url)

        total_product_urls += len(product_urls)
        total_other_urls += len(other_urls)

        print(f"    Product URLs: {len(product_urls)} ({new_product} new)")
        print(f"    Other URLs:   {len(other_urls)} ({new_other} new)")

        results.append({
            'vendor_name': vendor,
            'sitemap_url': sitemap_url,
            'total_urls': len(all_urls),
            'product_urls': len(product_urls),
            'other_urls': len(other_urls),
            'new_urls': new_product + new_other,
            'status': 'ok',
        })

        time.sleep(0.5)  # Be polite between suppliers

    # Write summary CSV
    summary_path = os.path.join(REPO_ROOT, 'sitemap_crawl_summary.csv')
    if results:
        fieldnames = list(results[0].keys())
        with open(summary_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

    # Print summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    print(f"Suppliers crawled:     {len(results)}")
    print(f"Total product URLs:    {total_product_urls}")
    print(f"Total other URLs:      {total_other_urls}")
    print(f"Total URLs:            {total_product_urls + total_other_urls}")

    # Database stats
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM discovered_urls WHERE url_type = 'product'")
    db_product_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT vendor_name) FROM discovered_urls")
    db_vendor_count = cursor.fetchone()[0]
    conn.close()

    print(f"\nDatabase totals:")
    print(f"  Product URLs in DB:  {db_product_count}")
    print(f"  Vendors in DB:       {db_vendor_count}")
    print(f"\nSummary CSV: {summary_path}")

    # Top vendors by product URLs
    if results:
        print(f"\nTop suppliers by product URLs found:")
        sorted_results = sorted(results, key=lambda x: x['product_urls'], reverse=True)
        for r in sorted_results[:20]:
            if r['product_urls'] > 0:
                print(f"  {r['vendor_name']:<35} {r['product_urls']:>6} product URLs")


if __name__ == "__main__":
    main()
