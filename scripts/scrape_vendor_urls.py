#!/usr/bin/env python3
"""
Vendor URL Scraper

Crawls vendor sitemaps to find product URLs and matches them to Shopify products by SKU.
"""

import sqlite3
import re
import time
import argparse
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
import requests

DB_PATH = 'supplier_products.db'

# Known vendor website mappings
VENDOR_SITES = {
    # Already scraped (batch 1)
    'Parisi': 'https://parisi.com.au',
    'Phoenix Tapware': 'https://www.phoenixtapware.com.au',
    'Caroma': 'https://www.caroma.com.au',
    'Argent': 'https://www.argentaust.com.au',
    'Oliveri': 'https://oliveri.com.au',
    'Cassa Design': 'https://www.cassadesign.com.au',
    'Greens': 'https://greenstapware.com.au',
    'Avenir': 'https://avenirdesign.com',
    'Sussex': 'https://sussextaps.com.au',
    'Fienza': 'https://fienza.com.au',
    'Brodware': 'https://www.brodware.com',
    'Billi': 'https://www.billi.com.au',
    'Expella': 'https://expella.com.au',
    'Haron': 'https://haron.com.au',
    'Meir Tapware': 'https://www.meir.com.au',
    'Linkware': 'https://www.linkwareint.com',
    'Turner Hastings': 'https://www.turnerhastings.com.au',
    # Batch 2 - remaining vendors
    'Nero Tapware': 'https://nerotapware.com.au',
    'Villeroy & Boch': 'https://www.villeroy-boch.com.au',
    'Thermogroup': 'https://www.thermogroup.com.au',
    'Studio Bagno': 'https://studiobagno.com.au',
    'Hansgrohe': 'https://www.hansgrohe.com.au',
    'Franke': 'https://www.franke.com',
    'Victoria + Albert': 'https://vandabaths.com',
    'Puretec': 'https://www.puretec.com.au',
    'Timberline': 'https://timberline.com.au',
    'Kaldewei': 'https://www.kaldewei.com',
    'Decina': 'https://decina.com.au',
    'Blanco': 'https://www.blanco.com',
    'Pietra Bianca': 'https://pietrabianca.com.au',
    'Rifco': 'https://www.rifco.com.au',
    'Velux': 'https://www.velux.com.au',
    'Bathroom Butler': 'https://www.bathroombutler.com',
    'Clark': 'https://www.clark.com.au',
    'Verotti': 'https://verotti.com',
    'Mixx Tapware': 'https://mixxtapware.com.au',
    'Shaws': 'https://www.shawsofdarwen.com',
    'Euro Appliances': 'https://www.euroappliances.au',
    'Gessi': 'https://www.gessi.com',
    'Arcisan': 'https://www.streamlineproducts.com.au',
    'ADP': 'https://www.adpaustralia.com.au',
    'Rinnai': 'https://www.rinnai.com.au',
    'Geberit': 'https://www.geberit.com.au',
    'TOTO': 'https://asia.toto.com',
    'Rheem': 'https://www.rheem.com.au',
    'Gareth Ashton': 'https://www.abey.com.au',
    'Zip': 'https://www.zipwater.com',
    'Globo': 'https://www.ceramicaglobo.com',
}


PRODUCT_URL_PATTERNS = [
    '/products/', '/product/', '/product-', '/shop/', '/store/',
    '/catalog/', '/item/', '/range/', '/ranges/',
    '/bathroom/', '/kitchen/', '/tapware/', '/accessories/',
    '/basins/', '/toilets/', '/baths/', '/sinks/', '/showers/',
    '/vanities/', '/mirrors/', '/mixers/', '/taps/',
]

# URL patterns to exclude (not product pages)
EXCLUDE_URL_PATTERNS = [
    '/blog/', '/news/', '/contact', '/about', '/privacy',
    '/terms', '/warranty', '/faq', '/support/', '/careers',
    '/login', '/account', '/cart', '/checkout', '/wishlist',
    '.pdf', '.jpg', '.png', '.gif', '/page/', '/tag/',
]


def get_sitemap_urls(base_url):
    """Fetch and parse sitemap.xml to get all product URLs"""
    urls = []
    sitemap_locations = [
        f"{base_url}/sitemap.xml",
        f"{base_url}/sitemap_products_1.xml",
        f"{base_url}/sitemap_products.xml",
        f"{base_url}/product-sitemap.xml",
        f"{base_url}/wp-sitemap.xml",
        f"{base_url}/sitemap_index.xml",
        f"{base_url}/sitemap-index.xml",
    ]

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    for sitemap_url in sitemap_locations:
        try:
            print(f"  Trying: {sitemap_url}")
            resp = requests.get(sitemap_url, headers=headers, timeout=30)
            if resp.status_code != 200:
                continue

            # Parse XML
            root = ET.fromstring(resp.content)
            ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

            # Check if this is a sitemap index
            sitemaps = root.findall('.//sm:sitemap/sm:loc', ns)
            if sitemaps:
                print(f"  Found sitemap index with {len(sitemaps)} sitemaps")
                for sm in sitemaps:
                    sm_url = sm.text
                    # Fetch ALL sub-sitemaps (not just "product" ones)
                    # Many sites use generic names like sitemap_sections_8_0.xml
                    print(f"    Fetching: {sm_url}")
                    time.sleep(0.5)
                    try:
                        sm_resp = requests.get(sm_url, headers=headers, timeout=30)
                        if sm_resp.status_code == 200:
                            sm_root = ET.fromstring(sm_resp.content)
                            locs = sm_root.findall('.//sm:url/sm:loc', ns)
                            count = 0
                            for loc in locs:
                                url = loc.text
                                if not url:
                                    continue
                                url_lower = url.lower()
                                # Skip excluded patterns
                                if any(p in url_lower for p in EXCLUDE_URL_PATTERNS):
                                    continue
                                # Filter for product-like URLs
                                if any(p in url_lower for p in PRODUCT_URL_PATTERNS):
                                    urls.append(url)
                                    count += 1
                            if count > 0:
                                print(f"    Found {count} product URLs")
                    except Exception as e:
                        print(f"    Error: {e}")
            else:
                # Direct URL list
                locs = root.findall('.//sm:url/sm:loc', ns)
                for loc in locs:
                    url = loc.text
                    if not url:
                        continue
                    url_lower = url.lower()
                    if any(p in url_lower for p in EXCLUDE_URL_PATTERNS):
                        continue
                    if any(p in url_lower for p in PRODUCT_URL_PATTERNS):
                        urls.append(url)
                if not urls:
                    # If no product URLs found with filters, grab all non-excluded URLs
                    for loc in locs:
                        url = loc.text
                        if url and not any(p in url.lower() for p in EXCLUDE_URL_PATTERNS):
                            urls.append(url)
                print(f"  Found {len(urls)} URLs")

            if urls:
                break

            # If sitemap index had sub-sitemaps but no product URLs matched,
            # grab all non-excluded URLs from those sitemaps as fallback
            if sitemaps and not urls:
                print(f"  No product-pattern URLs found, trying all URLs from sub-sitemaps...")
                for sm in sitemaps:
                    sm_url = sm.text
                    time.sleep(0.3)
                    try:
                        sm_resp = requests.get(sm_url, headers=headers, timeout=30)
                        if sm_resp.status_code == 200:
                            sm_root = ET.fromstring(sm_resp.content)
                            locs = sm_root.findall('.//sm:url/sm:loc', ns)
                            for loc in locs:
                                url = loc.text
                                if url and not any(p in url.lower() for p in EXCLUDE_URL_PATTERNS):
                                    urls.append(url)
                    except Exception:
                        pass
                if urls:
                    print(f"  Fallback: found {len(urls)} total URLs")
                    break

        except Exception as e:
            print(f"  Error fetching {sitemap_url}: {e}")
            # Try regex fallback for malformed XML
            if 'not well-formed' in str(e) and resp and resp.status_code == 200:
                try:
                    content = resp.text
                    # Extract URLs using regex from malformed XML
                    found_urls = re.findall(r'<loc>(https?://[^<]+)</loc>', content)
                    if found_urls:
                        # Check if these are sub-sitemaps
                        sub_sitemaps = [u for u in found_urls if 'sitemap' in u.lower() and u.endswith('.xml')]
                        if sub_sitemaps:
                            print(f"  Regex fallback: found {len(sub_sitemaps)} sub-sitemaps")
                            for sm_url in sub_sitemaps:
                                time.sleep(0.5)
                                try:
                                    sm_resp = requests.get(sm_url, headers=headers, timeout=30)
                                    if sm_resp.status_code == 200:
                                        sm_urls = re.findall(r'<loc>(https?://[^<]+)</loc>', sm_resp.text)
                                        count = 0
                                        for url in sm_urls:
                                            url_lower = url.lower()
                                            if any(p in url_lower for p in EXCLUDE_URL_PATTERNS):
                                                continue
                                            if any(p in url_lower for p in PRODUCT_URL_PATTERNS):
                                                urls.append(url)
                                                count += 1
                                        if count > 0:
                                            print(f"    Regex: found {count} product URLs from {sm_url.split('/')[-1]}")
                                except Exception:
                                    pass
                        else:
                            # Direct URLs
                            for url in found_urls:
                                url_lower = url.lower()
                                if any(p in url_lower for p in EXCLUDE_URL_PATTERNS):
                                    continue
                                if any(p in url_lower for p in PRODUCT_URL_PATTERNS):
                                    urls.append(url)
                            if not urls:
                                for url in found_urls:
                                    if not any(p in url.lower() for p in EXCLUDE_URL_PATTERNS):
                                        urls.append(url)
                            if urls:
                                print(f"  Regex fallback: found {len(urls)} URLs")
                except Exception as re_err:
                    print(f"  Regex fallback also failed: {re_err}")
            if urls:
                break
            continue

    return urls


def normalize_for_matching(text):
    """Normalize text for fuzzy matching"""
    if not text:
        return ''
    text = text.lower()
    # Remove vendor prefixes
    for prefix in ['parisi ', 'nero ', 'caroma ', 'phoenix ', 'fienza ',
                   'oliveri ', 'hansgrohe ', 'franke ', 'villeroy & boch ',
                   'greens ', 'sussex ', 'argent ', 'brodware ', 'avenir ',
                   'cassa design ', 'turner hastings ', 'gareth ashton ',
                   'thermogroup ', 'studio bagno ', 'blanco ', 'clark ',
                   'verotti ', 'mixx ', 'gessi ', 'arcisan ', 'adp ',
                   'rinnai ', 'geberit ', 'toto ', 'rheem ', 'zip ',
                   'puretec ', 'timberline ', 'kaldewei ', 'decina ',
                   'pietra bianca ', 'rifco ', 'velux ', 'bathroom butler ',
                   'euro appliances ', 'shaws ', 'victoria albert ',
                   'victoria + albert ', 'globo ', 'meir ']:
        if text.startswith(prefix):
            text = text[len(prefix):]
    # Remove SKU suffix (usually after last " - ")
    if ' - ' in text:
        text = text.rsplit(' - ', 1)[0]
    # Remove common noise
    text = re.sub(r'\d+x\d+', '', text)  # dimensions
    text = re.sub(r'\d+mm', '', text)  # mm measurements
    text = re.sub(r'\d+ltr?', '', text)  # litres
    # Keep only meaningful words
    text = re.sub(r'[^a-z0-9 ]', ' ', text)
    text = ' '.join(text.split())
    return text


def slug_to_words(slug):
    """Convert URL slug to searchable words"""
    return slug.lower().replace('-', ' ').replace('_', ' ')


def match_urls_to_products(vendor, urls):
    """Match sitemap URLs to Shopify products by SKU and title"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get all SKUs for this vendor that don't have URLs yet
    cursor.execute("""
        SELECT s.sku, s.title
        FROM shopify_products s
        LEFT JOIN supplier_products sp ON s.sku = sp.sku
        WHERE s.vendor = ?
        AND s.status = 'active'
        AND (sp.product_url IS NULL OR sp.product_url = '')
    """, (vendor,))

    products = cursor.fetchall()
    print(f"\n  Products needing URLs: {len(products)}")

    if not products:
        conn.close()
        return 0

    # Build lookup structures
    sku_lookup = {}  # normalized_sku -> (original_sku, title)
    title_lookup = {}  # normalized_title -> (original_sku, title)
    title_words_lookup = []  # [(key_words, original_sku, title)]

    for sku, title in products:
        # SKU-based matching
        sku_norm = sku.lower().replace('-', '').replace(' ', '').replace('.', '').replace('/', '')
        sku_lookup[sku_norm] = (sku, title)
        sku_lookup[sku.lower()] = (sku, title)

        # Title-based matching
        title_norm = normalize_for_matching(title)
        title_lookup[title_norm] = (sku, title)

        # Extract key words from title for partial matching
        words = set(title_norm.split())
        # Remove very common words
        words -= {'the', 'and', 'with', 'for', 'set', 'pack', 'kit', 'in', 'no', 'tap', 'hole'}
        if len(words) >= 2:
            title_words_lookup.append((words, sku, title))

    matched = 0
    used_skus = set()

    for url in urls:
        path = urlparse(url).path
        slug = path.rstrip('/').split('/')[-1]
        slug_norm = slug.lower().replace('-', '').replace(' ', '').replace('.', '').replace('/', '')
        slug_words = set(slug_to_words(slug).split())
        slug_words -= {'the', 'and', 'with', 'for', 'set', 'pack', 'kit', 'in', 'no', 'tap', 'hole'}

        best_match = None
        best_score = 0

        # Method 1: Direct SKU match in URL
        for sku_norm_key, (original_sku, title) in sku_lookup.items():
            if original_sku in used_skus:
                continue
            if len(sku_norm_key) >= 4 and sku_norm_key in slug_norm:
                best_match = (original_sku, title)
                best_score = 1.0
                break

        # Method 2: Title word overlap matching
        if not best_match and len(slug_words) >= 2:
            for words, sku, title in title_words_lookup:
                if sku in used_skus:
                    continue
                overlap = slug_words & words
                if len(overlap) >= 2:
                    # Score based on overlap ratio
                    score = len(overlap) / max(len(slug_words), len(words))
                    if score > best_score and score >= 0.4:
                        best_score = score
                        best_match = (sku, title)

        if best_match:
            original_sku, title = best_match
            used_skus.add(original_sku)

            # Save to database
            cursor.execute("SELECT id FROM supplier_products WHERE sku = ?", (original_sku,))
            existing = cursor.fetchone()

            if existing:
                cursor.execute(
                    "UPDATE supplier_products SET product_url = ?, supplier_name = ? WHERE sku = ?",
                    (url, vendor, original_sku)
                )
            else:
                cursor.execute("""
                    INSERT INTO supplier_products (sku, supplier_name, product_url)
                    VALUES (?, ?, ?)
                """, (original_sku, vendor, url))

            matched += 1

    conn.commit()
    conn.close()

    print(f"  Matched: {matched} products")
    return matched


def scrape_vendor(vendor, base_url):
    """Scrape a single vendor's sitemap and match URLs"""
    print(f"\n{'=' * 60}")
    print(f"SCRAPING: {vendor}")
    print(f"Site: {base_url}")
    print(f"{'=' * 60}")

    # Step 1: Get sitemap URLs
    urls = get_sitemap_urls(base_url)

    if not urls:
        print(f"\n  No product URLs found in sitemap")
        return 0

    print(f"\n  Total product URLs found: {len(urls)}")

    # Step 2: Match to products
    matched = match_urls_to_products(vendor, urls)

    return matched


def main():
    parser = argparse.ArgumentParser(description='Scrape vendor URLs')
    parser.add_argument('--vendor', help='Specific vendor to scrape')
    parser.add_argument('--url', help='Base URL for the vendor website')
    parser.add_argument('--list', action='store_true', help='List vendors needing URLs')
    parser.add_argument('--all', action='store_true', help='Scrape all vendors in VENDOR_SITES')
    args = parser.parse_args()

    if args.list:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.vendor, COUNT(*) as total,
                   SUM(CASE WHEN sp.product_url IS NOT NULL AND sp.product_url != '' THEN 1 ELSE 0 END) as has_url,
                   COUNT(*) - SUM(CASE WHEN sp.product_url IS NOT NULL AND sp.product_url != '' THEN 1 ELSE 0 END) as missing
            FROM shopify_products s
            LEFT JOIN supplier_products sp ON s.sku = sp.sku
            WHERE s.status = 'active'
            GROUP BY s.vendor
            HAVING missing > 0
            ORDER BY missing DESC
            LIMIT 40
        """)
        print(f"\n{'Vendor':<25s} {'Total':>6s} {'Has URL':>8s} {'Missing':>8s}")
        print("-" * 50)
        for row in cursor.fetchall():
            print(f"{row[0]:<25s} {row[1]:>6d} {row[2]:>8d} {row[3]:>8d}")
        conn.close()
        return

    if args.all:
        total_matched = 0
        results = []
        for vendor, url in VENDOR_SITES.items():
            matched = scrape_vendor(vendor, url)
            total_matched += matched
            results.append((vendor, matched))
            time.sleep(1)  # Be polite between vendors

        print(f"\n\n{'=' * 60}")
        print(f"SCRAPING COMPLETE - RESULTS")
        print(f"{'=' * 60}")
        for vendor, matched in sorted(results, key=lambda x: -x[1]):
            if matched > 0:
                print(f"  {vendor:<30s} +{matched} URLs")
        print(f"\n  TOTAL NEW URLs: {total_matched}")
        return

    if args.vendor and args.url:
        scrape_vendor(args.vendor, args.url)
    elif args.vendor and args.vendor in VENDOR_SITES:
        scrape_vendor(args.vendor, VENDOR_SITES[args.vendor])
    else:
        print("Usage: python scripts/scrape_vendor_urls.py --vendor 'Vendor Name' --url 'https://vendor-site.com'")
        print("       python scripts/scrape_vendor_urls.py --vendor 'Vendor Name'  (if in VENDOR_SITES)")
        print("       python scripts/scrape_vendor_urls.py --all")
        print("       python scripts/scrape_vendor_urls.py --list")


if __name__ == '__main__':
    main()
