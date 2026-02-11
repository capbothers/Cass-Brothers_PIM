"""
Abey.com.au Website Crawler

Discovers all product pages, extracts SKUs, and outputs CSV for import pipeline.

Usage:
    python scripts/crawl_abey.py
    python scripts/crawl_abey.py --output abey_products.csv --limit 100
    python scripts/crawl_abey.py --start-url https://www.abey.com.au/products
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import csv
import time
import argparse
import json
import re
from typing import Set, List, Dict, Optional
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class AbeyCrawler:
    """Crawler for abey.com.au website"""

    def __init__(self, base_url: str = "https://www.abey.com.au",
                 rate_limit: float = 1.0,
                 user_agent: str = None):
        """
        Initialize crawler

        Args:
            base_url: Base URL of the website
            rate_limit: Seconds between requests (default: 1.0)
            user_agent: Custom user agent string
        """
        self.base_url = base_url
        self.rate_limit = rate_limit
        self.user_agent = user_agent or (
            'Mozilla/5.0 (compatible; CassBrothersPIM/1.0; +https://cassbrothers.com.au)'
        )

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })

        self.visited_urls: Set[str] = set()
        self.product_urls: Set[str] = set()
        self.products: List[Dict[str, str]] = []

        self.stats = {
            'pages_crawled': 0,
            'products_found': 0,
            'errors': 0,
            'skus_extracted': 0,
            'skus_failed': 0
        }

    def crawl(self, max_products: int = None, start_url: str = None) -> List[Dict[str, str]]:
        """
        Main crawl method

        Args:
            max_products: Stop after finding this many products
            start_url: Override starting URL

        Returns:
            List of product dicts with sku, supplier_name, product_url
        """
        logger.info(f"Starting crawl of {self.base_url}")
        logger.info(f"Rate limit: {self.rate_limit}s between requests")

        # Strategy 1: Try sitemap first
        sitemap_products = self._crawl_from_sitemap()
        if sitemap_products:
            logger.info(f"✅ Found {len(sitemap_products)} product URLs from sitemap")
            self.product_urls.update(sitemap_products)
        else:
            logger.info("⚠️  No sitemap found, will crawl category pages")

        # Strategy 2: Crawl category/product pages
        if not sitemap_products or len(sitemap_products) < 10:
            start = start_url or f"{self.base_url}/products"
            self._crawl_from_category(start, max_pages=50)

        logger.info(f"\n📊 Found {len(self.product_urls)} unique product URLs")

        # Extract SKUs from product pages
        logger.info("\n🔍 Extracting SKUs from product pages...")
        for i, product_url in enumerate(list(self.product_urls), 1):
            if max_products and i > max_products:
                break

            logger.info(f"[{i}/{len(self.product_urls)}] {product_url}")

            product_data = self._extract_product_data(product_url)
            if product_data:
                self.products.append(product_data)
                self.stats['skus_extracted'] += 1
            else:
                self.stats['skus_failed'] += 1

            # Rate limiting
            if i < len(self.product_urls):
                time.sleep(self.rate_limit)

        logger.info(f"\n✅ Crawl complete! Found {len(self.products)} products with SKUs")
        self._print_stats()

        return self.products

    def _crawl_from_sitemap(self) -> Set[str]:
        """Try to discover products from sitemap.xml"""
        sitemap_urls = [
            f"{self.base_url}/sitemap.xml",
            f"{self.base_url}/sitemap_products.xml",
            f"{self.base_url}/sitemap_index.xml",
        ]

        product_urls = set()

        for sitemap_url in sitemap_urls:
            try:
                logger.info(f"Checking {sitemap_url}...")
                response = self.session.get(sitemap_url, timeout=10)

                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'xml')

                    # Check for sitemap index
                    sitemaps = soup.find_all('sitemap')
                    if sitemaps:
                        for sitemap in sitemaps:
                            loc = sitemap.find('loc')
                            if loc and 'product' in loc.text:
                                sub_products = self._parse_sitemap(loc.text)
                                product_urls.update(sub_products)

                    # Check for direct URLs
                    urls = soup.find_all('url')
                    for url in urls:
                        loc = url.find('loc')
                        if loc and self._is_product_url(loc.text):
                            product_urls.add(loc.text)

                    if product_urls:
                        logger.info(f"✅ Found {len(product_urls)} product URLs in sitemap")
                        return product_urls

            except Exception as e:
                logger.debug(f"Could not fetch {sitemap_url}: {e}")

        return product_urls

    def _parse_sitemap(self, sitemap_url: str) -> Set[str]:
        """Parse a sitemap XML file"""
        try:
            response = self.session.get(sitemap_url, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'xml')
                urls = soup.find_all('url')

                product_urls = set()
                for url in urls:
                    loc = url.find('loc')
                    if loc and self._is_product_url(loc.text):
                        product_urls.add(loc.text)

                return product_urls
        except Exception as e:
            logger.debug(f"Error parsing sitemap {sitemap_url}: {e}")

        return set()

    def _crawl_from_category(self, start_url: str, max_pages: int = 50):
        """Crawl from category/listing pages to discover products"""
        to_visit = [start_url]
        pages_crawled = 0

        while to_visit and pages_crawled < max_pages:
            url = to_visit.pop(0)

            if url in self.visited_urls:
                continue

            try:
                logger.info(f"Crawling: {url}")
                response = self.session.get(url, timeout=15)
                response.raise_for_status()

                self.visited_urls.add(url)
                pages_crawled += 1

                soup = BeautifulSoup(response.content, 'html.parser')

                # Find product links
                product_links = self._find_product_links(soup, url)
                self.product_urls.update(product_links)

                # Find category/pagination links
                category_links = self._find_category_links(soup, url)
                for link in category_links:
                    if link not in self.visited_urls and link not in to_visit:
                        to_visit.append(link)

                # Rate limiting
                time.sleep(self.rate_limit)

            except Exception as e:
                logger.error(f"Error crawling {url}: {e}")
                self.stats['errors'] += 1

    def _is_product_url(self, url: str) -> bool:
        """Check if URL is likely a product page"""
        url_lower = url.lower()

        # Common product URL patterns
        product_patterns = [
            '/product/',
            '/products/',
            '/p/',
            '/item/',
        ]

        # Exclude patterns
        exclude_patterns = [
            '/category/',
            '/categories/',
            '/collection/',
            '/collections/',
            '/search',
            '/cart',
            '/checkout',
            '/account',
            '/blog',
            '/pages',
        ]

        # Check if it matches product patterns
        has_product_pattern = any(pattern in url_lower for pattern in product_patterns)

        # Check if it doesn't match exclude patterns
        not_excluded = not any(pattern in url_lower for pattern in exclude_patterns)

        return has_product_pattern and not_excluded

    def _find_product_links(self, soup: BeautifulSoup, base_url: str) -> Set[str]:
        """Find product links on a page"""
        product_links = set()

        # Strategy 1: Look for common product link patterns
        selectors = [
            'a[href*="/product/"]',
            'a[href*="/products/"]',
            '.product a',
            '.product-card a',
            '.product-item a',
            '[class*="product"] a',
        ]

        for selector in selectors:
            links = soup.select(selector)
            for link in links:
                href = link.get('href')
                if href:
                    full_url = urljoin(base_url, href)
                    if self._is_product_url(full_url):
                        product_links.add(full_url)

        return product_links

    def _find_category_links(self, soup: BeautifulSoup, base_url: str) -> Set[str]:
        """Find category/pagination links"""
        category_links = set()

        # Look for pagination
        pagination_selectors = [
            'a[href*="page="]',
            '.pagination a',
            '[class*="pagination"] a',
            'a[rel="next"]',
        ]

        for selector in pagination_selectors:
            links = soup.select(selector)
            for link in links:
                href = link.get('href')
                if href:
                    full_url = urljoin(base_url, href)
                    if self.base_url in full_url:
                        category_links.add(full_url)

        # Look for category links (limited to avoid over-crawling)
        category_selectors = [
            'a[href*="/category/"]',
            'a[href*="/collection/"]',
            '.category a',
        ]

        for selector in category_selectors:
            links = soup.select(selector)[:10]  # Limit to prevent explosion
            for link in links:
                href = link.get('href')
                if href:
                    full_url = urljoin(base_url, href)
                    if self.base_url in full_url:
                        category_links.add(full_url)

        return category_links

    def _extract_product_data(self, url: str) -> Optional[Dict[str, str]]:
        """
        Extract product data from a product page

        Returns:
            Dict with sku, supplier_name, product_url
        """
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Extract SKU
            sku = self._extract_sku(soup, url)

            if not sku:
                logger.warning(f"  ⚠️  Could not find SKU")
                return None

            logger.info(f"  ✅ Found SKU: {sku}")

            return {
                'sku': sku,
                'supplier_name': 'abey.com.au',
                'product_url': url
            }

        except Exception as e:
            logger.error(f"  ❌ Error extracting data: {e}")
            self.stats['errors'] += 1
            return None

    def _extract_sku(self, soup: BeautifulSoup, url: str) -> Optional[str]:
        """
        Extract SKU from product page

        Tries multiple strategies:
        1. Meta tags (product:sku, sku)
        2. JSON-LD structured data
        3. Common HTML patterns (SKU:, Product Code:, etc.)
        4. URL patterns
        5. Data attributes
        """
        # Strategy 1: Meta tags
        meta_patterns = [
            {'property': 'product:sku'},
            {'name': 'sku'},
            {'itemprop': 'sku'},
            {'property': 'og:product:sku'},
        ]

        for pattern in meta_patterns:
            meta = soup.find('meta', pattern)
            if meta and meta.get('content'):
                return self._clean_sku(meta['content'])

        # Strategy 2: JSON-LD
        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_ld_scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    sku = data.get('sku') or data.get('productID')
                    if sku:
                        return self._clean_sku(sku)
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            sku = item.get('sku') or item.get('productID')
                            if sku:
                                return self._clean_sku(sku)
            except:
                pass

        # Strategy 3: Common HTML patterns
        text_patterns = [
            r'SKU[:\s]+([A-Z0-9\-]+)',
            r'Product\s+Code[:\s]+([A-Z0-9\-]+)',
            r'Item\s+#[:\s]+([A-Z0-9\-]+)',
            r'Model[:\s]+([A-Z0-9\-]+)',
        ]

        page_text = soup.get_text()
        for pattern in text_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                return self._clean_sku(match.group(1))

        # Strategy 4: Data attributes
        sku_elements = soup.find_all(attrs={'data-sku': True})
        if sku_elements:
            return self._clean_sku(sku_elements[0]['data-sku'])

        # Strategy 5: Specific selectors
        selectors = [
            '[itemprop="sku"]',
            '.sku',
            '.product-sku',
            '#sku',
            '[class*="sku"]',
        ]

        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                text = elem.get_text().strip()
                # Remove label if present
                text = re.sub(r'^SKU[:\s]+', '', text, flags=re.IGNORECASE)
                if text:
                    return self._clean_sku(text)

        # Strategy 6: URL-based SKU (last resort)
        url_match = re.search(r'/([A-Z0-9\-]{4,})/?$', url, re.IGNORECASE)
        if url_match:
            return self._clean_sku(url_match.group(1))

        return None

    def _clean_sku(self, sku: str) -> str:
        """Clean and normalize SKU"""
        if not sku:
            return None

        # Remove common prefixes/labels
        sku = re.sub(r'^(SKU|Product Code|Item #)[:\s]+', '', sku, flags=re.IGNORECASE)

        # Strip whitespace
        sku = sku.strip()

        # Remove quotes
        sku = sku.strip('"\'')

        return sku if sku else None

    def _print_stats(self):
        """Print crawl statistics"""
        logger.info("\n" + "=" * 60)
        logger.info("CRAWL STATISTICS")
        logger.info("=" * 60)
        logger.info(f"Pages Crawled: {self.stats['pages_crawled']}")
        logger.info(f"Product URLs Found: {len(self.product_urls)}")
        logger.info(f"SKUs Extracted: {self.stats['skus_extracted']}")
        logger.info(f"SKUs Failed: {self.stats['skus_failed']}")
        logger.info(f"Errors: {self.stats['errors']}")

    def save_to_csv(self, filename: str):
        """Save products to CSV"""
        if not self.products:
            logger.warning("No products to save")
            return

        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['sku', 'supplier_name', 'product_url'])
            writer.writeheader()
            writer.writerows(self.products)

        logger.info(f"\n💾 Saved {len(self.products)} products to {filename}")


def main():
    parser = argparse.ArgumentParser(
        description='Crawl abey.com.au to discover products and extract SKUs'
    )
    parser.add_argument(
        '--output', '-o',
        default='abey_supplier_urls.csv',
        help='Output CSV file (default: abey_supplier_urls.csv)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Max products to crawl'
    )
    parser.add_argument(
        '--start-url',
        help='Override starting URL'
    )
    parser.add_argument(
        '--rate-limit',
        type=float,
        default=1.0,
        help='Seconds between requests (default: 1.0)'
    )

    args = parser.parse_args()

    print("╔════════════════════════════════════════════════════════════╗")
    print("║  Abey.com.au Product Crawler                              ║")
    print("╚════════════════════════════════════════════════════════════╝\n")

    crawler = AbeyCrawler(rate_limit=args.rate_limit)

    try:
        products = crawler.crawl(max_products=args.limit, start_url=args.start_url)

        if products:
            crawler.save_to_csv(args.output)

            print("\n📋 Next Steps:")
            print(f"1. Review {args.output}")
            print(f"2. Import to database:")
            print(f"   python -c \"from core.supplier_db import get_supplier_db; import csv;")
            print(f"   db = get_supplier_db();")
            print(f"   with open('{args.output}') as f:")
            print(f"       reader = csv.DictReader(f);")
            print(f"       db.import_from_csv(list(reader))\"")
            print(f"3. Run pilot:")
            print(f"   python scripts/run_pilot.py --supplier abey.com.au --limit 50")
        else:
            print("\n⚠️  No products found")

    except KeyboardInterrupt:
        print("\n\n⚠️  Crawl interrupted by user")
        if crawler.products:
            crawler.save_to_csv(args.output)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
