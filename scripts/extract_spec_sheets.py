#!/usr/bin/env python3
"""
Extract spec sheet PDF URLs from supplier product pages.

Scans supplier product pages for PDF links related to spec sheets,
technical data, and installation guides. Stores URLs in supplier_products.spec_sheet_url.

No LLM calls - just HTTP fetching and HTML parsing. Runs fast.

Usage:
    python scripts/extract_spec_sheets.py --limit 100
    python scripts/extract_spec_sheets.py --vendor "Nero Tapware"
    python scripts/extract_spec_sheets.py --dry-run
"""

import os
import sys
import re
import json
import time
import sqlite3
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

DB_PATH = 'supplier_products.db'

# Keywords that indicate a spec sheet PDF (ordered by specificity)
SPEC_KEYWORDS = [
    'spec sheet', 'specification sheet', 'spec_sheet', 'specsheet',
    'data sheet', 'datasheet', 'data_sheet',
    'technical data', 'technical specification', 'tech spec',
    'product specification', 'product data',
]

# Keywords for installation guides (separate metafield)
INSTALL_KEYWORDS = [
    'installation guide', 'install guide', 'installation instruction',
    'install instruction', 'fitting instruction', 'installation manual',
]

# Keywords for brochures (lower priority)
BROCHURE_KEYWORDS = [
    'brochure', 'catalogue', 'catalog', 'range brochure',
]

# Keywords to EXCLUDE (not spec sheets)
EXCLUDE_KEYWORDS = [
    'warranty', 'terms', 'privacy', 'cookie', 'sitemap',
    'returns', 'shipping', 'care and maintenance',
]


def classify_pdf_link(url: str, link_text: str, context: str = '') -> Optional[str]:
    """
    Classify a PDF link as spec_sheet, install_guide, brochure, or None.

    Returns the classification or None if not relevant.
    """
    combined = f"{url} {link_text} {context}".lower()

    # Exclude irrelevant PDFs
    for kw in EXCLUDE_KEYWORDS:
        if kw in combined:
            return None

    # Must be a PDF or look like a document link
    is_pdf = '.pdf' in url.lower()

    # Check spec sheet keywords first (highest priority)
    for kw in SPEC_KEYWORDS:
        if kw in combined:
            return 'spec_sheet'

    # Check installation guides
    for kw in INSTALL_KEYWORDS:
        if kw in combined:
            return 'install_guide'

    # Check brochures
    for kw in BROCHURE_KEYWORDS:
        if kw in combined:
            return 'brochure'

    # If it's a PDF on the product page, try to classify by filename
    if is_pdf:
        filename = url.split('/')[-1].lower()
        if any(kw in filename for kw in ['spec', 'datasheet', 'technical']):
            return 'spec_sheet'
        if any(kw in filename for kw in ['install', 'fitting', 'instruction', '_im']):
            return 'install_guide'
        if any(kw in filename for kw in ['brochure', 'catalogue', 'catalog']):
            return 'brochure'
        # Generic PDF on product page - likely a spec sheet
        return 'spec_sheet'

    return None


def extract_pdf_links(html: str, base_url: str) -> List[Dict]:
    """
    Extract all PDF and document links from HTML.

    Returns list of dicts with: url, text, classification
    """
    results = []
    seen_urls = set()

    # Pattern 1: <a> tags with href containing .pdf
    pdf_pattern = re.findall(
        r'<a[^>]*href=["\']([^"\']*\.pdf[^"\']*)["\'][^>]*>(.*?)</a>',
        html, re.IGNORECASE | re.DOTALL
    )
    for href, text in pdf_pattern:
        clean_text = re.sub(r'<[^>]+>', '', text).strip()
        full_url = urljoin(base_url, href)
        if full_url not in seen_urls:
            seen_urls.add(full_url)
            classification = classify_pdf_link(full_url, clean_text)
            if classification:
                results.append({
                    'url': full_url,
                    'text': clean_text[:100],
                    'classification': classification
                })

    # Pattern 2: <a> tags where link text mentions specs/downloads
    # This catches non-.pdf links like PHP download endpoints
    spec_text_pattern = re.findall(
        r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        html, re.IGNORECASE | re.DOTALL
    )
    for href, text in spec_text_pattern:
        clean_text = re.sub(r'<[^>]+>', '', text).strip()
        lower_text = clean_text.lower()
        if any(kw in lower_text for kw in ['spec sheet', 'specification sheet', 'data sheet', 'technical data']):
            full_url = urljoin(base_url, href)
            if full_url not in seen_urls:
                seen_urls.add(full_url)
                # Link text explicitly says spec sheet — classify directly
                results.append({
                    'url': full_url,
                    'text': clean_text[:100],
                    'classification': 'spec_sheet'
                })

    # Pattern 3: data attributes or JavaScript with PDF URLs
    data_pdf = re.findall(
        r'(?:data-href|data-url|data-src|data-file)[=:]["\']([^"\']*\.pdf[^"\']*)',
        html, re.IGNORECASE
    )
    for href in data_pdf:
        full_url = urljoin(base_url, href)
        if full_url not in seen_urls:
            seen_urls.add(full_url)
            classification = classify_pdf_link(full_url, '')
            if classification:
                results.append({
                    'url': full_url,
                    'text': '',
                    'classification': classification
                })

    return results


def fetch_page(url: str, timeout: int = 15) -> Optional[str]:
    """Fetch a page and return HTML content."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    try:
        r = requests.get(url, timeout=timeout, headers=headers, allow_redirects=True)
        if r.status_code == 200:
            return r.text
        return None
    except Exception:
        return None


def process_product(sku: str, product_url: str, supplier_name: str) -> Dict:
    """Process a single product page for spec sheet PDFs."""
    result = {
        'sku': sku,
        'supplier_name': supplier_name,
        'product_url': product_url,
        'spec_sheet_url': None,
        'install_guide_url': None,
        'brochure_url': None,
        'all_pdfs': [],
        'success': False,
        'error': None,
    }

    html = fetch_page(product_url)
    if html is None:
        result['error'] = 'fetch_failed'
        return result

    pdf_links = extract_pdf_links(html, product_url)
    result['all_pdfs'] = pdf_links
    result['success'] = True

    # Pick the best link for each classification
    for link in pdf_links:
        if link['classification'] == 'spec_sheet' and result['spec_sheet_url'] is None:
            result['spec_sheet_url'] = link['url']
        elif link['classification'] == 'install_guide' and result['install_guide_url'] is None:
            result['install_guide_url'] = link['url']
        elif link['classification'] == 'brochure' and result['brochure_url'] is None:
            result['brochure_url'] = link['url']

    return result


def get_products_to_scan(vendor: Optional[str] = None, limit: Optional[int] = None,
                          skip_existing: bool = True) -> List[Dict]:
    """Get products that need spec sheet scanning."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    query = """
        SELECT sup.sku, sup.product_url, sup.supplier_name, sup.spec_sheet_url
        FROM supplier_products sup
        JOIN shopify_products s ON s.sku = sup.sku
        WHERE s.status = 'active'
        AND sup.product_url IS NOT NULL
        AND sup.product_url != ''
    """

    params = []
    if skip_existing:
        query += " AND (sup.spec_sheet_url IS NULL OR sup.spec_sheet_url = '')"

    if vendor:
        query += " AND s.vendor = ?"
        params.append(vendor)

    query += " ORDER BY sup.supplier_name, sup.sku"

    if limit:
        query += f" LIMIT {limit}"

    cur.execute(query, params)
    products = [dict(row) for row in cur.fetchall()]
    conn.close()
    return products


def save_results(results: List[Dict], dry_run: bool = False):
    """Save extracted spec sheet URLs to database."""
    if dry_run:
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    updated = 0
    for r in results:
        if r['spec_sheet_url']:
            cur.execute("""
                UPDATE supplier_products
                SET spec_sheet_url = ?, updated_at = ?
                WHERE sku = ?
            """, (r['spec_sheet_url'], datetime.now().isoformat(), r['sku']))
            updated += 1

    conn.commit()
    conn.close()
    return updated


def main():
    parser = argparse.ArgumentParser(description='Extract spec sheet PDFs from supplier pages')
    parser.add_argument('--limit', type=int, help='Max products to scan')
    parser.add_argument('--vendor', help='Only scan specific vendor')
    parser.add_argument('--dry-run', action='store_true', help='Preview without saving')
    parser.add_argument('--workers', type=int, default=5, help='Concurrent workers (default: 5)')
    parser.add_argument('--rescan', action='store_true', help='Rescan products that already have spec sheets')
    args = parser.parse_args()

    print("=" * 70)
    print("SPEC SHEET PDF EXTRACTOR")
    print("=" * 70)

    if args.dry_run:
        print("\n  DRY RUN - no changes will be saved\n")

    # Get products to scan
    products = get_products_to_scan(
        vendor=args.vendor,
        limit=args.limit,
        skip_existing=not args.rescan
    )

    total = len(products)
    print(f"Products to scan: {total}")
    if args.vendor:
        print(f"Vendor filter: {args.vendor}")
    print()

    if total == 0:
        print("Nothing to scan.")
        return

    # Process with thread pool for concurrent fetching
    results = []
    found_count = 0
    error_count = 0
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(process_product, p['sku'], p['product_url'], p['supplier_name']): p
            for p in products
        }

        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            results.append(result)

            if result['spec_sheet_url']:
                found_count += 1
                status = "FOUND"
            elif result['error']:
                error_count += 1
                status = "ERROR"
            else:
                status = "none"

            # Progress every 50 products or when found
            if i % 50 == 0 or status == "FOUND":
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                print(f"  [{i}/{total}] {result['sku'][:25]:25s} [{result['supplier_name'][:15]:15s}] "
                      f"{status:5s} | Found: {found_count} | {rate:.1f}/sec")
                if status == "FOUND":
                    print(f"    -> {result['spec_sheet_url'][:70]}")

    # Save results
    elapsed = time.time() - start_time
    print(f"\n{'─' * 70}")
    print(f"Scan complete in {elapsed:.0f}s ({total/elapsed:.1f} products/sec)")
    print(f"  Spec sheets found: {found_count}")
    print(f"  Fetch errors:      {error_count}")
    print(f"  No PDFs:           {total - found_count - error_count}")

    if not args.dry_run:
        updated = save_results(results)
        print(f"\n  Saved {updated} spec sheet URLs to database")
    else:
        print(f"\n  DRY RUN - would save {found_count} spec sheet URLs")

    # Save detailed results to JSON
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_file = f'spec_sheet_results_{timestamp}.json'
    summary = {
        'total_scanned': total,
        'spec_sheets_found': found_count,
        'errors': error_count,
        'elapsed_seconds': round(elapsed, 1),
        'timestamp': datetime.now().isoformat(),
    }

    # Only save results with PDFs found (keep file small)
    found_results = [r for r in results if r['all_pdfs']]
    with open(results_file, 'w') as f:
        json.dump({'summary': summary, 'results': found_results}, f, indent=2)
    print(f"  Results saved to {results_file}")


if __name__ == '__main__':
    main()
