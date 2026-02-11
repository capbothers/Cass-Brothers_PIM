#!/usr/bin/env python3
"""
Discover Supplier Website URLs and Sitemaps

Takes vendor names from the Shopify baseline CSV and:
1. Tries common URL patterns to find each supplier's website
2. Checks for sitemap.xml to discover product pages
3. Outputs a verified supplier_urls.csv

Usage:
    python scripts/discover_supplier_urls.py
    python scripts/discover_supplier_urls.py --min-products 100
"""

import os
import sys
import csv
import time
import requests
import argparse
from collections import Counter
from urllib.parse import urlparse

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Known URL overrides where the domain isn't obvious from the vendor name
KNOWN_URLS = {
    # Own brands - skip
    'Cass Brothers': None,
    'Cass Brothers Grates': None,
    'cassbrothers': None,
    'Timberline x Shaynna Blaze': None,  # same as Timberline

    # Verified supplier URLs (researched & confirmed)
    'Phoenix Tapware': 'www.phoenixtapware.com.au',
    'Nero Tapware': 'nerotapware.com.au',
    'Villeroy & Boch': 'www.argentaust.com.au',  # distributed by Argent Australia
    'Victoria + Albert': 'vandabaths.com',
    'Timberline': 'timberline.com.au',
    'Cassa Design': 'www.cassadesign.com.au',
    'Studio Bagno': 'studiobagno.com.au',
    'Pietra Bianca': 'pietrabianca.com.au',
    'Turner Hastings': 'www.turnerhastings.com.au',
    'Gareth Ashton': 'www.abey.com.au',  # sub-brand of Abey
    'Euro Appliances': 'www.euroappliances.au',
    'Milu Odourless': 'milu.com.au',
    'DADOquartz\u00ae': 'dadoquartz.com.au',
    'Master Rail': 'masterrail.com.au',
    'Greens': 'greenstapware.com.au',
    'Zip': 'zipwater.com',
    'ADP': 'www.adpaustralia.com.au',
    'Globo': 'ceramicaglobo.com',
    'Franke': 'franke.com',
    'Armando Vicario': 'www.abey.com.au',  # sub-brand of Abey
    'Mixx Tapware': 'mixxtapware.com.au',
    'Sussex': 'sussextaps.com.au',
    'Bounty Brassware': 'bountybrassware.com.au',
    'Fix a Tap': 'fixatap.com.au',
    'Fix A Loo': 'fixaloo.com.au',
    'Paco Jaanson': 'pacojaanson.com.au',
    'GRO Agencies': 'groagencies.com.au',
    'Concrete Studio': 'concrete.studio',
    'Suprema Xpressfit': 'xpressfit.com.au',
    'Ledin Australia': 'ledin.com.au',
    'Aqua Pure': 'aquapure.com.au',
    'Grates 2 Go Australia': 'grates2go.com.au',
    'The Bidet Shop': 'thebidetshop.com.au',
    'Omega Appliances': 'omega-appliances.com.au',
    'Stiebel Eltron': 'www.stiebel-eltron.com.au',

    # Corrected from first discovery run
    'Argent': 'www.argentaust.com.au',
    'Avenir': 'www.avenir.com.au',
    'Lauxes': 'lauxesgrates.com.au',
    'PLD': 'www.pldnsw.com.au',
    'Gessi': 'gessi.com',
    'Hansgrohe': 'www.hansgrohe.com.au',
    'Billi': 'www.billi.com.au',
    'Meir Tapware': 'www.meir.com.au',
    'Linkware': 'www.linkwareint.com',
    'Methven': 'www.methven.com',
    'Clark': 'www.clark.com.au',
    'Bette': 'www.my-bette.com',
    'Shaws': 'www.shawsofdarwen.com',
    'Arcisan': 'www.streamlineproducts.com.au',  # parent company
    'TURNER HASTINGS (TURHAS)': 'www.turnerhastings.com.au',  # duplicate name
    'Bathroom Butler': 'www.bathroombutler.com',
    'Hansa': 'www.hansa.com',
    'Insinkerator': 'www.insinkerator.com',
    'IXL': 'www.ixlappliances.com.au',
}


def guess_domains(vendor_name: str):
    """Generate candidate domain names from a vendor name."""
    # Check known overrides first
    if vendor_name in KNOWN_URLS:
        url = KNOWN_URLS[vendor_name]
        if url:
            return [url]
        return []  # None means skip (own brand)

    # Clean the vendor name for URL guessing
    clean = vendor_name.lower().strip()
    clean = clean.replace('&', '').replace('+', '').replace("'", '')
    clean = clean.replace('  ', ' ').strip()

    # Generate candidates
    slug = clean.replace(' ', '')  # "phoenixtapware"
    slug_dash = clean.replace(' ', '-')  # "phoenix-tapware"

    candidates = [
        f"{slug}.com.au",
        f"{slug}.com",
        f"{slug_dash}.com.au",
        f"{slug_dash}.com",
        f"www.{slug}.com.au",
        f"www.{slug}.com",
    ]

    return candidates


def check_url(domain: str, timeout: int = 15) -> dict:
    """Check if a domain is reachable and look for sitemap."""
    result = {
        'domain': domain,
        'reachable': False,
        'final_url': None,
        'has_sitemap': False,
        'sitemap_url': None,
        'product_url_count': 0,
    }

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    # Try multiple URL variations
    urls_to_try = [f"https://{domain}"]
    if not domain.startswith('www.'):
        urls_to_try.append(f"https://www.{domain}")
    urls_to_try.append(f"http://{domain}")

    for url in urls_to_try:
        try:
            resp = requests.get(url, timeout=timeout, allow_redirects=True,
                               headers=headers)
            if resp.status_code < 400:
                result['reachable'] = True
                result['final_url'] = resp.url
                break
        except Exception:
            continue

    # Check for sitemap
    if result['reachable']:
        base = result['final_url'].rstrip('/')
        parsed = urlparse(base)
        site_root = f"{parsed.scheme}://{parsed.netloc}"

        for sitemap_path in ['/sitemap.xml', '/sitemap_index.xml', '/sitemap_products.xml']:
            try:
                sm_resp = requests.get(f"{site_root}{sitemap_path}", timeout=timeout,
                                      headers=headers)
                if sm_resp.status_code == 200 and ('<?xml' in sm_resp.text[:100] or '<urlset' in sm_resp.text[:200] or '<sitemapindex' in sm_resp.text[:200]):
                    result['has_sitemap'] = True
                    result['sitemap_url'] = f"{site_root}{sitemap_path}"

                    # Count product-like URLs in sitemap
                    text = sm_resp.text.lower()
                    product_indicators = ['/product/', '/products/', '/p/', '/catalogue/']
                    count = sum(text.count(ind) for ind in product_indicators)
                    result['product_url_count'] = count
                    break
            except Exception:
                continue

    return result


def get_vendors_from_csv(csv_path: str, min_products: int = 0) -> list:
    """Read vendor names and counts from Shopify baseline CSV."""
    vendors = Counter()
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            v = row.get('vendor', '').strip()
            if v:
                vendors[v] += 1

    result = []
    for vendor, count in vendors.most_common():
        if count >= min_products:
            result.append({'vendor': vendor, 'product_count': count})

    return result


def main():
    parser = argparse.ArgumentParser(description='Discover supplier website URLs')
    parser.add_argument('--min-products', type=int, default=100,
                       help='Only check vendors with at least this many products (default: 100)')
    parser.add_argument('--output', '-o', default='supplier_urls.csv',
                       help='Output CSV path (default: supplier_urls.csv)')
    parser.add_argument('--baseline', default='shopify_baseline.csv',
                       help='Shopify baseline CSV path')

    args = parser.parse_args()

    baseline_path = os.path.join(REPO_ROOT, args.baseline)
    output_path = os.path.join(REPO_ROOT, args.output)

    if not os.path.exists(baseline_path):
        print(f"Error: {baseline_path} not found. Run export_shopify_products.py first.")
        sys.exit(1)

    print("="*70)
    print("  Discover Supplier URLs")
    print("="*70)

    # Get vendors
    vendors = get_vendors_from_csv(baseline_path, min_products=args.min_products)
    print(f"\nFound {len(vendors)} vendors with >= {args.min_products} products\n")

    results = []

    for i, v in enumerate(vendors, 1):
        vendor = v['vendor']
        count = v['product_count']
        candidates = guess_domains(vendor)

        if not candidates:
            print(f"[{i}/{len(vendors)}] {vendor:<35} ({count:>5}) SKIP (own brand)")
            results.append({
                'vendor_name': vendor,
                'website_url': '',
                'product_count': count,
                'reachable': False,
                'has_sitemap': False,
                'sitemap_url': '',
                'sitemap_product_urls': 0,
                'notes': 'own brand - skip',
            })
            continue

        print(f"[{i}/{len(vendors)}] {vendor:<35} ({count:>5}) checking {candidates[0]}...", end=' ', flush=True)

        found = False
        for domain in candidates:
            time.sleep(0.3)  # Be polite
            result = check_url(domain)

            if result['reachable']:
                sitemap_info = f"sitemap: {result['product_url_count']} product URLs" if result['has_sitemap'] else "no sitemap"
                print(f"OK -> {result['final_url']}  ({sitemap_info})")

                results.append({
                    'vendor_name': vendor,
                    'website_url': domain,
                    'product_count': count,
                    'reachable': True,
                    'has_sitemap': result['has_sitemap'],
                    'sitemap_url': result.get('sitemap_url', ''),
                    'sitemap_product_urls': result['product_url_count'],
                    'notes': '',
                })
                found = True
                break

        if not found:
            print(f"NOT FOUND (tried: {', '.join(candidates[:2])})")
            results.append({
                'vendor_name': vendor,
                'website_url': candidates[0],
                'product_count': count,
                'reachable': False,
                'has_sitemap': False,
                'sitemap_url': '',
                'sitemap_product_urls': 0,
                'notes': 'URL not verified',
            })

    # Write results
    fieldnames = ['vendor_name', 'website_url', 'product_count', 'reachable',
                  'has_sitemap', 'sitemap_url', 'sitemap_product_urls', 'notes']

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    # Summary
    reachable = sum(1 for r in results if r['reachable'])
    with_sitemap = sum(1 for r in results if r['has_sitemap'])
    total_sitemap_urls = sum(r['sitemap_product_urls'] for r in results)
    skipped = sum(1 for r in results if r['notes'] == 'own brand - skip')

    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"Total vendors checked: {len(results)}")
    print(f"Reachable:            {reachable}")
    print(f"With sitemap:         {with_sitemap}")
    print(f"Product URLs found:   {total_sitemap_urls}")
    print(f"Skipped (own brand):  {skipped}")
    print(f"Not found:            {len(results) - reachable - skipped}")
    print(f"\nOutput: {output_path}")


if __name__ == "__main__":
    main()
