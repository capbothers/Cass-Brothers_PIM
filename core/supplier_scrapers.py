"""
Supplier-Specific Scraper Patterns

Extends the base SpecSheetScraper with supplier-specific logic
for finding spec sheet PDFs on product pages.
"""

from typing import Optional, Dict, Callable
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re


class SupplierScraperPatterns:
    """Supplier-specific patterns and selectors for spec sheet discovery"""

    # Supplier-specific patterns
    PATTERNS = {
        'abey.com.au': {
            'keywords': ['specification', 'spec sheet', 'datasheet', 'technical data', 'product data'],
            'selectors': [
                'a[href*="specification"]',
                'a[href*="spec"]',
                'a[href*="datasheet"]',
                '.product-downloads a',
                '.product-specifications a',
                '.downloads a',
            ],
            'exclude': ['catalogue', 'brochure', 'manual'],
        },
        'default': {
            'keywords': ['spec', 'specification', 'datasheet', 'technical', 'dimension'],
            'selectors': [
                'a[href$=".pdf"]',
                'a[href*="spec"]',
                'a[href*="datasheet"]',
            ],
            'exclude': ['catalog', 'brochure', 'warranty'],
        }
    }

    @classmethod
    def get_pattern(cls, supplier: str) -> Dict:
        """
        Get scraper pattern for supplier

        Args:
            supplier: Supplier domain (e.g., 'abey.com.au')

        Returns:
            Pattern dict with keywords, selectors, and exclusions
        """
        # Extract domain from URL if full URL provided
        if '://' in supplier:
            from urllib.parse import urlparse
            supplier = urlparse(supplier).netloc

        # Find matching pattern
        for key, pattern in cls.PATTERNS.items():
            if key in supplier.lower():
                return pattern

        return cls.PATTERNS['default']

    @classmethod
    def find_spec_sheet_for_supplier(cls, soup: BeautifulSoup, base_url: str, supplier: str) -> Optional[str]:
        """
        Find spec sheet using supplier-specific patterns

        Args:
            soup: BeautifulSoup object of product page
            base_url: Base URL for resolving relative links
            supplier: Supplier domain

        Returns:
            Spec sheet URL or None
        """
        pattern = cls.get_pattern(supplier)

        # Strategy 1: Try supplier-specific CSS selectors
        for selector in pattern['selectors']:
            links = soup.select(selector)
            for link in links:
                href = link.get('href', '')
                text = link.get_text().lower()

                # Must be PDF
                if not href.lower().endswith('.pdf') and 'pdf' not in href.lower():
                    continue

                # Check for spec sheet keywords
                if any(kw in text for kw in pattern['keywords']):
                    # Exclude unwanted documents
                    if not any(ex in text for ex in pattern['exclude']):
                        return urljoin(base_url, href)

                # Check href for spec sheet keywords
                if any(kw in href.lower() for kw in pattern['keywords']):
                    if not any(ex in href.lower() for ex in pattern['exclude']):
                        return urljoin(base_url, href)

        # Strategy 2: Generic PDF search with keyword scoring
        all_links = soup.find_all('a', href=True)
        candidates = []

        for link in all_links:
            href = link['href'].lower()
            text = link.get_text().lower()

            # Must be PDF
            if not href.endswith('.pdf') and 'pdf' not in href:
                continue

            # Score based on keywords
            score = 0
            for keyword in pattern['keywords']:
                if keyword in text or keyword in href:
                    score += 1

            # Penalize exclusions
            for exclude in pattern['exclude']:
                if exclude in text or exclude in href:
                    score -= 2

            if score > 0:
                candidates.append((score, urljoin(base_url, link['href'])))

        # Return highest scoring candidate
        if candidates:
            candidates.sort(reverse=True, key=lambda x: x[0])
            return candidates[0][1]

        return None


# Supplier-specific extraction functions
def scrape_abey_product(url: str) -> Optional[str]:
    """
    Abey-specific scraper

    Args:
        url: Product URL on abey.com.au

    Returns:
        Spec sheet URL or None
    """
    import requests

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # Abey-specific: Look for "Downloads" or "Specifications" section
        downloads_section = soup.find(class_=['downloads', 'product-downloads', 'specifications'])
        if downloads_section:
            pdf_links = downloads_section.find_all('a', href=re.compile(r'\.pdf$', re.I))
            for link in pdf_links:
                text = link.get_text().lower()
                if 'spec' in text or 'data' in text or 'dimension' in text:
                    return urljoin(url, link['href'])

        # Fallback to generic pattern
        return SupplierScraperPatterns.find_spec_sheet_for_supplier(soup, url, 'abey.com.au')

    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None


# Registry of supplier-specific scrapers
SUPPLIER_SCRAPERS: Dict[str, Callable] = {
    'abey.com.au': scrape_abey_product,
    # Add more suppliers as needed:
    # 'supplier2.com': scrape_supplier2_product,
}


def get_supplier_scraper(supplier: str) -> Optional[Callable]:
    """
    Get supplier-specific scraper function

    Args:
        supplier: Supplier domain

    Returns:
        Scraper function or None for generic scraper
    """
    for key, scraper in SUPPLIER_SCRAPERS.items():
        if key in supplier.lower():
            return scraper
    return None
