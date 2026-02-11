#!/usr/bin/env python3
"""
Verify and populate boolean capability metafields for filtered/boiling/chilled
water system products across all vendors (Billi, Zip, Puretec, Insinkerator, etc.)

Two-pass approach:
  Pass 1: Rule-based parsing from product titles + Shopify tags (free, fast)
  Pass 2: LLM verification for flagged/uncertain products (Claude Haiku)

Usage:
    python scripts/verify_billi_zip_capabilities.py [--dry-run] [--llm-verify]
"""

import os
import sys
import json
import time
import sqlite3
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================
# Tag parsing mappings for NEWZIPFilterSystem / ZIPFilterSystem
# ============================================================

FILTER_SYSTEM_MAPPINGS = {
    # NEWZIPFilterSystem values
    'All In One': {'is_boiling': 1, 'is_chilled': 1, 'is_sparkling': 1, 'is_filtered': 1, 'is_ambient': 1},
    'Boiling & Chilled': {'is_boiling': 1, 'is_chilled': 1, 'is_sparkling': 0, 'is_filtered': 1, 'is_ambient': 0},
    'Boiling / Chilled & Sparkling': {'is_boiling': 1, 'is_chilled': 1, 'is_sparkling': 1, 'is_filtered': 1, 'is_ambient': 0},
    'Boiling & Ambient': {'is_boiling': 1, 'is_chilled': 0, 'is_sparkling': 0, 'is_filtered': 1, 'is_ambient': 1},
    'Boiling / Ambient': {'is_boiling': 1, 'is_chilled': 0, 'is_sparkling': 0, 'is_filtered': 1, 'is_ambient': 1},
    'Chilled Only': {'is_boiling': 0, 'is_chilled': 1, 'is_sparkling': 0, 'is_filtered': 1, 'is_ambient': 0},
    'Chilled & Sparkling': {'is_boiling': 0, 'is_chilled': 1, 'is_sparkling': 1, 'is_filtered': 1, 'is_ambient': 0},
    'Chilled / Sparkling': {'is_boiling': 0, 'is_chilled': 1, 'is_sparkling': 1, 'is_filtered': 1, 'is_ambient': 0},
    'Ambient Only': {'is_boiling': 0, 'is_chilled': 0, 'is_sparkling': 0, 'is_filtered': 1, 'is_ambient': 1},
    # Insinkerator / Blanco specific NEWZipFilterSystem tags
    'Boiling Only': {'is_boiling': 1, 'is_chilled': 0, 'is_sparkling': 0, 'is_filtered': 1, 'is_ambient': 0},
    'Boiling / Hot & Cold': {'is_boiling': 1, 'is_chilled': 0, 'is_sparkling': 0, 'is_filtered': 1, 'is_ambient': 0},
    'Boiling / Chilled / Hot & Cold': {'is_boiling': 1, 'is_chilled': 1, 'is_sparkling': 0, 'is_filtered': 1, 'is_ambient': 0},
    'Boiling / Ambient / Hot & Cold': {'is_boiling': 1, 'is_chilled': 0, 'is_sparkling': 0, 'is_filtered': 1, 'is_ambient': 1},
    'Hot / Cold & Ambient': {'is_boiling': 0, 'is_chilled': 0, 'is_sparkling': 0, 'is_filtered': 1, 'is_ambient': 1},
    # Puretec specific
    'Chilled / Sparkling & Ambient': {'is_boiling': 0, 'is_chilled': 1, 'is_sparkling': 1, 'is_filtered': 1, 'is_ambient': 1},
    # ZIPFilterSystem values (older format)
    'All-In-One': {'is_boiling': 1, 'is_chilled': 1, 'is_sparkling': 1, 'is_filtered': 1, 'is_ambient': 1},
    'Boiling / Chilled / Sparkling': {'is_boiling': 1, 'is_chilled': 1, 'is_sparkling': 1, 'is_filtered': 1, 'is_ambient': 0},
    'Boiling / Chilled / Hot & Ambient': {'is_boiling': 1, 'is_chilled': 1, 'is_sparkling': 0, 'is_filtered': 1, 'is_ambient': 1},
    'Boiling / Chilled / Sparkling / Hot & Ambient': {'is_boiling': 1, 'is_chilled': 1, 'is_sparkling': 1, 'is_filtered': 1, 'is_ambient': 1},
    'Boiling / Ambient / Chilled': {'is_boiling': 1, 'is_chilled': 1, 'is_sparkling': 0, 'is_filtered': 1, 'is_ambient': 1},
    'Chilled / Sparkling / Ambient': {'is_boiling': 0, 'is_chilled': 1, 'is_sparkling': 1, 'is_filtered': 1, 'is_ambient': 1},
    'Boiling / Chilled': {'is_boiling': 1, 'is_chilled': 1, 'is_sparkling': 0, 'is_filtered': 1, 'is_ambient': 0},
}

# Tags that identify a product as part of the drinking water collection
DRINKING_WATER_TAGS = [
    'NEWZIPFilterSystem:', 'NEWZipFilterSystem:', 'ZIPFilterSystem:', 'ZIPELEMENT:',
    'Filtered Water Tap Products', 'DrinkingWaterCollection',
    'Type: Filtered Water Taps', 'Type: Water Filter Systems',
    'Boiling / Chilled / Sparkling Filter Systems',
    'Puretec Boiling Chilled Sparkling Collection',
    'Billi Boiling Chilled Sparkling Collection',
    'Zip Boiling Chilled Sparkling Collection',
]

# Title keywords that identify drinking water products
DRINKING_WATER_TITLE_KEYWORDS = [
    'boiling', 'chilled', 'sparkling', 'filtered water',
    'filter tap', 'filter faucet', 'filtered mixer',
    'filtered sink mixer', '3-way filtered',
    'purifier sink mixer', 'purifier tap',
    'instant boiling', 'instant hot water',
    'autoboil', 'hydroboil', 'econoboil', 'hydrotap',
    'chilltap', 'chill tap',
    'filtration system', 'filter system',
    'filterwall', 'sparq',
    'multitap', '3n1', '4n1',
    'steaming hot filtered', 'boiling filtered',
]

# Title keywords for accessory detection
ACCESSORY_KEYWORDS = [
    'replacement filter', 'replacement water filter', 'replacement cartridge',
    'co2 cylinder', 'co2 cartridge',
    'font kit', 'font incl', 'slimline font', 'hydrotap font',
    'dispenser riser', 'riser 70mm', 'riser 120mm',
    'installation', 'pre-filter kit',
    'stand alone', 'raised brushed', 'raised gun metal',
    # Insinkerator accessories (not water systems)
    'sinktop switch', 'sink flange', 'sink stopper', 'mounting gasket',
    'basketwaste', 'basket waste', 'button and tube', 'button kit',
    'food waste disposer', 'waste disposal', 'plastic stopper',
    'sink baffle', 'drain flange', 'square waste', 'chrome stopper',
    'extended sink flange',
    # Oliveri/Franke accessories
    'connection kit', 'filter connection',
    # Generic filter accessories
    'inline filter', 'inline water', 'highflow inline',
    'filter cartridge',
]


def parse_tags(tags_str: str) -> List[str]:
    """Parse comma-separated Shopify tags into list."""
    if not tags_str:
        return []
    return [t.strip() for t in tags_str.split(',') if t.strip()]


def has_drinking_water_tags(tags: List[str]) -> bool:
    """Check if product has any drinking water collection tags."""
    for tag in tags:
        for dw_tag in DRINKING_WATER_TAGS:
            if dw_tag in tag:
                return True
    return False


def has_drinking_water_title(title: str) -> bool:
    """Check if product title indicates a drinking water product."""
    t = title.lower()
    return any(kw in t for kw in DRINKING_WATER_TITLE_KEYWORDS)


def extract_filter_system_tag(tags: List[str]) -> Optional[str]:
    """Extract the NEWZIPFilterSystem or ZIPFilterSystem tag value."""
    # Prefer NEWZIPFilterSystem (newer, more reliable)
    for tag in tags:
        for prefix in ['NEWZIPFilterSystem:', 'NEWZipFilterSystem:']:
            if tag.startswith(prefix):
                return tag[len(prefix):].strip()
    # Fall back to ZIPFilterSystem
    for tag in tags:
        if tag.startswith('ZIPFilterSystem:'):
            return tag[len('ZIPFilterSystem:'):].strip()
    return None


def capabilities_from_title(title: str) -> Dict[str, Optional[int]]:
    """Extract capabilities from product title keywords."""
    t = title.lower()
    caps = {
        'is_boiling': None,
        'is_chilled': None,
        'is_sparkling': None,
        'is_filtered': None,
        'is_ambient': None,
    }

    # Boiling indicators
    if any(kw in t for kw in ['boiling', 'autoboil', 'hydroboil', 'econoboil',
                               'steaming hot', '3n1', '4n1']):
        caps['is_boiling'] = 1

    # Chilled indicators
    if any(kw in t for kw in ['chilled', 'chilltap', 'chill tap']):
        caps['is_chilled'] = 1

    # Sparkling indicators
    if 'sparkling' in t:
        caps['is_sparkling'] = 1

    # Filtered indicators
    if any(kw in t for kw in ['filtered', 'filter tap', 'filter system',
                               'filter faucet', 'filter mixer',
                               '3-way filtered', 'filtration',
                               'filterwall', 'sparq', 'purifier']):
        caps['is_filtered'] = 1

    # Ambient indicators
    if 'ambient' in t:
        caps['is_ambient'] = 1

    return caps


def is_accessory(title: str) -> bool:
    """Check if product is an accessory (not a water system)."""
    t = title.lower()
    # If it's a tap/mixer/system, it's not an accessory even if title mentions a cartridge
    if any(kw in t for kw in ['mixer', 'tap', 'faucet', 'water system']):
        return False
    return any(kw in t for kw in ACCESSORY_KEYWORDS)


def capabilities_from_tags(tags: List[str]) -> Dict[str, Optional[int]]:
    """Extract capabilities from structured tags."""
    system_value = extract_filter_system_tag(tags)
    if system_value and system_value in FILTER_SYSTEM_MAPPINGS:
        return dict(FILTER_SYSTEM_MAPPINGS[system_value])

    # Fallback: check ZIPELEMENT tags
    caps = {
        'is_boiling': None,
        'is_chilled': None,
        'is_sparkling': None,
        'is_filtered': None,
        'is_ambient': None,
    }
    for tag in tags:
        if tag == 'ZIPELEMENT:Chilled':
            caps['is_chilled'] = 1
        elif tag == 'ZIPELEMENT:Sparkling':
            caps['is_sparkling'] = 1
        elif tag == 'ZIPELEMENT:Boiling':
            caps['is_boiling'] = 1

    # If any ZIPELEMENT found, assume filtered
    if any(v == 1 for v in caps.values()):
        caps['is_filtered'] = 1

    return caps


def merge_capabilities(title_caps: Dict, tag_caps: Dict) -> Tuple[Dict[str, int], List[str]]:
    """
    Merge title-derived and tag-derived capabilities.
    Returns (merged_caps, issues).
    Title is treated as most reliable for explicit mentions.
    Tags (NEWZIPFilterSystem) provide structured data.
    """
    merged = {}
    issues = []

    for field in ['is_boiling', 'is_chilled', 'is_sparkling', 'is_filtered', 'is_ambient']:
        t_val = title_caps.get(field)
        tag_val = tag_caps.get(field)

        if t_val is not None and tag_val is not None:
            if t_val != tag_val:
                # Title says yes but tag says no (or vice versa)
                issues.append(f'{field}: title={t_val} vs tag={tag_val}')
                # Trust title for explicit positive mentions
                merged[field] = t_val if t_val == 1 else tag_val
            else:
                merged[field] = t_val
        elif tag_val is not None:
            # Tag has data, title doesn't mention it
            merged[field] = tag_val
        elif t_val is not None:
            # Title mentions it but no tag
            merged[field] = t_val
        else:
            # Neither source has data — leave as None (uncertain)
            merged[field] = None

    return merged, issues


class CapabilityVerifier:
    """Verify and populate capability booleans for drinking water products."""

    def __init__(self, dry_run: bool = False, llm_verify: bool = False):
        self.db_path = 'supplier_products.db'
        self.dry_run = dry_run
        self.llm_verify = llm_verify
        self.results = []
        self.stats = {
            'total': 0,
            'pass1_resolved': 0,
            'pass1_flagged': 0,
            'accessories': 0,
            'llm_verified': 0,
            'updated': 0,
        }

        if llm_verify:
            api_key = os.getenv('ANTHROPIC_API_KEY')
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY required for --llm-verify")
            from anthropic import Anthropic
            self.client = Anthropic(api_key=api_key)

    def get_products(self) -> List[Dict]:
        """Get all active products that are part of the drinking water collection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get all active products with raw_json to check tags
        cursor.execute("""
            SELECT
                s.id, s.sku, s.title, s.vendor, s.raw_json,
                s.is_boiling, s.is_chilled, s.is_sparkling,
                s.is_filtered, s.is_ambient,
                sup.product_url
            FROM shopify_products s
            LEFT JOIN supplier_products sup ON s.sku = sup.sku
            WHERE s.status = 'active'
            AND s.raw_json IS NOT NULL
            ORDER BY s.vendor, s.sku
        """)

        # Filter to only drinking water products
        products = []
        for row in cursor.fetchall():
            product = dict(row)
            tags = []
            try:
                raw = json.loads(product['raw_json'])
                tags = parse_tags(raw.get('tags', ''))
            except (json.JSONDecodeError, TypeError):
                pass

            if has_drinking_water_tags(tags) or has_drinking_water_title(product['title']):
                product['_tags'] = tags
                products.append(product)

        conn.close()
        return products

    def pass1_rule_based(self, products: List[Dict]) -> List[Dict]:
        """
        Pass 1: Rule-based parsing from title + tags.
        Returns list of results with capabilities and flags.
        """
        results = []

        for product in products:
            sku = product['sku']
            title = product['title']
            vendor = product['vendor']
            tags = product.get('_tags', [])

            result = {
                'id': product['id'],
                'sku': sku,
                'title': title,
                'vendor': vendor,
                'supplier_url': product.get('product_url'),
                'is_accessory': False,
                'source': 'pass1',
                'issues': [],
                'capabilities': {},
            }

            # Check if this is an accessory
            if is_accessory(title):
                result['is_accessory'] = True
                result['capabilities'] = {
                    'is_boiling': 0, 'is_chilled': 0, 'is_sparkling': 0,
                    'is_filtered': 0, 'is_ambient': 0,
                }
                result['confidence'] = 'high'
                self.stats['accessories'] += 1
                results.append(result)
                continue

            # Extract from both sources
            title_caps = capabilities_from_title(title)
            tag_caps = capabilities_from_tags(tags)

            # Merge
            merged, issues = merge_capabilities(title_caps, tag_caps)
            result['capabilities'] = merged
            result['issues'] = issues
            result['title_caps'] = title_caps
            result['tag_caps'] = tag_caps
            result['filter_system_tag'] = extract_filter_system_tag(tags)

            # If filtered but no boiling/chilled/sparkling, it's an ambient filtered tap
            if (merged.get('is_filtered') == 1 and
                    merged.get('is_boiling') in (0, None) and
                    merged.get('is_chilled') in (0, None) and
                    merged.get('is_sparkling') in (0, None) and
                    merged.get('is_ambient') is None):
                merged['is_ambient'] = 1

            # Determine confidence
            has_nulls = any(v is None for v in merged.values())
            has_issues = len(issues) > 0

            if has_issues:
                result['confidence'] = 'low'
                result['flag_reason'] = 'title/tag mismatch'
                self.stats['pass1_flagged'] += 1
            elif has_nulls:
                # Fill remaining nulls with 0 (assume capability not present if not mentioned)
                for field in merged:
                    if merged[field] is None:
                        merged[field] = 0
                result['confidence'] = 'medium'
                self.stats['pass1_resolved'] += 1
            else:
                result['confidence'] = 'high'
                self.stats['pass1_resolved'] += 1

            results.append(result)

        return results

    def pass2_llm_verify(self, results: List[Dict]) -> List[Dict]:
        """
        Pass 2: LLM verification for flagged products.
        Only runs if --llm-verify flag is set.
        """
        flagged = [r for r in results if r['confidence'] == 'low']
        if not flagged:
            print("  No products flagged for LLM verification")
            return results

        print(f"\n  LLM verifying {len(flagged)} flagged products...")

        import requests
        from bs4 import BeautifulSoup

        for i, result in enumerate(flagged, 1):
            print(f"  [{i}/{len(flagged)}] {result['sku']}: {result['title'][:60]}...")

            # Build context for LLM
            title = result['title']
            url = result.get('supplier_url', '')

            # Try to fetch supplier page for additional context
            page_content = ''
            if url:
                try:
                    resp = requests.get(url, timeout=10, headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    })
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.content, 'html.parser')
                        page_content = soup.get_text(separator='\n', strip=True)[:4000]
                except Exception:
                    pass

            prompt = f"""Determine the water capabilities of this product.
This is a filtered/boiling/chilled water system product from {result['vendor']}.

Product Title: {title}
Supplier URL: {url}

{f"Supplier Page Content:{chr(10)}{page_content}" if page_content else "No supplier page content available."}

For each capability, return true if this product provides that type of water, false if it does not.
If this is an accessory (filter, CO2 cylinder, riser, font/dispenser kit, sink flange, waste disposer), all should be false.

Return ONLY valid JSON:
{{
    "is_boiling": true/false,
    "is_chilled": true/false,
    "is_sparkling": true/false,
    "is_filtered": true/false,
    "is_ambient": true/false
}}"""

            try:
                message = self.client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=200,
                    messages=[{"role": "user", "content": prompt}]
                )

                response_text = message.content[0].text.strip()
                # Extract JSON
                if '```json' in response_text:
                    response_text = response_text.split('```json')[1].split('```')[0].strip()
                elif '```' in response_text:
                    response_text = response_text.split('```')[1].split('```')[0].strip()
                else:
                    first_brace = response_text.find('{')
                    last_brace = response_text.rfind('}')
                    if first_brace >= 0 and last_brace > first_brace:
                        response_text = response_text[first_brace:last_brace + 1]

                llm_caps = json.loads(response_text)

                # Convert to 0/1
                result['capabilities'] = {
                    k: 1 if v else 0
                    for k, v in llm_caps.items()
                    if k in ('is_boiling', 'is_chilled', 'is_sparkling', 'is_filtered', 'is_ambient')
                }
                result['source'] = 'llm'
                result['confidence'] = 'high'
                self.stats['llm_verified'] += 1

                print(f"    LLM: {result['capabilities']}")

            except Exception as e:
                print(f"    LLM error: {e}")
                # Fall back to filling nulls with 0
                for field in result['capabilities']:
                    if result['capabilities'][field] is None:
                        result['capabilities'][field] = 0
                result['confidence'] = 'medium'

            time.sleep(0.5)

        return results

    def update_database(self, results: List[Dict]):
        """Write verified capabilities to the database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        updated = 0
        for result in results:
            caps = result['capabilities']
            # Skip if still has None values
            if any(v is None for v in caps.values()):
                continue

            if self.dry_run:
                continue

            cursor.execute("""
                UPDATE shopify_products
                SET is_boiling = ?, is_chilled = ?, is_sparkling = ?,
                    is_filtered = ?, is_ambient = ?
                WHERE id = ?
            """, (
                caps.get('is_boiling', 0),
                caps.get('is_chilled', 0),
                caps.get('is_sparkling', 0),
                caps.get('is_filtered', 0),
                caps.get('is_ambient', 0),
                result['id'],
            ))
            updated += 1

        if not self.dry_run:
            conn.commit()
        conn.close()

        self.stats['updated'] = updated

    def print_summary(self, results: List[Dict]):
        """Print a detailed summary report."""
        print("\n" + "=" * 80)
        print("DRINKING WATER CAPABILITY VERIFICATION REPORT")
        print("=" * 80)

        if self.dry_run:
            print("\n  [DRY RUN - no database changes made]\n")

        print(f"\nTotal products: {self.stats['total']}")
        print(f"  Accessories (caps all false): {self.stats['accessories']}")
        print(f"  Pass 1 resolved: {self.stats['pass1_resolved']}")
        print(f"  Pass 1 flagged: {self.stats['pass1_flagged']}")
        if self.llm_verify:
            print(f"  LLM verified: {self.stats['llm_verified']}")
        print(f"  Database updated: {self.stats['updated']}")

        # Capability breakdown
        cap_counts = {
            'is_boiling': 0, 'is_chilled': 0, 'is_sparkling': 0,
            'is_filtered': 0, 'is_ambient': 0,
        }
        for r in results:
            for field, val in r['capabilities'].items():
                if val == 1:
                    cap_counts[field] += 1

        print(f"\nCapability totals:")
        for field, count in cap_counts.items():
            print(f"  {field}: {count}")

        # Per-vendor breakdown
        vendors = sorted(set(r['vendor'] for r in results))
        for vendor in vendors:
            vendor_results = [r for r in results if r['vendor'] == vendor]
            print(f"\n--- {vendor} ({len(vendor_results)} products) ---")

            v_caps = {f: 0 for f in cap_counts}
            v_accessories = 0
            for r in vendor_results:
                if r['is_accessory']:
                    v_accessories += 1
                for field, val in r['capabilities'].items():
                    if val == 1:
                        v_caps[field] += 1

            print(f"  Accessories: {v_accessories}")
            for field, count in v_caps.items():
                if count > 0:
                    print(f"  {field}: {count}")

        # Show any still-flagged products
        still_flagged = [r for r in results if r['confidence'] == 'low']
        if still_flagged:
            print(f"\nStill flagged ({len(still_flagged)} products - run with --llm-verify to resolve):")
            for r in still_flagged:
                print(f"  {r['sku']} ({r['vendor']}): {r['title'][:65]}")
                print(f"    Issues: {r['issues']}")
                print(f"    Title caps: {r.get('title_caps', {})}")
                print(f"    Tag caps: {r.get('tag_caps', {})}")
                print()

        # Sample spot-checks
        print("\nSpot-checks:")
        spot_checks = [
            ('B5000', 'Should be boiling+chilled+sparkling+filtered'),
            ('B1000', 'Should be filtered only (ambient)'),
            ('Autoboil', 'Should be boiling+filtered'),
            ('CO2', 'Should be all false (accessory)'),
            ('GN1100', 'Insinkerator: boiling+filtered'),
            ('4N1 Boiling, Chilled', 'Insinkerator: boiling+chilled+filtered'),
            ('SPARQ', 'Puretec: chilled+sparkling+filtered+ambient'),
            ('FilterWall', 'Puretec: filtered only'),
            ('3-Way Filtered', 'Filtered ambient tap'),
            ('Food Waste', 'Should be all false (accessory)'),
        ]
        for keyword, expected in spot_checks:
            matches = [r for r in results if keyword.lower() in r['title'].lower()]
            if matches:
                r = matches[0]
                caps_str = ', '.join(f'{k}={v}' for k, v in r['capabilities'].items() if v == 1)
                print(f"  {r['title'][:60]}")
                print(f"    Got: {caps_str or '(none)'}")
                print(f"    Expected: {expected}")

        print("\n" + "=" * 80)

    def save_results(self, results: List[Dict]):
        """Save results JSON for audit."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'billi_zip_verification_{timestamp}.json'

        # Clean results for JSON serialization (remove raw_json and _tags from output)
        clean_results = []
        for r in results:
            clean = {k: v for k, v in r.items() if k not in ('raw_json', '_tags')}
            clean_results.append(clean)

        with open(filename, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'dry_run': self.dry_run,
                'llm_verify': self.llm_verify,
                'stats': self.stats,
                'results': clean_results,
            }, f, indent=2)

        print(f"\nResults saved to: {filename}")

    def run(self):
        """Run the full verification pipeline."""
        print("=" * 80)
        print("DRINKING WATER CAPABILITY VERIFICATION")
        if self.dry_run:
            print("  MODE: Dry run (no database changes)")
        if self.llm_verify:
            print("  MODE: LLM verification enabled for flagged products")
        print("=" * 80)

        # Get products
        products = self.get_products()
        self.stats['total'] = len(products)

        # Show vendor breakdown
        from collections import Counter
        vendor_counts = Counter(p['vendor'] for p in products)
        print(f"\nFound {len(products)} drinking water products:")
        for vendor, count in vendor_counts.most_common():
            print(f"  {vendor}: {count}")

        # Pass 1: Rule-based
        print("\n--- Pass 1: Title + Tag Parsing ---")
        results = self.pass1_rule_based(products)
        print(f"  Resolved: {self.stats['pass1_resolved']}")
        print(f"  Accessories: {self.stats['accessories']}")
        print(f"  Flagged for review: {self.stats['pass1_flagged']}")

        # Pass 2: LLM verification (optional)
        if self.llm_verify:
            print("\n--- Pass 2: LLM Verification ---")
            results = self.pass2_llm_verify(results)

        # Update database
        print("\n--- Updating Database ---")
        self.update_database(results)

        # Report
        self.print_summary(results)
        self.save_results(results)

        self.results = results


def main():
    parser = argparse.ArgumentParser(
        description='Verify drinking water product capabilities (Billi, Zip, Puretec, Insinkerator, etc.)'
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview without making database changes')
    parser.add_argument('--llm-verify', action='store_true',
                        help='Use Claude Haiku to verify flagged products')

    args = parser.parse_args()

    verifier = CapabilityVerifier(
        dry_run=args.dry_run,
        llm_verify=args.llm_verify,
    )
    verifier.run()


if __name__ == '__main__':
    main()
