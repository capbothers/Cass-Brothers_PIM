#!/usr/bin/env python3
"""
Test LLM-based product spec extraction
Processes 10-20 sample products to validate approach before production
"""

import os
import sys
import json
import sqlite3
import requests
import time
from datetime import datetime
from typing import Dict, List, Optional
from anthropic import Anthropic
from bs4 import BeautifulSoup

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core.data_validator import validate_metafield, filter_by_confidence


class LLMExtractionTest:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found. Set environment variable or pass api_key parameter.")

        self.client = Anthropic(api_key=self.api_key)
        self.test_results = []
        self.total_cost = 0.0

    def select_test_samples(self, sample_size: int = 15) -> List[Dict]:
        """Select diverse sample of products from different suppliers"""
        conn = sqlite3.connect('supplier_products.db')
        cursor = conn.cursor()

        # Get diverse sample across suppliers
        cursor.execute("""
            WITH supplier_samples AS (
                SELECT
                    supplier_name,
                    product_url,
                    product_name,
                    sku,
                    extraction_source,
                    ROW_NUMBER() OVER (PARTITION BY supplier_name ORDER BY RANDOM()) as rn
                FROM supplier_products
                WHERE extraction_source IN ('json_ld', 'html_parse')
                AND product_url IS NOT NULL
            )
            SELECT supplier_name, product_url, product_name, sku, extraction_source
            FROM supplier_samples
            WHERE rn = 1
            LIMIT ?
        """, (sample_size,))

        samples = []
        for row in cursor.fetchall():
            samples.append({
                'supplier': row[0],
                'url': row[1],
                'name': row[2],
                'sku': row[3],
                'extraction_source': row[4]
            })

        conn.close()
        return samples

    def extract_with_llm(self, url: str) -> Dict:
        """Extract specifications using Claude API"""

        extraction_prompt = """You are extracting product specifications from this webpage content. Extract ALL specifications and technical details.

Look for:
- Dimensions (width, depth, height, length, diameter) in mm or cm
- Material/construction details
- Colour/finish
- Weight
- Warranty information
- Technical specifications (water consumption, ratings, certifications, etc.)
- Installation type/mounting
- Item/product code/SKU
- Brand
- Price
- Features list
- Any other relevant product attributes

Check ALL parts of the page including:
- Meta tags (og:description, product meta tags)
- Product description sections
- Specification tables
- Feature lists
- Technical information sections

Return ONLY valid JSON with descriptive keys. Use this exact format:
{
  "item_code": "...",
  "brand": "...",
  "dimensions": {...},
  "material": "...",
  "colour": "...",
  ...other specs...
}

Be thorough and extract every specification you can find."""

        print(f"  → Fetching {url[:60]}...")

        try:
            # Fetch page HTML
            response = requests.get(url, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response.raise_for_status()

            # Parse HTML to extract key content
            soup = BeautifulSoup(response.content, 'html.parser')

            # Get meta description (often has specs)
            meta_desc = soup.find('meta', property='og:description')
            meta_content = meta_desc.get('content', '') if meta_desc else ''

            # Get main product content
            product_div = soup.find(['div', 'section'], class_=lambda x: x and any(
                term in str(x).lower() for term in ['product', 'woocommerce', 'entry-content']
            ))
            product_text = product_div.get_text() if product_div else soup.get_text()

            # Limit text size for API
            content = f"""
Product URL: {url}

Meta Description:
{meta_content[:1000]}

Product Content:
{product_text[:3000]}
"""

            print(f"  → Calling Claude API for extraction...")

            # Call Claude API
            message = self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=2000,
                messages=[{
                    "role": "user",
                    "content": f"{extraction_prompt}\n\nWebpage Content:\n{content}"
                }]
            )

            # Parse response
            response_text = message.content[0].text

            # Extract JSON from response (might have markdown code blocks)
            if '```json' in response_text:
                json_start = response_text.find('```json') + 7
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end].strip()
            elif '```' in response_text:
                json_start = response_text.find('```') + 3
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end].strip()

            raw_specs = json.loads(response_text)

            # Calculate cost (approx based on tokens)
            input_tokens = message.usage.input_tokens
            output_tokens = message.usage.output_tokens
            cost = (input_tokens / 1_000_000 * 3.0) + (output_tokens / 1_000_000 * 15.0)

            return {
                "status": "success",
                "raw_specs": raw_specs,
                "cost": cost,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens
            }

        except json.JSONDecodeError as e:
            return {
                "status": "error",
                "error": f"JSON parse error: {str(e)}",
                "raw_response": response_text[:200] if 'response_text' in locals() else None,
                "cost": 0.01
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "cost": 0.0
            }

    def standardize_with_llm(self, raw_specs: Dict, supplier: str) -> Dict:
        """Standardize raw specs to metafield schema using LLM"""

        standardization_prompt = f"""Given raw product specifications from {supplier}, standardize them to match our metafield schema.

Target Schema Fields:
- overall_width_mm: integer (10-5000)
- overall_depth_mm: integer (10-3000)
- overall_height_mm: integer (5-3000)
- basin_width_mm: integer (for basins/sinks)
- basin_depth_mm: integer
- material: string (standardize to: ceramic, porcelain, vitreous china, stainless steel, brass, copper, acrylic, stone, wood, glass, composite)
- colour_finish: string (standardize but keep finish descriptors like Gloss, Matte, Brushed, Polished)
- warranty_years: integer
- item_code: string
- installation_type: string (e.g., wall-hung, floor-standing, wall-mounted, back-to-wall, close-coupled)
- mounting_type: string
- weight_kg: float
- wels_rating: string (for Australian water efficiency)
- brand: string
- finish: string (for tapware - chrome, brushed nickel, matte black, etc.)

Standardization Rules:
1. Extract numeric values from dimensions (e.g., "600mm" → 600, "60cm" → 600)
2. Standardize material names: "Vitreous China"/"vitrified ceramic" → "ceramic"
3. For multiple materials, primary material in 'material' field
4. Keep finish descriptors in colour (e.g., "Gloss White", "Matte Black")
5. Extract years from warranty ("5 years" → 5, "lifetime" → 99)
6. Only return fields with valid, confident data
7. Add 'confidence_notes' array for uncertain mappings

Return ONLY valid JSON matching schema. No explanatory text."""

        print(f"  → Calling Claude API for standardization...")

        try:
            message = self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1500,
                messages=[{
                    "role": "user",
                    "content": f"{standardization_prompt}\n\nRaw Specifications:\n{json.dumps(raw_specs, indent=2)}"
                }]
            )

            response_text = message.content[0].text

            # Extract JSON from response
            if '```json' in response_text:
                json_start = response_text.find('```json') + 7
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end].strip()
            elif '```' in response_text:
                json_start = response_text.find('```') + 3
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end].strip()

            standardized = json.loads(response_text)

            # Calculate cost
            input_tokens = message.usage.input_tokens
            output_tokens = message.usage.output_tokens
            cost = (input_tokens / 1_000_000 * 3.0) + (output_tokens / 1_000_000 * 15.0)

            return {
                "status": "success",
                "standardized": standardized,
                "cost": cost,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "cost": 0.0
            }

    def validate_specs(self, standardized: Dict) -> Dict:
        """Validate using existing validation pipeline"""

        validated = {}
        total_confidence = 0.0
        issues = []

        # Map field keys to types for validation
        field_types = {
            'overall_width_mm': 'single_line_text_field',
            'overall_depth_mm': 'single_line_text_field',
            'overall_height_mm': 'single_line_text_field',
            'basin_width_mm': 'single_line_text_field',
            'basin_depth_mm': 'single_line_text_field',
            'material': 'single_line_text_field',
            'colour_finish': 'single_line_text_field',
            'warranty_years': 'number_integer',
            'item_code': 'single_line_text_field',
            'installation_type': 'single_line_text_field',
            'mounting_type': 'single_line_text_field',
            'weight_kg': 'number_decimal',
            'wels_rating': 'single_line_text_field',
            'brand': 'single_line_text_field',
            'finish': 'single_line_text_field',
        }

        for key, value in standardized.items():
            if key == 'confidence_notes':
                continue

            # Get field type
            field_type = field_types.get(key, 'single_line_text_field')

            # Use existing validator
            result = validate_metafield(
                key, str(value), field_type, source='llm'
            )

            # ValidationResult has: value, confidence, issues
            if result.confidence >= 0.3:  # Accept if above minimum threshold
                validated[key] = result.value
                total_confidence += result.confidence
            else:
                issues.append(f"{key}: {value} (confidence too low: {result.confidence:.2f})")

            # Add any validation issues
            issues.extend(result.issues)

        # Calculate overall confidence
        confidence_score = max(0.0, min(1.0, 0.5 + total_confidence))

        # Classify
        if confidence_score >= 0.7:
            classification = "auto_push"
        elif confidence_score >= 0.3:
            classification = "needs_review"
        else:
            classification = "rejected"

        return {
            "validated_specs": validated,
            "confidence_score": confidence_score,
            "classification": classification,
            "issues": issues
        }

    def test_product(self, sample: Dict) -> Dict:
        """Test full pipeline on one product"""

        print(f"\nTesting: {sample['supplier']} - {sample['name'][:50]}...")

        result = {
            "supplier": sample['supplier'],
            "url": sample['url'],
            "sku": sample['sku'],
            "name": sample['name'],
            "extraction_source": sample['extraction_source']
        }

        try:
            # Stage 1: Extract
            extraction = self.extract_with_llm(sample['url'])
            result['extraction_status'] = extraction['status']
            result['extraction_cost'] = extraction.get('cost', 0)
            self.total_cost += result['extraction_cost']

            if extraction['status'] != 'success':
                result['error'] = f"Extraction failed: {extraction.get('error', 'Unknown error')}"
                return result

            # Rate limiting
            time.sleep(0.5)

            # Stage 2: Standardize
            standardization = self.standardize_with_llm(
                extraction['raw_specs'],
                sample['supplier']
            )
            result['standardization_status'] = standardization['status']
            result['standardization_cost'] = standardization.get('cost', 0)
            self.total_cost += result['standardization_cost']

            if standardization['status'] != 'success':
                result['error'] = f"Standardization failed: {standardization.get('error', 'Unknown error')}"
                return result

            # Stage 3: Validate
            standardized_data = standardization['standardized']
            # Remove confidence_notes before validation
            confidence_notes = standardized_data.pop('confidence_notes', [])

            validation = self.validate_specs(standardized_data)
            result['validated_specs'] = validation['validated_specs']
            result['confidence_score'] = validation['confidence_score']
            result['classification'] = validation['classification']
            result['issues'] = validation['issues']
            result['spec_count'] = len(validation['validated_specs'])
            result['confidence_notes'] = confidence_notes

            print(f"  ✓ {result['spec_count']} specs | Confidence: {result['confidence_score']:.2f} | {result['classification']}")

            # Rate limiting between products
            time.sleep(1.0)

        except Exception as e:
            result['error'] = str(e)
            print(f"  ✗ Error: {e}")

        return result

    def run_test(self, sample_size: int = 15):
        """Run full test on sample products"""

        print("="*100)
        print("LLM EXTRACTION TEST PIPELINE")
        print("="*100)

        # Select samples
        print(f"\nSelecting {sample_size} diverse product samples...")
        samples = self.select_test_samples(sample_size)
        print(f"✓ Selected {len(samples)} products from {len(set(s['supplier'] for s in samples))} suppliers")

        # Test each product
        print("\n" + "="*100)
        print("TESTING PRODUCTS")
        print("="*100)

        for sample in samples:
            result = self.test_product(sample)
            self.test_results.append(result)

        # Generate report
        self.generate_report()

    def generate_report(self):
        """Generate test results report"""

        print("\n" + "="*100)
        print("TEST RESULTS SUMMARY")
        print("="*100)

        total_products = len(self.test_results)
        successful = [r for r in self.test_results if 'error' not in r]
        failed = [r for r in self.test_results if 'error' in r]

        print(f"\nProducts Tested: {total_products}")
        print(f"  ✓ Successful: {len(successful)} ({len(successful)/total_products*100:.1f}%)")
        print(f"  ✗ Failed: {len(failed)} ({len(failed)/total_products*100:.1f}%)")

        auto_push = []
        if successful:
            # Classification breakdown
            auto_push = [r for r in successful if r.get('classification') == 'auto_push']
            needs_review = [r for r in successful if r.get('classification') == 'needs_review']
            rejected = [r for r in successful if r.get('classification') == 'rejected']

            print(f"\nClassification:")
            print(f"  Auto-Push (≥0.7): {len(auto_push)} ({len(auto_push)/len(successful)*100:.1f}%)")
            print(f"  Needs Review (0.3-0.7): {len(needs_review)} ({len(needs_review)/len(successful)*100:.1f}%)")
            print(f"  Rejected (<0.3): {len(rejected)} ({len(rejected)/len(successful)*100:.1f}%)")

            # Specs extracted
            avg_specs = sum(r.get('spec_count', 0) for r in successful) / len(successful)
            print(f"\nAverage Specs Extracted: {avg_specs:.1f}")

            # Confidence scores
            avg_confidence = sum(r.get('confidence_score', 0) for r in successful) / len(successful)
            print(f"Average Confidence Score: {avg_confidence:.2f}")

        # Cost analysis
        print(f"\n" + "="*100)
        print("COST ANALYSIS")
        print("="*100)
        print(f"Total Cost (test): ${self.total_cost:.2f}")
        print(f"Cost per Product: ${self.total_cost/total_products:.3f}")
        print(f"\nProjected Production Costs:")
        print(f"  14,845 products × ${self.total_cost/total_products:.3f} = ${(self.total_cost/total_products)*14845:.2f}")

        # Save detailed results
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f'llm_extraction_test_{timestamp}.json'

        with open(output_file, 'w') as f:
            json.dump({
                'summary': {
                    'total_products': total_products,
                    'successful': len(successful),
                    'failed': len(failed),
                    'total_cost': self.total_cost,
                    'cost_per_product': self.total_cost/total_products if total_products > 0 else 0
                },
                'results': self.test_results
            }, f, indent=2)

        print(f"\n✓ Detailed results saved to: {output_file}")

        # Show sample successes
        if auto_push:
            print(f"\n" + "="*100)
            print("SAMPLE AUTO-PUSH PRODUCTS (High Confidence)")
            print("="*100)
            for r in auto_push[:3]:
                print(f"\n{r['supplier']} - {r['name'][:50]}...")
                print(f"  Confidence: {r['confidence_score']:.2f}")
                print(f"  Specs: {list(r['validated_specs'].keys())[:5]}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Test LLM extraction pipeline')
    parser.add_argument('--samples', type=int, default=15, help='Number of products to test')
    parser.add_argument('--api-key', help='Anthropic API key (or set ANTHROPIC_API_KEY env var)')

    args = parser.parse_args()

    try:
        tester = LLMExtractionTest(api_key=args.api_key)
        tester.run_test(sample_size=args.samples)
    except ValueError as e:
        print(f"Error: {e}")
        print("\nTo run this test, you need an Anthropic API key:")
        print("  1. Get key from: https://console.anthropic.com/")
        print("  2. Set environment variable: export ANTHROPIC_API_KEY='your-key'")
        print("  3. Or pass with --api-key flag")
        sys.exit(1)


if __name__ == '__main__':
    main()
