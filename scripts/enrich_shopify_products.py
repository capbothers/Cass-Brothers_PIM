#!/usr/bin/env python3
"""
Production LLM Extraction Pipeline for Shopify Product Enrichment

Extracts specifications from supplier websites for Shopify products and updates the database.
Supports resumption, progress tracking, and detailed cost reporting.

Usage:
    python scripts/enrich_shopify_products.py [--limit N] [--resume]
"""

import os
import sys
import json
import time
import argparse
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from anthropic import Anthropic
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.data_validator import validate_metafield

# Super category mapping for 3-tier navigation (15 super categories)
SUPER_CATEGORY_MAP = {
    # Tapware
    "Basin Tapware": "Tapware",
    "Kitchen Tapware": "Tapware",
    "Bath Tapware": "Tapware",
    "Shower Tapware": "Tapware",

    # Core Bathroom
    "Basins": "Basins",
    "Toilets": "Toilets",
    "Bidets": "Toilets",
    "Urinals": "Toilets",
    "Smart Toilets": "Smart Toilets",
    "Baths": "Baths",

    # Sinks & Furniture
    "Kitchen Sinks": "Sinks",
    "Laundry Sinks": "Sinks",
    "Vanities": "Furniture",
    "Mirrors & Cabinets": "Furniture",

    # Showers
    "Showers": "Showers",
    "Shower Screens": "Showers",

    # Accessories
    "Bathroom Accessories": "Accessories",
    "Kitchen Accessories": "Accessories",

    # Specialty Systems
    "Boiling Water Taps": "Boiling, Chilled & Sparkling",
    "Chilled Water Taps": "Boiling, Chilled & Sparkling",
    "Sparkling Water Taps": "Boiling, Chilled & Sparkling",
    "Filtered Water Systems": "Boiling, Chilled & Sparkling",

    # Appliances & Systems
    "Kitchen Appliances": "Appliances",
    "Laundry Appliances": "Appliances",
    "Hot Water Systems": "Hot Water Systems",
    "Continuous Flow": "Hot Water Systems",
    "Storage Water Heaters": "Hot Water Systems",
    "Heat Pumps": "Hot Water Systems",

    # Climate Control
    "Air Conditioning": "Heating & Cooling",
    "Heaters": "Heating & Cooling",
    "Underfloor Heating": "Heating & Cooling",
    "Ventilation": "Heating & Cooling",

    # Outdoor & Hardware
    "Outdoor Products": "Hardware & Outdoor",
    "Skylights": "Hardware & Outdoor",
    "Drainage": "Hardware & Outdoor",

    # Accessibility
    "Assisted Living": "Assisted Living",
    "Aged Care": "Assisted Living",

    # Fallback mappings (when LLM extracts simplified category names)
    "Accessories": "Accessories",
    "Sinks": "Sinks",
    "Tapware": "Tapware",
    "Furniture": "Furniture",
    "Appliances": "Appliances"
}


class ShopifyEnrichmentPipeline:
    """Production pipeline for enriching Shopify products with LLM extraction"""

    def __init__(self, api_key: Optional[str] = None, resume: bool = False):
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY required")

        self.client = Anthropic(api_key=self.api_key)
        self.db_path = 'supplier_products.db'
        self.resume = resume

        # Progress tracking
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.checkpoint_file = f'enrichment_checkpoint_{self.session_id}.json'
        self.results_file = f'enrichment_results_{self.session_id}.json'

        # Stats
        self.total_cost = 0.0
        self.processed_count = 0
        self.success_count = 0
        self.failed_count = 0
        self.skipped_count = 0
        self.results = []

        # Pricing (per million tokens)
        self.input_price = 0.25  # Haiku input
        self.output_price = 1.25  # Haiku output

        # Load checkpoint if resuming
        if self.resume:
            self._load_checkpoint()

    def _load_checkpoint(self):
        """Load progress from previous run"""
        checkpoint_files = sorted(Path('.').glob('enrichment_checkpoint_*.json'), reverse=True)
        if checkpoint_files:
            with open(checkpoint_files[0], 'r') as f:
                checkpoint = json.load(f)
                self.processed_count = checkpoint.get('processed_count', 0)
                self.success_count = checkpoint.get('success_count', 0)
                self.failed_count = checkpoint.get('failed_count', 0)
                self.total_cost = checkpoint.get('total_cost', 0.0)
                self.session_id = checkpoint.get('session_id', self.session_id)
                print(f"✓ Resuming from checkpoint: {self.processed_count} products processed")

    def _save_checkpoint(self):
        """Save progress checkpoint"""
        checkpoint = {
            'session_id': self.session_id,
            'processed_count': self.processed_count,
            'success_count': self.success_count,
            'failed_count': self.failed_count,
            'skipped_count': self.skipped_count,
            'total_cost': self.total_cost,
            'timestamp': datetime.now().isoformat()
        }
        with open(self.checkpoint_file, 'w') as f:
            json.dump(checkpoint, f, indent=2)

    def get_products_to_enrich(self, limit: Optional[int] = None,
                               force_specs: bool = False) -> List[Dict]:
        """
        Get Shopify products that need enrichment (have supplier URLs but missing specs)

        Args:
            limit: Max number of products to return
            force_specs: If True, also include products that have categories but no specs
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if force_specs:
            # Re-enrich products that have categories but no spec data
            query = """
            SELECT
                s.id as shopify_id,
                s.sku,
                s.title,
                sp.product_url as supplier_url,
                sp.supplier_name
            FROM shopify_products s
            INNER JOIN supplier_products sp ON s.sku = sp.sku
            WHERE sp.product_url IS NOT NULL
            AND sp.product_url != ''
            AND s.status = 'active'
            AND s.material IS NULL
            AND s.overall_width_mm IS NULL
            ORDER BY s.id
            """
        else:
            query = """
            SELECT
                s.id as shopify_id,
                s.sku,
                s.title,
                sp.product_url as supplier_url,
                sp.supplier_name
            FROM shopify_products s
            INNER JOIN supplier_products sp ON s.sku = sp.sku
            WHERE sp.product_url IS NOT NULL
            AND sp.product_url != ''
            AND s.status = 'active'
            AND (s.primary_category IS NULL OR s.enriched_confidence < 0.5)
            ORDER BY s.id
            """

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query)
        products = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return products

    @staticmethod
    def _extract_json_text(text: str) -> str:
        """Extract JSON from LLM response text, handling code fences and preamble text"""
        # Try markdown code fences first
        if '```json' in text:
            return text.split('```json')[1].split('```')[0].strip()
        elif '```' in text:
            return text.split('```')[1].split('```')[0].strip()
        # Fall back to finding JSON by brackets
        first_brace = text.find('{')
        if first_brace > 0:
            # There's text before the JSON - extract from first { to last }
            last_brace = text.rfind('}')
            if last_brace > first_brace:
                return text[first_brace:last_brace + 1]
        return text

    def extract_with_llm(self, url: str, product_title: str) -> Tuple[Dict, float]:
        """
        Extract raw specifications from supplier webpage
        Returns: (extracted_specs, cost)
        """
        try:
            # Fetch webpage
            response = requests.get(url, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Extract relevant content
            meta_desc = soup.find('meta', property='og:description')
            meta_content = meta_desc.get('content', '') if meta_desc else ''

            # Find product-specific content
            product_div = soup.find(['div', 'section'], class_=lambda x: x and any(
                term in str(x).lower() for term in ['product', 'woocommerce', 'entry-content', 'item']
            ))

            if product_div:
                content = f"Product Title: {product_title}\n\nMeta Description: {meta_content}\n\n"
                content += product_div.get_text(separator='\n', strip=True)[:8000]
            else:
                content = f"Product Title: {product_title}\n\nMeta Description: {meta_content}\n\n"
                content += soup.get_text(separator='\n', strip=True)[:8000]

            # Extraction prompt
            prompt = """Extract ALL product information and specifications from this webpage. Focus on:

            CATEGORY INFORMATION:
            - Product category (Basin, Toilet, Tap/Mixer, Sink, Bath, Shower, Vanity, Accessory)
            - Subcategory (Wall Hung, Floor Mounted, Bench Mount, Countertop, etc.)
            - Collection/Range name (e.g., Alfresco, Urbane, Edwardian)

            SPECIFICATIONS:
            - Dimensions (width, depth, height, diameter in mm)
            - Material (ceramic, porcelain, stainless steel, brass, etc.)
            - Color/Finish (white, chrome, matte black, etc.)
            - Weight
            - Warranty
            - Technical specs (tap hole size, flow rate, water pressure, etc.)
            - Installation/mounting type (wall mounted, floor standing, etc.)
            - Standards/certifications (WELS, Watermark, etc.)

            Return ONLY valid JSON:
            {
                "product_category": "Basin|Toilet|Tap|Sink|Bath|Shower|Vanity|Accessory",
                "subcategory": "Wall Hung|Floor Mounted|...",
                "collection_name": "range or collection name",
                "width_mm": "value",
                "depth_mm": "value",
                "material": "value",
                "colour_finish": "value",
                ...
            }

            Return {} if no specs found or if this is a category/listing page."""

            # Call Claude API
            message = self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=2000,
                messages=[{
                    "role": "user",
                    "content": f"{prompt}\n\nWebpage Content:\n{content}"
                }]
            )

            # Calculate cost
            input_tokens = message.usage.input_tokens
            output_tokens = message.usage.output_tokens
            cost = (input_tokens / 1_000_000 * self.input_price +
                   output_tokens / 1_000_000 * self.output_price)

            # Parse response
            response_text = message.content[0].text.strip()
            response_text = self._extract_json_text(response_text)
            extracted = json.loads(response_text)

            return extracted, cost

        except json.JSONDecodeError as e:
            return {'error': f'JSON parse error: {str(e)}'}, 0.0
        except requests.RequestException as e:
            return {'error': f'Request failed: {str(e)}'}, 0.0
        except Exception as e:
            return {'error': f'Extraction failed: {str(e)}'}, 0.0

    def standardize_with_llm(self, raw_specs: Dict, supplier: str, title: str = '', supplier_url: str = '') -> Tuple[Dict, float]:
        """
        Standardize raw specs to metafield schema
        Returns: (standardized_specs, cost)
        """
        if 'error' in raw_specs or not raw_specs:
            return {}, 0.0

        try:
            prompt = f"""Given raw product specifications from {supplier}, standardize them to match our metafield schema.

PRODUCT TITLE: {title}
PRODUCT URL: {supplier_url}

CATEGORY MAPPING (Consolidated Structure):
Map product_category to ONE of these primary categories:
- Basin Tapware: basin mixers, basin taps, basin wall mixers, bench mount basin mixers
- Kitchen Tapware: kitchen mixers, sink mixers, pull-out mixers, filtered water taps
- Bath Tapware: bath mixers, bath wall mixers, bath spouts, bath fillers
- Shower Tapware: shower mixers, wall mixers, diverters
- Basins: basins, countertop basins, wall hung basins, undermount basins
- Kitchen Sinks: kitchen sinks, topmount sinks, undermount sinks
- Laundry Sinks: laundry sinks, laundry troughs, laundry tubs
- Toilets: toilets, in-wall toilets, wall hung toilets, floor mounted toilets
- Baths: baths, freestanding baths, built-in baths
- Showers: shower heads, hand showers, shower rails
- Vanities: wall hung vanities, freestanding vanities
- Bathroom Accessories: towel rails, towel rings, mirrors, magnifying mirrors, toilet roll holders, shelves, soap dispensers, robe hooks, exhaust fans, ventilation
- Kitchen Accessories: cutting boards, drainer trays, sink strainers, colanders, sink caddies

CRITICAL CLASSIFICATION RULES:
1. If the product title or URL contains "kitchen" or "sink mixer", use "Kitchen Tapware" NOT "Basin Tapware".
2. If the product title or URL contains "laundry", use "Laundry Sinks" for sinks or appropriate laundry category.
3. Mirrors, magnifying mirrors, exhaust fans = "Bathroom Accessories", NEVER "Kitchen Accessories".
4. Kitchen Accessories are ONLY items used with kitchen sinks: cutting boards, drainer trays, strainers, colanders, sink caddies.
5. For accessories, put the specific type (Towel Rail, Mirror, Cutting Board, etc.) in product_category_type.

Target Schema Fields:
- primary_category: string (one of the above categories)
- product_category_type: string (subcategory like "Wall Hung", "Bench Mount", etc.)
- collection_name: string (product range/collection name)
- overall_width_mm: integer (10-5000)
- overall_depth_mm: integer (10-3000)
- overall_height_mm: integer (10-3000)
- material: string (ceramic, porcelain, vitreous china, stainless steel, brass, copper, chrome, acrylic, stone, wood, glass, composite)
- colour_finish: string (keep finish descriptors like Gloss, Matte, Brushed, Polished)
- warranty_years: integer (1-25)
- weight_kg: decimal (0.1-500.0)
- tap_hole_size_mm: integer (0-50, use 0 for "no tap hole")
- installation_type: string (wall mounted, floor standing, countertop, inset, undermount, semi-recessed)
- flow_rate_lpm: decimal (liters per minute)
- water_pressure_min_kpa: integer
- water_pressure_max_kpa: integer

Rules:
1. Convert all measurements to numeric values (remove units)
2. Standardize material names (e.g., "Vitreous China" → "vitreous china")
3. Map to consolidated primary_category
4. Keep color/finish descriptive (e.g., "Matte Black", "Polished Chrome")
5. Extract warranty as integer years
6. Only include fields where you have confident data

Return ONLY valid JSON:
{{
    "primary_category": "Basin Tapware",
    "product_category_type": "Bench Mount",
    "collection_name": "Alfresco",
    "overall_width_mm": 600,
    "material": "ceramic",
    ...
}}"""

            message = self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1500,
                messages=[{
                    "role": "user",
                    "content": f"{prompt}\n\nRaw Specifications:\n{json.dumps(raw_specs, indent=2)}"
                }]
            )

            # Calculate cost
            input_tokens = message.usage.input_tokens
            output_tokens = message.usage.output_tokens
            cost = (input_tokens / 1_000_000 * self.input_price +
                   output_tokens / 1_000_000 * self.output_price)

            # Parse response
            response_text = message.content[0].text.strip()
            response_text = self._extract_json_text(response_text)
            standardized = json.loads(response_text)

            return standardized, cost

        except Exception as e:
            return {'error': f'Standardization failed: {str(e)}'}, 0.0

    def validate_specs(self, standardized: Dict) -> Tuple[Dict, float, List[str]]:
        """
        Validate standardized specs using existing validator
        Returns: (validated_specs, avg_confidence, issues)
        """
        if 'error' in standardized or not standardized:
            return {}, 0.0, ['No specs to validate']

        field_types = {
            'primary_category': 'single_line_text_field',
            'product_category_type': 'single_line_text_field',
            'collection_name': 'single_line_text_field',
            'overall_width_mm': 'single_line_text_field',
            'overall_depth_mm': 'single_line_text_field',
            'overall_height_mm': 'single_line_text_field',
            'material': 'single_line_text_field',
            'colour_finish': 'single_line_text_field',
            'warranty_years': 'number_integer',
            'weight_kg': 'number_decimal',
            'tap_hole_size_mm': 'number_integer',
            'installation_type': 'single_line_text_field',
            'flow_rate_lpm': 'number_decimal',
            'water_pressure_min_kpa': 'number_integer',
            'water_pressure_max_kpa': 'number_integer',
        }

        validated = {}
        total_confidence = 0.0
        field_count = 0
        issues = []

        for key, value in standardized.items():
            field_type = field_types.get(key, 'single_line_text_field')
            result = validate_metafield(key, str(value), field_type, source='llm')

            if result.confidence >= 0.3:  # Accept if above minimum threshold
                validated[key] = result.value
                total_confidence += result.confidence
                field_count += 1

                if result.issues:
                    issues.extend(result.issues)
            else:
                issues.append(f'{key}: Low confidence ({result.confidence:.2f})')

        avg_confidence = total_confidence / field_count if field_count > 0 else 0.0

        return validated, avg_confidence, issues

    # Valid columns that can be updated by enrichment
    VALID_ENRICHMENT_COLUMNS = {
        'primary_category', 'product_category_type', 'collection_name',
        'super_category', 'overall_width_mm', 'overall_depth_mm',
        'overall_height_mm', 'material', 'colour_finish', 'warranty_years',
        'weight_kg', 'tap_hole_size_mm', 'installation_type',
        'flow_rate_lpm', 'water_pressure_min_kpa', 'water_pressure_max_kpa',
        'is_boiling', 'is_chilled', 'is_sparkling', 'is_filtered', 'is_ambient',
    }

    def update_database(self, shopify_id: int, specs: Dict, confidence: float):
        """Update Shopify product with enriched specs"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Build UPDATE statement dynamically - only valid columns
        updates = []
        values = []

        for key, value in specs.items():
            if key in self.VALID_ENRICHMENT_COLUMNS:
                # Convert "None" strings and zero values to actual NULL
                if value is None or str(value) in ('None', '', '0', '0.0'):
                    value = None
                updates.append(f"{key} = ?")
                values.append(value)

        # Add metadata
        updates.append("enriched_at = ?")
        updates.append("enriched_confidence = ?")
        values.extend([datetime.now().isoformat(), confidence])
        values.append(shopify_id)

        query = f"UPDATE shopify_products SET {', '.join(updates)} WHERE id = ?"

        cursor.execute(query, values)
        conn.commit()
        conn.close()

    def process_product(self, product: Dict) -> Dict:
        """Process single product through extraction pipeline"""
        result = {
            'shopify_id': product['shopify_id'],
            'sku': product['sku'],
            'title': product['title'],
            'supplier_url': product['supplier_url'],
            'supplier_name': product.get('supplier_name', 'unknown'),
            'timestamp': datetime.now().isoformat(),
            'success': False
        }

        try:
            # Step 1: Extract
            raw_specs, extract_cost = self.extract_with_llm(
                product['supplier_url'],
                product['title']
            )
            result['extraction_cost'] = extract_cost
            result['raw_specs'] = raw_specs

            if 'error' in raw_specs:
                result['error'] = raw_specs['error']
                result['classification'] = 'failed'
                return result

            if not raw_specs:
                result['error'] = 'No specs found (likely category page)'
                result['classification'] = 'skipped'
                return result

            # Step 2: Standardize
            time.sleep(0.5)  # Rate limiting
            standardized, standard_cost = self.standardize_with_llm(
                raw_specs,
                result['supplier_name'],
                title=product.get('title', ''),
                supplier_url=product.get('supplier_url', '')
            )
            result['standardization_cost'] = standard_cost
            result['standardized_specs'] = standardized

            if 'error' in standardized:
                result['error'] = standardized['error']
                result['classification'] = 'failed'
                return result

            # Step 3: Validate
            validated, confidence, issues = self.validate_specs(standardized)
            result['validated_specs'] = validated
            result['confidence'] = confidence
            result['issues'] = issues
            result['spec_count'] = len(validated)

            # Auto-assign super_category based on primary_category
            if 'primary_category' in validated:
                primary = validated['primary_category']
                if primary in SUPER_CATEGORY_MAP:
                    validated['super_category'] = SUPER_CATEGORY_MAP[primary]

            # Classify
            if confidence >= 0.7:
                result['classification'] = 'auto_push'
                result['success'] = True
            elif confidence >= 0.3:
                result['classification'] = 'needs_review'
                result['success'] = True
            else:
                result['classification'] = 'rejected'
                result['error'] = 'Low confidence scores'
                return result

            # Update database for all successful extractions
            # Confidence score stored for review filtering
            self.update_database(
                product['shopify_id'],
                validated,
                confidence
            )

            return result

        except Exception as e:
            result['error'] = f'Pipeline error: {str(e)}'
            result['classification'] = 'failed'
            return result

    def run(self, limit: Optional[int] = None, force_specs: bool = False):
        """Run enrichment pipeline on Shopify products"""
        print("=" * 80)
        print("SHOPIFY PRODUCT ENRICHMENT PIPELINE")
        if force_specs:
            print("  MODE: Force spec extraction for categorized products")
        print("=" * 80)

        # Get products to process
        products = self.get_products_to_enrich(limit, force_specs=force_specs)
        total_products = len(products)

        if self.resume and self.processed_count > 0:
            products = products[self.processed_count:]
            print(f"\n✓ Resuming: {len(products)} products remaining")

        print(f"\nProducts to enrich: {total_products}")
        if limit:
            print(f"(Limited to first {limit})")
        print(f"Estimated cost: ${total_products * 0.02:.2f} - ${total_products * 0.05:.2f}")
        print()

        # Process each product
        for i, product in enumerate(products, 1):
            print(f"[{self.processed_count + i}/{total_products}] Processing {product['sku']}...")

            result = self.process_product(product)

            # Track stats
            product_cost = result.get('extraction_cost', 0) + result.get('standardization_cost', 0)
            self.total_cost += product_cost
            self.processed_count += 1

            if result['success']:
                self.success_count += 1
                status = "✓"
            elif result.get('classification') == 'skipped':
                self.skipped_count += 1
                status = "⊘"
            else:
                self.failed_count += 1
                status = "✗"

            print(f"  {status} {result.get('classification', 'unknown')}: "
                  f"{result.get('spec_count', 0)} specs, "
                  f"confidence {result.get('confidence', 0):.2f}, "
                  f"cost ${product_cost:.4f}")

            if result.get('error'):
                print(f"    Error: {result['error']}")

            self.results.append(result)

            # Save checkpoint every 10 products
            if i % 10 == 0:
                self._save_checkpoint()
                self._save_results()

            # Rate limiting
            time.sleep(1.0)

        # Final save
        self._save_checkpoint()
        self._save_results()
        self._print_summary()

    def _save_results(self):
        """Save detailed results to JSON"""
        with open(self.results_file, 'w') as f:
            json.dump({
                'session_id': self.session_id,
                'timestamp': datetime.now().isoformat(),
                'summary': {
                    'total_processed': self.processed_count,
                    'successful': self.success_count,
                    'failed': self.failed_count,
                    'skipped': self.skipped_count,
                    'total_cost': self.total_cost
                },
                'results': self.results
            }, f, indent=2)

    def _print_summary(self):
        """Print final summary report"""
        print("\n" + "=" * 80)
        print("ENRICHMENT COMPLETE")
        print("=" * 80)

        print(f"\nProducts Processed: {self.processed_count}")
        print(f"  ✓ Successful: {self.success_count} ({self.success_count/self.processed_count*100:.1f}%)")
        print(f"  ⊘ Skipped (category pages): {self.skipped_count}")
        print(f"  ✗ Failed: {self.failed_count}")

        # Classification breakdown
        auto_push = [r for r in self.results if r.get('classification') == 'auto_push']
        needs_review = [r for r in self.results if r.get('classification') == 'needs_review']

        print(f"\nClassification:")
        print(f"  Auto-Push (≥0.7): {len(auto_push)} products")
        print(f"  Needs Review (0.3-0.7): {len(needs_review)} products")

        # Costs
        print(f"\nCosts:")
        print(f"  Total: ${self.total_cost:.2f}")
        print(f"  Per Product: ${self.total_cost/self.processed_count:.4f}")

        # Specs extracted
        total_specs = sum(r.get('spec_count', 0) for r in self.results if r['success'])
        avg_specs = total_specs / self.success_count if self.success_count > 0 else 0

        print(f"\nSpecifications:")
        print(f"  Total Extracted: {total_specs}")
        print(f"  Average per Product: {avg_specs:.1f}")

        print(f"\nResults saved to: {self.results_file}")
        print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description='Enrich Shopify products with LLM extraction')
    parser.add_argument('--limit', type=int, help='Limit number of products to process')
    parser.add_argument('--resume', action='store_true', help='Resume from last checkpoint')
    parser.add_argument('--force-specs', action='store_true', help='Re-enrich products with categories but missing specs')
    parser.add_argument('--api-key', help='Anthropic API key (or set ANTHROPIC_API_KEY env var)')

    args = parser.parse_args()

    try:
        pipeline = ShopifyEnrichmentPipeline(api_key=args.api_key, resume=args.resume)
        pipeline.run(limit=args.limit, force_specs=args.force_specs)

    except KeyboardInterrupt:
        print("\n\n⚠ Interrupted by user. Progress saved to checkpoint file.")
        print("   Resume with: python scripts/enrich_shopify_products.py --resume")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
