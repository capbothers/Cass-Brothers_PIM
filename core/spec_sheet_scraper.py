"""
Spec Sheet Discovery Scraper
Finds PDF spec sheet URLs on supplier product pages
"""

import requests
from bs4 import BeautifulSoup
from typing import Optional, List, Dict, Any
import logging
import re
from urllib.parse import urljoin, urlparse
import time

logger = logging.getLogger(__name__)


class SpecSheetScraper:
    """Discover spec sheet PDFs on supplier product pages"""

    # Keywords that indicate a spec sheet link
    SPEC_SHEET_KEYWORDS = [
        'spec', 'specification', 'datasheet', 'data sheet',
        'technical', 'dimension', 'installation', 'guide',
        'manual', 'brochure', 'pdf'
    ]

    # Keywords to EXCLUDE (catalogs, general docs, etc.)
    EXCLUDE_KEYWORDS = [
        'catalog', 'catalogue', 'brochure', 'warranty',
        'care-guide', 'general', 'overview', 'all-products'
    ]

    def __init__(self, timeout: int = 15, user_agent: str = None):
        """
        Initialize spec sheet scraper

        Args:
            timeout: Request timeout in seconds
            user_agent: Custom user agent string
        """
        self.timeout = timeout
        self.user_agent = user_agent or (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': self.user_agent})

    def find_spec_sheet_url(self, product_url: str, supplier_hint: str = None) -> Optional[str]:
        """
        Find spec sheet PDF URL on a product page

        Args:
            product_url: URL of the supplier product page
            supplier_hint: Optional supplier domain hint for specific patterns (e.g., 'abey.com.au')

        Returns:
            URL of the spec sheet PDF, or None if not found
        """
        try:
            logger.info(f"Searching for spec sheet on: {product_url}")

            # Fetch the page
            response = self.session.get(product_url, timeout=self.timeout)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Try supplier-specific patterns first
            if supplier_hint:
                pdf_link = self._find_supplier_specific(soup, product_url, supplier_hint)
                if pdf_link:
                    logger.info(f"✅ Found spec sheet via supplier pattern: {pdf_link}")
                    return pdf_link

            # Strategy 1: Find PDF links with spec sheet keywords in text
            pdf_link = self._find_by_link_text(soup, product_url)
            if pdf_link:
                logger.info(f"✅ Found spec sheet via link text: {pdf_link}")
                return pdf_link

            # Strategy 2: Find PDF links with spec sheet keywords in href
            pdf_link = self._find_by_href_keywords(soup, product_url)
            if pdf_link:
                logger.info(f"✅ Found spec sheet via href keywords: {pdf_link}")
                return pdf_link

            # Strategy 3: Find data attributes pointing to PDFs
            pdf_link = self._find_by_data_attributes(soup, product_url)
            if pdf_link:
                logger.info(f"✅ Found spec sheet via data attributes: {pdf_link}")
                return pdf_link

            # Strategy 4: Search for embedded PDFs or iframes
            pdf_link = self._find_embedded_pdf(soup, product_url)
            if pdf_link:
                logger.info(f"✅ Found spec sheet via embedded PDF: {pdf_link}")
                return pdf_link

            logger.info(f"⚠️  No spec sheet found on {product_url}")
            return None

        except requests.exceptions.Timeout:
            logger.warning(f"Timeout fetching {product_url}")
            return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"Error fetching {product_url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error scraping {product_url}: {e}")
            return None

    def _find_by_link_text(self, soup: BeautifulSoup, base_url: str) -> Optional[str]:
        """Find PDF links by examining link text for keywords"""
        for link in soup.find_all('a', href=True):
            text = link.get_text().lower().strip()
            href = link['href'].lower()

            # Must be a PDF link
            if not href.endswith('.pdf') and 'pdf' not in href:
                continue

            # Check if link text contains spec sheet keywords
            if any(keyword in text for keyword in self.SPEC_SHEET_KEYWORDS):
                # Exclude unwanted documents
                if not any(exclude in text for exclude in self.EXCLUDE_KEYWORDS):
                    return urljoin(base_url, link['href'])

        return None

    def _find_by_href_keywords(self, soup: BeautifulSoup, base_url: str) -> Optional[str]:
        """Find PDF links by examining href for spec sheet keywords"""
        candidates = []

        for link in soup.find_all('a', href=True):
            href = link['href'].lower()

            # Must be a PDF
            if not href.endswith('.pdf') and 'pdf' not in href:
                continue

            # Score based on keyword matches
            score = 0
            for keyword in self.SPEC_SHEET_KEYWORDS:
                if keyword in href:
                    score += 1

            # Penalize excluded keywords
            for keyword in self.EXCLUDE_KEYWORDS:
                if keyword in href:
                    score -= 2

            if score > 0:
                candidates.append((score, urljoin(base_url, link['href'])))

        # Return highest scoring candidate
        if candidates:
            candidates.sort(reverse=True, key=lambda x: x[0])
            return candidates[0][1]

        return None

    def _find_by_data_attributes(self, soup: BeautifulSoup, base_url: str) -> Optional[str]:
        """Find PDFs in data attributes (data-pdf, data-spec, etc.)"""
        data_attrs = ['data-pdf', 'data-spec', 'data-datasheet', 'data-file', 'data-document']

        for attr in data_attrs:
            elements = soup.find_all(attrs={attr: True})
            for elem in elements:
                url = elem.get(attr, '')
                if url and '.pdf' in url.lower():
                    return urljoin(base_url, url)

        return None

    def _find_embedded_pdf(self, soup: BeautifulSoup, base_url: str) -> Optional[str]:
        """Find PDFs embedded in iframes or object tags"""
        # Check iframes
        for iframe in soup.find_all('iframe', src=True):
            src = iframe['src']
            if '.pdf' in src.lower():
                return urljoin(base_url, src)

        # Check object/embed tags
        for obj in soup.find_all(['object', 'embed'], attrs={'data': True}):
            data = obj.get('data', '')
            if '.pdf' in data.lower():
                return urljoin(base_url, data)

        return None

    def _find_supplier_specific(self, soup: BeautifulSoup, base_url: str, supplier: str) -> Optional[str]:
        """
        Try supplier-specific patterns for finding spec sheets

        Args:
            soup: BeautifulSoup object
            base_url: Base URL for resolving relative links
            supplier: Supplier hint (e.g., 'abey.com.au')

        Returns:
            Spec sheet URL or None
        """
        supplier_lower = supplier.lower()

        # Abey-specific patterns
        if 'abey' in supplier_lower:
            # Abey often has spec sheets in Downloads or Specifications sections
            selectors = [
                '.downloads a[href$=".pdf"]',
                '.specifications a[href$=".pdf"]',
                '.product-downloads a[href$=".pdf"]',
                'a[href*="specification"][href$=".pdf"]',
                'a[href*="/files/"][href$=".pdf"]',
            ]

            for selector in selectors:
                links = soup.select(selector)
                for link in links:
                    href = link.get('href', '')
                    text = link.get_text().lower()

                    # Check if it looks like a spec sheet
                    if any(kw in text or kw in href.lower() for kw in ['spec', 'data', 'dimension', 'technical']):
                        # Exclude unwanted docs
                        if not any(ex in text or ex in href.lower() for ex in self.EXCLUDE_KEYWORDS):
                            return urljoin(base_url, href)

        return None

    def batch_scrape(self, products: List[Dict[str, Any]], rate_limit: float = 1.0) -> Dict[str, Any]:
        """
        Scrape spec sheets for multiple products

        Args:
            products: List of product dicts with 'sku' and 'product_url' keys
            rate_limit: Seconds to wait between requests

        Returns:
            Dict with statistics and results
        """
        from .supplier_db import get_supplier_db

        db = get_supplier_db()
        results = {
            'total': len(products),
            'found': 0,
            'not_found': 0,
            'errors': 0,
            'found_skus': [],
            'not_found_skus': [],
            'error_skus': []
        }

        for i, product in enumerate(products):
            sku = product.get('sku')
            product_url = product.get('product_url')

            if not sku or not product_url:
                results['errors'] += 1
                continue

            logger.info(f"[{i+1}/{len(products)}] Scraping {sku}...")

            try:
                spec_sheet_url = self.find_spec_sheet_url(product_url)

                if spec_sheet_url:
                    # Update database
                    db.update_spec_sheet_url(sku, spec_sheet_url)
                    results['found'] += 1
                    results['found_skus'].append(sku)
                else:
                    # Still update timestamp to mark as scraped
                    db.update_spec_sheet_url(sku, '')
                    results['not_found'] += 1
                    results['not_found_skus'].append(sku)

            except Exception as e:
                logger.error(f"Error processing {sku}: {e}")
                results['errors'] += 1
                results['error_skus'].append(sku)

            # Rate limiting
            if i < len(products) - 1:
                time.sleep(rate_limit)

        logger.info(f"📊 Batch scrape complete: {results['found']} found, {results['not_found']} not found, {results['errors']} errors")
        return results


# Singleton instance
_scraper_instance = None


def get_spec_sheet_scraper() -> SpecSheetScraper:
    """Get singleton spec sheet scraper instance"""
    global _scraper_instance
    if _scraper_instance is None:
        _scraper_instance = SpecSheetScraper()
    return _scraper_instance
