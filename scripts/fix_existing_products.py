#!/usr/bin/env python3
"""
Fix Existing Products Script

Fills missing data and fixes incorrect data in existing Shopify products using:
1. Shopify fetcher to get current product data
2. Page/PDF extraction to get supplier data
3. Smart merge to fill gaps and fix errors
4. Validation before applying
5. Batch processing with checkpoints

Usage:
    python scripts/fix_existing_products.py --supplier abey.com.au --limit 10
    python scripts/fix_existing_products.py --supplier abey.com.au --fill-empty --fix-errors
    python scripts/fix_existing_products.py --sku ABL0901 --dry-run
"""

import os
import sys
import json
import argparse
from datetime import datetime
from typing import Dict, List, Any, Optional

# Add repo root to path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(REPO_ROOT, '.env'))

# Import core modules
from core import supplier_db, queue_processor, page_extractors, shopify_fetcher, confidence_scorer, data_validator

class ProductFixer:
    """Fixes existing Shopify products by filling gaps and correcting errors."""

    def __init__(self, supplier: str, dry_run: bool = False):
        self.supplier = supplier
        self.dry_run = dry_run

        # Initialize core modules
        self.db = supplier_db.get_supplier_db()
        self.processor = queue_processor.get_queue_processor()
        self.page_extractor = page_extractors.get_page_extractor()
        self.shopify = shopify_fetcher.get_shopify_fetcher()
        self.scorer = confidence_scorer.get_confidence_scorer()
        self.validator = data_validator.get_data_validator()

        self.shopify_available = bool(self.shopify.shop_url and self.shopify.access_token)

        # Metrics
        self.metrics = {
            'total_products': 0,
            'shopify_found': 0,
            'shopify_not_found': 0,
            'extraction_success': 0,
            'extraction_failed': 0,
            'fields_filled': 0,
            'fields_fixed': 0,
            'validation_passed': 0,
            'validation_failed': 0,
            'shopify_updated': 0,
            'errors': []
        }

        # Checkpoint state
        self.checkpoint_file = None
        self.processed_skus = set()

    def fix_products(self, limit: int = None, fill_empty: bool = True,
                    fix_errors: bool = False, confidence_threshold: float = 0.8,
                    batch_size: int = 50):
        """
        Process products from supplier database and fix them in Shopify.

        Args:
            limit: Maximum number of products to process
            fill_empty: Fill empty fields with extracted data
            fix_errors: Fix incorrect data with high-confidence extractions
            confidence_threshold: Minimum confidence to fix existing data (default 0.8)
            batch_size: Number of products per batch
        """
        print(f"\n{'='*80}")
        print(f"FIXING EXISTING PRODUCTS: {self.supplier}")
        print(f"{'='*80}")
        print(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        print(f"Fill empty fields: {fill_empty}")
        print(f"Fix errors: {fix_errors} (confidence >= {confidence_threshold})")
        print(f"Batch size: {batch_size}")
        print()

        # Setup checkpoint
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        if self.dry_run:
            checkpoint_dir = '/tmp'
        else:
            checkpoint_dir = REPO_ROOT if os.access(REPO_ROOT, os.W_OK) else '/tmp'
        self.checkpoint_file = os.path.join(checkpoint_dir, f'fix_checkpoint_{self.supplier}_{timestamp}.json')

        # Get products from supplier database
        products = self._get_supplier_products(limit)
        self.metrics['total_products'] = len(products)

        if not products:
            print(f"No products found for supplier: {self.supplier}")
            return

        print(f"Found {len(products)} products to process\n")

        # Process in batches
        for batch_num in range(0, len(products), batch_size):
            batch = products[batch_num:batch_num + batch_size]
            batch_label = f"Batch {batch_num//batch_size + 1}/{(len(products) + batch_size - 1)//batch_size}"

            print(f"\n{'-'*80}")
            print(f"{batch_label}: Processing {len(batch)} products")
            print(f"{'-'*80}\n")

            try:
                self._process_batch(batch, fill_empty, fix_errors, confidence_threshold)
            except KeyboardInterrupt:
                print("\n\nInterrupted by user. Saving checkpoint...")
                self._save_checkpoint()
                sys.exit(0)
            except Exception as e:
                print(f"Error processing batch: {e}")
                self.metrics['errors'].append({
                    'batch': batch_label,
                    'error': str(e)
                })

            # Save checkpoint after each batch
            self._save_checkpoint()

        # Print final report
        self._print_report()

    def fix_single_product(self, sku: str, fill_empty: bool = True,
                          fix_errors: bool = False, confidence_threshold: float = 0.8):
        """Fix a single product by SKU."""
        print(f"\n{'='*80}")
        print(f"FIXING SINGLE PRODUCT: {sku}")
        print(f"{'='*80}")
        print(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}\n")

        # Get product from database
        product = self.db.get_product_by_sku(sku)
        if not product:
            print(f"Product not found in database: {sku}")
            return

        self.metrics['total_products'] = 1

        # Process single product
        result = self._process_product(product, fill_empty, fix_errors, confidence_threshold)

        if result:
            print(f"\n✓ Successfully processed {sku}")
            if result.get('changes'):
                print(f"\nChanges made:")
                for change in result['changes']:
                    print(f"  - {change}")
        else:
            print(f"\n✗ Failed to process {sku}")

        # Print report
        self._print_report()

    def _process_batch(self, products: List[Dict[str, Any]], fill_empty: bool,
                      fix_errors: bool, confidence_threshold: float):
        """Process a batch of products."""
        for i, product in enumerate(products, 1):
            sku = product.get('sku')

            # Skip if already processed
            if sku in self.processed_skus:
                print(f"[{i}/{len(products)}] Skipping {sku} (already processed)")
                continue

            print(f"[{i}/{len(products)}] Processing {sku}...")

            try:
                result = self._process_product(product, fill_empty, fix_errors, confidence_threshold)
                if result:
                    self.processed_skus.add(sku)

                    # Print summary for this product
                    if result.get('changes'):
                        print(f"  ✓ {len(result['changes'])} changes:")
                        for change in result['changes'][:3]:  # Show first 3
                            print(f"    - {change}")
                        if len(result['changes']) > 3:
                            print(f"    ... and {len(result['changes']) - 3} more")
                    else:
                        print(f"  → No changes needed")
                else:
                    print(f"  ✗ Failed")

            except Exception as e:
                print(f"  ✗ Error: {e}")
                self.metrics['errors'].append({
                    'sku': sku,
                    'error': str(e)
                })

    def _process_product(self, product: Dict[str, Any], fill_empty: bool,
                        fix_errors: bool, confidence_threshold: float) -> Optional[Dict[str, Any]]:
        """
        Process a single product.

        Returns dict with 'changes' list if successful, None if failed.
        """
        sku = product.get('sku')
        product_url = product.get('product_url')
        spec_sheet_url = product.get('spec_sheet_url')

        # Get collection: check override first, then detected_collection
        collection = self.db.get_collection_override(sku) or product.get('detected_collection')

        # Step 1: Fetch existing Shopify data
        if self.shopify_available:
            shopify_data = self.shopify.get_product_by_sku(sku)
            if not shopify_data:
                print(f"    Warning: Product not found in Shopify: {sku}")
                self.metrics['shopify_not_found'] += 1
                return None
        elif self.dry_run:
            shopify_data = {'sku': sku}
            print("    Warning: Shopify credentials missing; using empty baseline for dry-run")
        else:
            print("    Error: Shopify credentials missing; cannot run live updates")
            return None

        self.metrics['shopify_found'] += 1

        # Step 2: Extract specs from supplier URLs
        extracted_data = {}
        extraction_sources = []

        # Try page extraction first
        if product_url:
            try:
                page_specs = self.page_extractor.extract_specs(product_url, supplier_hint=self.supplier)
                if page_specs:
                    extracted_data.update(page_specs)
                    extraction_sources.append(f"page:{len(page_specs)} fields")
            except Exception as e:
                print(f"    Warning: Page extraction failed: {e}")

        # Fall back to PDF for missing fields
        if spec_sheet_url:
            try:
                result = self.processor.extract_from_spec_sheet(spec_sheet_url, collection, sku)
                if result.success and result.extracted_data:
                    pdf_data = result.extracted_data
                    # Merge: page specs take precedence
                    for key, value in pdf_data.items():
                        if key not in extracted_data or not extracted_data[key]:
                            extracted_data[key] = value
                    extraction_sources.append(f"pdf:{len(pdf_data)} fields")
            except Exception as e:
                print(f"    Warning: PDF extraction failed: {e}")

        if not extracted_data:
            print(f"    Warning: No data could be extracted")
            self.metrics['extraction_failed'] += 1
            return None

        self.metrics['extraction_success'] += 1

        # Step 3: Score confidence
        scoring_result = self.scorer.score_extracted_data(extracted_data, collection)
        field_confidence = {
            field: scores['confidence']
            for field, scores in scoring_result.get('field_scores', {}).items()
        }

        # Step 4: Merge for gaps and fixes
        merged_data, changes = self.shopify.merge_for_gaps_and_fixes(
            existing=shopify_data,
            extracted=extracted_data,
            field_confidence=field_confidence,
            fill_empty=fill_empty,
            fix_errors=fix_errors,
            confidence_threshold=confidence_threshold
        )

        if not changes:
            return {'changes': []}  # No changes needed

        # Count field types
        for change in changes:
            if change.startswith('Filled'):
                self.metrics['fields_filled'] += 1
            elif change.startswith('Fixed'):
                self.metrics['fields_fixed'] += 1

        # Step 5: Validate merged data
        is_valid, errors, warnings = self.validator.validate_product_data(merged_data, collection)

        if not is_valid:
            print(f"    Validation failed:")
            for error in errors:
                print(f"      - {error}")
            self.metrics['validation_failed'] += 1
            return None

        if warnings:
            print(f"    Validation warnings:")
            for warning in warnings:
                print(f"      - {warning}")

        self.metrics['validation_passed'] += 1

        # Step 6: Update Shopify (if not dry run)
        if not self.dry_run:
            try:
                success = self.shopify.update_product(sku, merged_data)
                if success:
                    self.metrics['shopify_updated'] += 1
                else:
                    print(f"    Failed to update Shopify")
                    return None
            except Exception as e:
                print(f"    Shopify update error: {e}")
                return None

        return {'changes': changes}

    def _get_supplier_products(self, limit: int = None) -> List[Dict[str, Any]]:
        """Get products from supplier database."""
        import sqlite3

        # Query supplier_products table for this supplier
        query = """
            SELECT * FROM supplier_products
            WHERE supplier_name = ?
            ORDER BY sku
        """
        params = [self.supplier]

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        conn = sqlite3.connect(self.db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(query, params)

        products = []
        for row in cursor.fetchall():
            product = dict(row)
            products.append(product)

        conn.close()
        return products

    def _save_checkpoint(self):
        """Save checkpoint state."""
        checkpoint_data = {
            'timestamp': datetime.now().isoformat(),
            'supplier': self.supplier,
            'processed_skus': list(self.processed_skus),
            'metrics': self.metrics
        }

        with open(self.checkpoint_file, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)

    def _print_report(self):
        """Print final report."""
        print(f"\n{'='*80}")
        print(f"PROCESSING COMPLETE")
        print(f"{'='*80}\n")

        print(f"Total products: {self.metrics['total_products']}")
        print(f"  Shopify found: {self.metrics['shopify_found']}")
        print(f"  Shopify not found: {self.metrics['shopify_not_found']}")
        print()

        print(f"Extraction:")
        print(f"  Success: {self.metrics['extraction_success']}")
        print(f"  Failed: {self.metrics['extraction_failed']}")
        print()

        print(f"Changes:")
        print(f"  Fields filled: {self.metrics['fields_filled']}")
        print(f"  Fields fixed: {self.metrics['fields_fixed']}")
        print()

        print(f"Validation:")
        print(f"  Passed: {self.metrics['validation_passed']}")
        print(f"  Failed: {self.metrics['validation_failed']}")
        print()

        if not self.dry_run:
            print(f"Shopify updates: {self.metrics['shopify_updated']}")
            print()

        if self.metrics['errors']:
            print(f"Errors: {len(self.metrics['errors'])}")
            for error in self.metrics['errors'][:5]:  # Show first 5
                print(f"  - {error.get('sku', error.get('batch', 'Unknown'))}: {error['error']}")
            if len(self.metrics['errors']) > 5:
                print(f"  ... and {len(self.metrics['errors']) - 5} more")
            print()

        if self.checkpoint_file and os.path.exists(self.checkpoint_file):
            print(f"Checkpoint saved: {self.checkpoint_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Fix existing Shopify products by filling gaps and correcting errors'
    )

    # Product selection
    parser.add_argument('--supplier', type=str, help='Supplier domain (e.g., abey.com.au)')
    parser.add_argument('--sku', type=str, help='Process single product by SKU')
    parser.add_argument('--limit', type=int, help='Limit number of products to process')

    # Processing options
    parser.add_argument('--fill-empty', action='store_true', default=True,
                       help='Fill empty fields with extracted data (default: True)')
    parser.add_argument('--no-fill-empty', action='store_false', dest='fill_empty',
                       help='Do not fill empty fields')
    parser.add_argument('--fix-errors', action='store_true', default=False,
                       help='Fix incorrect data with high-confidence extractions (default: False)')
    parser.add_argument('--confidence-threshold', type=float, default=0.8,
                       help='Minimum confidence to fix existing data (default: 0.8)')
    parser.add_argument('--batch-size', type=int, default=50,
                       help='Number of products per batch (default: 50)')

    # Execution options
    parser.add_argument('--dry-run', action='store_true',
                       help='Run without actually updating Shopify')

    args = parser.parse_args()

    # Validate arguments
    if not args.supplier and not args.sku:
        parser.error('Must specify either --supplier or --sku')

    if args.sku and not args.supplier:
        parser.error('Must specify --supplier when using --sku')

    # Create fixer
    fixer = ProductFixer(
        supplier=args.supplier,
        dry_run=args.dry_run
    )

    # Process products
    if args.sku:
        # Single product mode
        fixer.fix_single_product(
            sku=args.sku,
            fill_empty=args.fill_empty,
            fix_errors=args.fix_errors,
            confidence_threshold=args.confidence_threshold
        )
    else:
        # Batch mode
        fixer.fix_products(
            limit=args.limit,
            fill_empty=args.fill_empty,
            fix_errors=args.fix_errors,
            confidence_threshold=args.confidence_threshold,
            batch_size=args.batch_size
        )


if __name__ == '__main__':
    main()
