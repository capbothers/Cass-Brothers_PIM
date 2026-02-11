#!/usr/bin/env python3
"""
Headless Browser Vendor Scraper

Uses Playwright to scrape vendor sites that block standard HTTP requests
(bot protection, JS-rendered SPAs, etc.)
"""

import sqlite3
import re
import time
import argparse
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

DB_PATH = 'supplier_products.db'

# Vendors that need headless browser
HEADLESS_VENDORS = {
    'Caroma': 'https://www.caroma.com.au',
    'Villeroy & Boch': 'https://www.villeroy-boch.com.au',
    'Studio Bagno': 'https://studiobagno.com.au',
    'Hansgrohe': 'https://www.hansgrohe.com.au',
    'Decina': 'https://decina.com.au',
    'Clark': 'https://www.clark.com.au',
    'Mixx Tapware': 'https://mixxtapware.com.au',
    'Franke': 'https://www.franke.com/au/en/home-solutions.html',
    'Blanco': 'https://www.blanco.com/au-en',
    'Puretec': 'https://puretec.com.au',
    'Rifco': 'https://www.rifco.com.au',
    'Globo': 'https://www.ceramicaglobo.com/en',
    'Timberline': 'https://timberline.com.au',
    'Kaldewei': 'https://www.kaldewei.com',
    'Bathroom Butler': 'https://www.bathroombutler.com/au',
    'Turner Hastings': 'https://www.turnerhastings.com.au',
}

EXCLUDE_PATTERNS = [
    '/blog/', '/news/', '/contact', '/about', '/privacy', '/terms',
    '/warranty', '/faq', '/support/', '/careers', '/login', '/account',
    '/cart', '/checkout', '/wishlist', '.pdf', '.jpg', '.png', '.gif',
    '.svg', '.ico', '.woff', '.css', '.js', 'javascript:', 'mailto:',
    '#', '/tag/', '/page/', '/author/',
]

STOP_WORDS = {'the', 'and', 'with', 'for', 'set', 'pack', 'kit', 'in',
              'no', 'tap', 'hole', 'mm', 'bar'}


def normalize(text, vendor=''):
    """Normalize text for fuzzy matching"""
    if not text:
        return ''
    text = text.lower()
    for prefix in [vendor.lower() + ' ', vendor.split()[0].lower() + ' ']:
        if text.startswith(prefix):
            text = text[len(prefix):]
    if ' - ' in text:
        text = text.rsplit(' - ', 1)[0]
    text = re.sub(r'\d+x\d+', '', text)
    text = re.sub(r'\d+mm', '', text)
    text = re.sub(r'[^a-z0-9 ]', ' ', text)
    return ' '.join(text.split())


def match_urls_to_db(vendor, urls):
    """Match discovered URLs to Shopify products in the database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT s.sku, s.title FROM shopify_products s
        LEFT JOIN supplier_products sp ON s.sku = sp.sku
        WHERE s.vendor = ? AND s.status = 'active'
        AND (sp.product_url IS NULL OR sp.product_url = '')
    """, (vendor,))
    products = cursor.fetchall()

    if not products:
        print(f"  No products needing URLs for {vendor}")
        conn.close()
        return 0

    # Build lookup structures
    sku_lookup = {}
    title_words_lookup = []

    for sku, title in products:
        sku_norm = sku.lower().replace('-', '').replace(' ', '').replace('.', '').replace('/', '')
        sku_lookup[sku_norm] = (sku, title)
        sku_lookup[sku.lower()] = (sku, title)

        title_norm = normalize(title, vendor)
        words = set(title_norm.split()) - STOP_WORDS
        if len(words) >= 2:
            title_words_lookup.append((words, sku, title))

    matched = 0
    used_skus = set()

    for url in urls:
        slug = urlparse(url).path.rstrip('/').split('/')[-1]
        if not slug or len(slug) < 3:
            continue
        slug_norm = slug.lower().replace('-', '').replace(' ', '').replace('.', '').replace('/', '').replace('.html', '')
        slug_words = set(slug.lower().replace('-', ' ').replace('_', ' ').replace('.html', '').split()) - STOP_WORDS

        best_match = None
        best_score = 0

        # SKU match
        for sku_key, (orig_sku, title) in sku_lookup.items():
            if orig_sku in used_skus:
                continue
            if len(sku_key) >= 4 and sku_key in slug_norm:
                best_match = (orig_sku, title)
                best_score = 1.0
                break

        # Title word match
        if not best_match and len(slug_words) >= 2:
            for words, sku, title in title_words_lookup:
                if sku in used_skus:
                    continue
                overlap = slug_words & words
                if len(overlap) >= 2:
                    score = len(overlap) / max(len(slug_words), len(words))
                    if score > best_score and score >= 0.35:
                        best_score = score
                        best_match = (sku, title)

        if best_match:
            orig_sku, title = best_match
            used_skus.add(orig_sku)
            cursor.execute("SELECT id FROM supplier_products WHERE sku = ?", (orig_sku,))
            existing = cursor.fetchone()
            if existing:
                cursor.execute(
                    "UPDATE supplier_products SET product_url = ?, supplier_name = ? WHERE sku = ?",
                    (url, vendor, orig_sku)
                )
            else:
                cursor.execute(
                    "INSERT INTO supplier_products (sku, supplier_name, product_url) VALUES (?, ?, ?)",
                    (orig_sku, vendor, url)
                )
            matched += 1

    conn.commit()
    conn.close()
    return matched


def extract_links(page, domain):
    """Extract all product-like links from a rendered page"""
    links = page.eval_on_selector_all(
        'a[href]',
        'elements => elements.map(e => e.href)'
    )

    domain_clean = domain.replace('https://', '').replace('http://', '').rstrip('/')
    product_urls = set()

    for link in links:
        if not link or not isinstance(link, str):
            continue
        link_lower = link.lower()

        # Must be from same domain
        if domain_clean not in link_lower and not link.startswith('/'):
            continue

        # Skip excluded patterns
        if any(p in link_lower for p in EXCLUDE_PATTERNS):
            continue

        # Must have a meaningful path
        path = urlparse(link).path.rstrip('/')
        if path and len(path) > 3 and path.count('/') >= 1:
            product_urls.add(link)

    return list(product_urls)


def crawl_vendor(page, vendor, domain, max_pages=80):
    """Crawl a vendor site using headless browser, following product links"""
    print(f"\n{'=' * 60}")
    print(f"HEADLESS SCRAPING: {vendor}")
    print(f"Site: {domain}")
    print(f"{'=' * 60}")

    visited = set()
    all_urls = set()
    to_visit = [domain + '/']
    domain_clean = domain.replace('https://', '').replace('http://', '').rstrip('/')

    # Category/listing page patterns to follow deeper
    follow_patterns = [
        '/product', '/range', '/collection', '/category', '/shop',
        '/kitchen', '/bathroom', '/laundry', '/tapware', '/basin',
        '/toilet', '/bath', '/sink', '/shower', '/vanit', '/mirror',
        '/filter', '/tap', '/mixer', '/accessor', '/catalogue',
        '/heater', '/heating', '/towel', '/drain', '/waste',
    ]

    pages_crawled = 0
    while to_visit and pages_crawled < max_pages:
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)

        try:
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
            # Wait for dynamic content to render
            page.wait_for_timeout(3000)
            # Try to wait for network idle briefly (non-fatal if it times out)
            try:
                page.wait_for_load_state('networkidle', timeout=10000)
            except Exception:
                pass
            pages_crawled += 1

            links = extract_links(page, domain)
            new_count = 0
            for link in links:
                if link not in all_urls:
                    all_urls.add(link)
                    new_count += 1

                    # Queue category/listing pages for deeper crawling
                    link_lower = link.lower()
                    if link not in visited and any(p in link_lower for p in follow_patterns):
                        to_visit.append(link)

            if pages_crawled % 5 == 0 or new_count > 0:
                print(f"  Page {pages_crawled}: {url.replace(domain, '')[:60]} (+{new_count} new, {len(all_urls)} total)")

        except Exception as e:
            print(f"  Error on {url[:60]}: {str(e)[:50]}")
            continue

    print(f"\n  Crawled {pages_crawled} pages, found {len(all_urls)} unique URLs")

    # Match to products
    if all_urls:
        matched = match_urls_to_db(vendor, list(all_urls))
        print(f"  Matched: {matched} products")
        return matched
    return 0


def scrape_vendor_headless(vendor, domain, browser):
    """Scrape a single vendor using headless browser"""
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport={'width': 1920, 'height': 1080},
        locale='en-AU',
    )
    page = context.new_page()

    try:
        matched = crawl_vendor(page, vendor, domain)
    finally:
        context.close()

    return matched


def variant_match(vendor):
    """After URL matching, try to assign URLs to color/size variants"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT s.sku, s.title, sp.product_url
        FROM shopify_products s
        JOIN supplier_products sp ON s.sku = sp.sku
        WHERE s.vendor = ? AND s.status = 'active'
        AND sp.product_url IS NOT NULL AND sp.product_url != ''
    """, (vendor,))
    matched_products = cursor.fetchall()

    cursor.execute("""
        SELECT s.sku, s.title
        FROM shopify_products s
        LEFT JOIN supplier_products sp ON s.sku = sp.sku
        WHERE s.vendor = ? AND s.status = 'active'
        AND (sp.product_url IS NULL OR sp.product_url = '')
    """, (vendor,))
    unmatched_products = cursor.fetchall()

    if not matched_products or not unmatched_products:
        conn.close()
        return 0

    def extract_base(title, v):
        for prefix in [v + ' ', v.split()[0] + ' ']:
            if title.lower().startswith(prefix.lower()):
                title = title[len(prefix):]
        parts = title.split(' - ')
        if len(parts) >= 3:
            title = ' - '.join(parts[:2])
        elif len(parts) >= 2:
            title = parts[0]
        for color in ['Chrome', 'Matte Black', 'Brushed Nickel', 'Brushed Gold',
                      'Gun Metal', 'Black', 'White', 'Matte White', 'Snow White',
                      'Twilight', 'Black Walnut', 'Onyx', 'Brushed Bronze',
                      'Aged Iron', 'Satin Nickel', 'Polished Chrome', 'Champagne',
                      'Natural', 'Brushed Brass', 'Warm Brushed Nickel']:
            title = title.replace(color, '')
        title = re.sub(r'(No|One|Two|Three|Left|Right)\s*Tap\s*Hole', '', title, flags=re.I)
        title = re.sub(r'\d+x\d+', '', title)
        title = re.sub(r'\bLH\b|\bRH\b', '', title)
        return ' '.join(title.split()).strip()

    base_to_url = {}
    for sku, title, url in matched_products:
        base = extract_base(title, vendor)
        if base and len(base) > 5:
            base_to_url[base] = url

    new_matched = 0
    for sku, title in unmatched_products:
        base = extract_base(title, vendor)
        if base in base_to_url:
            url = base_to_url[base]
            cursor.execute("SELECT id FROM supplier_products WHERE sku = ?", (sku,))
            existing = cursor.fetchone()
            if existing:
                cursor.execute(
                    "UPDATE supplier_products SET product_url = ?, supplier_name = ? WHERE sku = ?",
                    (url, vendor, sku)
                )
            else:
                cursor.execute(
                    "INSERT INTO supplier_products (sku, supplier_name, product_url) VALUES (?, ?, ?)",
                    (sku, vendor, url)
                )
            new_matched += 1

    conn.commit()
    conn.close()
    return new_matched


def main():
    parser = argparse.ArgumentParser(description='Headless browser vendor scraper')
    parser.add_argument('--vendor', help='Specific vendor to scrape')
    parser.add_argument('--all', action='store_true', help='Scrape all blocked vendors')
    parser.add_argument('--max-pages', type=int, default=80, help='Max pages to crawl per vendor')
    args = parser.parse_args()

    vendors_to_scrape = {}
    if args.vendor:
        if args.vendor in HEADLESS_VENDORS:
            vendors_to_scrape[args.vendor] = HEADLESS_VENDORS[args.vendor]
        else:
            print(f"Unknown vendor: {args.vendor}")
            print(f"Available: {', '.join(HEADLESS_VENDORS.keys())}")
            return
    elif args.all:
        vendors_to_scrape = HEADLESS_VENDORS
    else:
        print("Usage: python scripts/scrape_headless.py --vendor 'Caroma'")
        print("       python scripts/scrape_headless.py --all")
        print(f"\nAvailable vendors: {', '.join(HEADLESS_VENDORS.keys())}")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        results = []
        for vendor, domain in vendors_to_scrape.items():
            matched = scrape_vendor_headless(vendor, domain, browser)
            # Try variant matching too
            variant = variant_match(vendor)
            if variant > 0:
                print(f"  + {variant} variant matches")
            results.append((vendor, matched + variant))
            time.sleep(2)

        browser.close()

    print(f"\n\n{'=' * 60}")
    print(f"HEADLESS SCRAPING COMPLETE")
    print(f"{'=' * 60}")
    total = 0
    for vendor, matched in sorted(results, key=lambda x: -x[1]):
        print(f"  {vendor:<28s} +{matched} URLs")
        total += matched
    print(f"\n  TOTAL: +{total} new URLs")


if __name__ == '__main__':
    main()
