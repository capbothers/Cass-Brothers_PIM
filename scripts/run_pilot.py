"""
Run Pilot Batch for Supplier

Orchestrates the complete data enrichment pipeline:
1. Discover spec sheet URLs on supplier product pages
2. Extract data from spec sheets (simulated for now)
3. Score confidence for each field
4. Generate pilot report with metrics

Usage:
    python scripts/run_pilot.py --supplier abey.com.au --limit 50
    python scripts/run_pilot.py --supplier abey.com.au --limit 100 --dry-run
"""

import sys
import os
import json
import argparse
from datetime import datetime
from typing import Dict, Any, List
import time
import importlib.util
from dotenv import load_dotenv

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(REPO_ROOT, '.env'))

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    env_path = os.path.join(REPO_ROOT, '.env')
    load_dotenv(env_path)
except ImportError:
    # dotenv not available, environment variables must be set manually
    pass


def _import_module_from_path(module_name: str, relative_path: str):
    """Import a module by file path to avoid loading core/__init__.py."""
    module_path = os.path.join(REPO_ROOT, relative_path)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


supplier_db_module = _import_module_from_path("supplier_db", os.path.join("core", "supplier_db.py"))
spec_sheet_scraper_module = _import_module_from_path("spec_sheet_scraper", os.path.join("core", "spec_sheet_scraper.py"))
confidence_scorer_module = _import_module_from_path("confidence_scorer", os.path.join("core", "confidence_scorer.py"))

get_supplier_db = supplier_db_module.get_supplier_db
get_spec_sheet_scraper = spec_sheet_scraper_module.get_spec_sheet_scraper
get_confidence_scorer = confidence_scorer_module.get_confidence_scorer


class PilotRunner:
    """Orchestrate pilot batch processing"""

    def __init__(self, supplier: str, limit: int = 50, dry_run: bool = False):
        self.supplier = supplier
        self.limit = limit
        self.dry_run = dry_run
        self.db = get_supplier_db()
        self.scraper = get_spec_sheet_scraper()
        self.scorer = get_confidence_scorer()
        self.use_real_extraction = False
        self.run_id = datetime.now().strftime('%Y%m%d_%H%M%S')

        self.metrics = {
            'total_skus': 0,
            'spec_sheets_found': 0,
            'spec_sheets_missing': 0,
            'extraction_attempted': 0,
            'extraction_success': 0,
            'extraction_failed': 0,
            'page_extraction_success': 0,
            'pdf_extraction_success': 0,
            'page_only': 0,
            'pdf_only': 0,
            'page_and_pdf': 0,
            'auto_apply_count': 0,
            'needs_review_count': 0,
            'high_confidence_products': 0,
            'low_confidence_products': 0,
            'errors': [],
            'extraction_samples': []
        }

    def run(self):
        """Run complete pilot workflow"""
        print("╔════════════════════════════════════════════════════════════╗")
        print("║  Pilot Batch Runner                                        ║")
        print("╚════════════════════════════════════════════════════════════╝\n")

        print(f"Supplier: {self.supplier}")
        print(f"Limit: {self.limit} SKUs")
        print(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}\n")

        # Phase 1: Get supplier products
        products = self._get_supplier_products()
        if not products:
            print(f"❌ No products found for supplier '{self.supplier}'")
            return

        self.metrics['total_skus'] = len(products)
        print(f"✅ Found {len(products)} products from {self.supplier}\n")

        # Phase 2: Discover spec sheets
        print("=" * 60)
        print("PHASE 1: Spec Sheet Discovery")
        print("=" * 60 + "\n")
        self._discover_spec_sheets(products)

        # Phase 3: Simulate extraction and scoring
        print("\n" + "=" * 60)
        print("PHASE 2: Data Extraction & Confidence Scoring")
        print("=" * 60 + "\n")
        if self.use_real_extraction:
            self._real_extraction_and_scoring(products)
        else:
            self._simulate_extraction_and_scoring(products)

        # Phase 4: Generate report
        print("\n" + "=" * 60)
        print("PHASE 3: Pilot Report")
        print("=" * 60 + "\n")
        self._generate_report()

    def _get_supplier_products(self) -> List[Dict[str, Any]]:
        """Get supplier products from database"""
        conn = self.db.db_path
        import sqlite3
        conn = sqlite3.connect(self.db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM supplier_products
            WHERE supplier_name LIKE ?
            ORDER BY updated_at DESC
            LIMIT ?
        ''', (f'%{self.supplier}%', self.limit))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def _discover_spec_sheets(self, products: List[Dict[str, Any]]):
        """Discover spec sheet URLs for products"""
        print(f"Discovering spec sheets for {len(products)} products...\n")

        for i, product in enumerate(products, 1):
            sku = product['sku']
            product_url = product['product_url']

            print(f"[{i}/{len(products)}] {sku}...", end=" ")

            try:
                # Check if already has spec sheet
                if product.get('spec_sheet_url'):
                    print(f"✓ Already has spec sheet")
                    self.metrics['spec_sheets_found'] += 1
                    continue

                # Discover spec sheet
                spec_sheet_url = self.scraper.find_spec_sheet_url(product_url)

                if spec_sheet_url:
                    print(f"✅ Found: {spec_sheet_url[:50]}...")
                    self.metrics['spec_sheets_found'] += 1

                    if not self.dry_run:
                        self.db.update_spec_sheet_url(sku, spec_sheet_url)
                else:
                    print(f"⚠️  No spec sheet found")
                    self.metrics['spec_sheets_missing'] += 1

                # Rate limiting
                if i < len(products):
                    time.sleep(1.0)  # 1 second between requests

            except Exception as e:
                print(f"❌ Error: {e}")
                self.metrics['spec_sheets_missing'] += 1
                self.metrics['errors'].append({
                    'sku': sku,
                    'phase': 'discovery',
                    'error': str(e)
                })

        print(f"\n📊 Spec Sheet Discovery Complete:")
        print(f"  Found: {self.metrics['spec_sheets_found']}")
        print(f"  Missing: {self.metrics['spec_sheets_missing']}")

    def _simulate_extraction_and_scoring(self, products: List[Dict[str, Any]]):
        """
        Simulate extraction and confidence scoring

        NOTE: This simulates extraction for pilot purposes.
        In production, you would call queue_processor.extract_from_spec_sheet()
        """
        print(f"Simulating extraction for products with spec sheets...\n")

        products_with_specs = [p for p in products if p.get('spec_sheet_url')]

        if not products_with_specs:
            print("⚠️  No products with spec sheets to extract")
            return

        for i, product in enumerate(products_with_specs[:10], 1):  # Limit to 10 for demo
            sku = product['sku']
            collection = product.get('detected_collection', 'unknown')

            print(f"[{i}/{min(10, len(products_with_specs))}] {sku} ({collection})...", end=" ")

            try:
                # Simulate extraction (replace with real extraction in production)
                simulated_data = self._simulate_extraction(product)

                # Score confidence
                scored = self.scorer.score_extracted_data(simulated_data, collection)

                # Track metrics
                self.metrics['extraction_attempted'] += 1
                self.metrics['extraction_success'] += 1
                self.metrics['auto_apply_count'] += len(scored['auto_apply_fields'])
                self.metrics['needs_review_count'] += len(scored['review_fields'])

                if scored['overall_confidence'] >= 0.6:
                    self.metrics['high_confidence_products'] += 1
                    print(f"✅ Conf: {scored['overall_confidence']:.2%} ({len(scored['auto_apply_fields'])} auto)")
                else:
                    self.metrics['low_confidence_products'] += 1
                    print(f"⚠️  Conf: {scored['overall_confidence']:.2%} (needs review)")

                # Store in database (if not dry run)
                if not self.dry_run:
                    # In production, you would:
                    # 1. Add to processing_queue
                    # 2. Store extracted_data
                    # 3. Store confidence_summary
                    pass

            except Exception as e:
                print(f"❌ Error: {e}")
                self.metrics['extraction_failed'] += 1
                self.metrics['errors'].append({
                    'sku': sku,
                    'phase': 'extraction',
                    'error': str(e)
                })

    def _simulate_extraction(self, product: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulate extraction for pilot purposes

        In production, replace with:
        from core.queue_processor import get_queue_processor
        processor = get_queue_processor()
        extracted = processor.extract_from_spec_sheet(spec_sheet_url, collection)
        """
        collection = product.get('detected_collection', 'sinks')

        # Simulate realistic extraction data
        if collection == 'sinks':
            return {
                'length_mm': '450',
                'overall_width_mm': '380',
                'overall_depth_mm': '200',
                'material': '304 Stainless Steel',
                'installation_type': 'Undermount',
                'bowl_count': '1',
                'warranty': '10 year',
                'finish': 'Brushed',
                'estimated_weight': 'approximately 8kg',  # Low confidence
            }
        elif collection == 'taps':
            return {
                'spout_height_mm': '185',
                'spout_reach_mm': '220',
                'material': 'Brass',
                'finish': 'Chrome',
                'installation_type': 'Deck Mounted',
                'wels_rating': '4 star',
            }
        else:
            return {
                'product_type': collection,
                'material': 'Stainless Steel',
                'finish': 'Polished',
            }

    def _real_extraction_and_scoring(self, products: List[Dict[str, Any]]):
        """
        Run real extraction + confidence scoring using product pages and spec sheets.

        Strategy:
        1. Try extracting specs from product page HTML first (more reliable)
        2. Fall back to PDF spec sheet for missing fields
        3. Merge results with page specs taking precedence
        """
        print(f"Running real extraction (page + PDF fallback)...\n")

        # Import required modules
        queue_processor_module = _import_module_from_path("queue_processor", os.path.join("core", "queue_processor.py"))
        collection_detector_module = _import_module_from_path("collection_detector", os.path.join("core", "collection_detector.py"))
        page_extractors_module = _import_module_from_path("page_extractors", os.path.join("core", "page_extractors.py"))

        processor = queue_processor_module.QueueProcessor(None, None, None)
        detect_collection = collection_detector_module.detect_collection
        page_extractor = page_extractors_module.get_page_extractor()

        for i, product in enumerate(products, 1):
            sku = product['sku']
            product_url = product.get('product_url', '')
            title = product.get('product_name') or ''
            supplier_name = product.get('supplier_name') or ''
            spec_sheet_url = product.get('spec_sheet_url', '')
            collection = product.get('detected_collection')

            if not collection:
                detected_collection, _confidence = detect_collection(title, product_url)
                collection = detected_collection or 'sinks'

            print(f"[{i}/{len(products)}] {sku} ({collection})...", end=" ")

            try:
                self.metrics['extraction_attempted'] += 1
                extracted_data = {}
                extraction_sources = []

                # Step 1: Try page extraction first
                page_extracted = False
                if product_url:
                    page_specs = page_extractor.extract_specs(product_url, supplier_hint=self.supplier)
                    if page_specs:
                        extracted_data.update(page_specs)
                        extraction_sources.append(f"page:{len(page_specs)} fields")
                        page_extracted = True
                        self.metrics['page_extraction_success'] += 1

                # Step 2: Fall back to PDF for missing fields
                pdf_extracted = False
                if spec_sheet_url:
                    result = processor.extract_from_spec_sheet(
                        spec_sheet_url,
                        collection,
                        product_title=title,
                        vendor=supplier_name
                    )

                    if result.success:
                        pdf_data = result.extracted_data or result.raw_extraction or {}
                        # Merge: page specs take precedence, add PDF fields for missing values
                        for key, value in pdf_data.items():
                            if key not in extracted_data or not extracted_data[key]:
                                extracted_data[key] = value
                        if pdf_data:
                            extraction_sources.append(f"pdf:{len(pdf_data)} fields")
                            pdf_extracted = True
                            self.metrics['pdf_extraction_success'] += 1

                # Track extraction source combinations
                if page_extracted and pdf_extracted:
                    self.metrics['page_and_pdf'] += 1
                elif page_extracted:
                    self.metrics['page_only'] += 1
                elif pdf_extracted:
                    self.metrics['pdf_only'] += 1

                if not extracted_data:
                    self.metrics['extraction_failed'] += 1
                    print(f"❌ No data extracted")
                    continue

                # Score confidence
                scored = self.scorer.score_extracted_data(extracted_data, collection)

                self.metrics['extraction_success'] += 1
                self.metrics['auto_apply_count'] += len(scored['auto_apply_fields'])
                self.metrics['needs_review_count'] += len(scored['review_fields'])

                sources_str = "+".join(extraction_sources) if extraction_sources else "unknown"

                if scored['overall_confidence'] >= 0.6:
                    self.metrics['high_confidence_products'] += 1
                    print(f"✅ {sources_str} | Conf: {scored['overall_confidence']:.2%} ({len(scored['auto_apply_fields'])} auto)")
                else:
                    self.metrics['low_confidence_products'] += 1
                    print(f"⚠️  {sources_str} | Conf: {scored['overall_confidence']:.2%} (needs review)")

                self.metrics['extraction_samples'].append({
                    'sku': sku,
                    'collection': collection,
                    'fields': extracted_data
                })

                if not self.dry_run:
                    queue_title = title or extracted_data.get('title') or ''
                    queue_id = self.db.add_to_processing_queue({
                        'variant_sku': sku,
                        'title': queue_title,
                        'vendor': supplier_name,
                        'shopify_spec_sheet': product['spec_sheet_url'],
                    }, target_collection=collection, run_id=self.run_id)

                    self.db.update_processing_queue_extracted_data(queue_id, extracted_data)
                    self.db.update_processing_queue_confidence(queue_id, scored)

            except Exception as e:
                print(f"❌ Error: {e}")
                self.metrics['extraction_failed'] += 1
                self.metrics['errors'].append({
                    'sku': sku,
                    'phase': 'extraction',
                    'error': str(e)
                })

    def _generate_report(self):
        """Generate pilot report"""
        print("PILOT REPORT")
        print("─" * 60)

        # Summary
        print(f"\n📊 Overall Metrics:")
        print(f"  Total SKUs Processed: {self.metrics['total_skus']}")
        print(f"  Spec Sheets Found: {self.metrics['spec_sheets_found']} ({self._percentage(self.metrics['spec_sheets_found'], self.metrics['total_skus'])})")
        print(f"  Spec Sheets Missing: {self.metrics['spec_sheets_missing']} ({self._percentage(self.metrics['spec_sheets_missing'], self.metrics['total_skus'])})")

        # Extraction
        print(f"\n🔬 Extraction & Scoring:")
        print(f"  Attempted: {self.metrics['extraction_attempted']}")
        print(f"  Success: {self.metrics['extraction_success']}")
        print(f"  Failed: {self.metrics['extraction_failed']}")

        # Extraction Sources
        if self.metrics['page_extraction_success'] > 0 or self.metrics['pdf_extraction_success'] > 0:
            print(f"\n📄 Extraction Sources:")
            print(f"  Page Extraction: {self.metrics['page_extraction_success']} products")
            print(f"  PDF Extraction: {self.metrics['pdf_extraction_success']} products")
            print(f"  Page Only: {self.metrics['page_only']} ({self._percentage(self.metrics['page_only'], self.metrics['extraction_success'])})")
            print(f"  PDF Only: {self.metrics['pdf_only']} ({self._percentage(self.metrics['pdf_only'], self.metrics['extraction_success'])})")
            print(f"  Page + PDF: {self.metrics['page_and_pdf']} ({self._percentage(self.metrics['page_and_pdf'], self.metrics['extraction_success'])})")

        # Confidence
        print(f"\n✅ Confidence Distribution:")
        print(f"  High Confidence (≥0.6): {self.metrics['high_confidence_products']} ({self._percentage(self.metrics['high_confidence_products'], self.metrics['extraction_success'])})")
        print(f"  Low Confidence (<0.6): {self.metrics['low_confidence_products']} ({self._percentage(self.metrics['low_confidence_products'], self.metrics['extraction_success'])})")

        # Auto-apply vs Review
        print(f"\n🎯 Field-Level Metrics:")
        total_fields = self.metrics['auto_apply_count'] + self.metrics['needs_review_count']
        print(f"  Total Fields Extracted: {total_fields}")
        print(f"  Auto-Apply Fields: {self.metrics['auto_apply_count']} ({self._percentage(self.metrics['auto_apply_count'], total_fields)})")
        print(f"  Needs Review Fields: {self.metrics['needs_review_count']} ({self._percentage(self.metrics['needs_review_count'], total_fields)})")

        # Errors
        if self.metrics['errors']:
            print(f"\n❌ Errors ({len(self.metrics['errors'])}):")
            for err in self.metrics['errors'][:5]:
                print(f"  • {err['sku']} ({err['phase']}): {err['error']}")
            if len(self.metrics['errors']) > 5:
                print(f"  ... and {len(self.metrics['errors']) - 5} more")

        # Next steps
        print(f"\n📋 Next Steps:")
        if self.metrics['needs_review_count'] > 0:
            print(f"  1. Export review queue:")
            print(f"     python scripts/export_review_queue.py --threshold 0.6")
        if self.metrics['high_confidence_products'] > 0:
            print(f"  2. Apply high-confidence fields to Shopify:")
            print(f"     python scripts/apply_to_shopify.py --collection <collection>")
        if self.metrics['spec_sheets_missing'] > 0:
            print(f"  3. Manually add spec sheet URLs for {self.metrics['spec_sheets_missing']} products")

        # Save report
        if not self.dry_run:
            report_file = self._save_report()
            print(f"\n💾 Report saved to: {report_file}")

    def _percentage(self, part: int, total: int) -> str:
        """Calculate percentage"""
        if total == 0:
            return "0%"
        return f"{part/total*100:.1f}%"

    def _save_report(self) -> str:
        """Save report to file"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = f'pilot_report_{self.supplier.replace(".", "_")}_{timestamp}.json'

        report_data = {
            'supplier': self.supplier,
            'timestamp': timestamp,
            'limit': self.limit,
            'metrics': self.metrics
        }

        with open(report_file, 'w') as f:
            json.dump(report_data, f, indent=2)

        return report_file


def main():
    parser = argparse.ArgumentParser(
        description='Run pilot batch for supplier data enrichment'
    )
    parser.add_argument(
        '--supplier',
        required=True,
        help='Supplier name or domain (e.g., abey.com.au)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=50,
        help='Number of SKUs to process (default: 50)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run without making database changes'
    )
    parser.add_argument(
        '--real-extraction',
        action='store_true',
        help='Run real spec sheet extraction (requires OpenAI API)'
    )

    args = parser.parse_args()

    runner = PilotRunner(
        supplier=args.supplier,
        limit=args.limit,
        dry_run=args.dry_run
    )
    runner.use_real_extraction = args.real_extraction

    runner.run()


if __name__ == "__main__":
    main()
