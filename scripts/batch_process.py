"""
Batch Processing Script with Checkpoints

Process large numbers of products in batches with checkpoint saves.
Allows resuming from last checkpoint on failure.

Usage:
    python scripts/batch_process.py --supplier abey.com.au --batch-size 100
    python scripts/batch_process.py --resume checkpoint_20260201_123456.json
"""

import sys
import os
import json
import argparse
from datetime import datetime
from typing import Dict, Any, List
import time
import importlib.util

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _import_module_from_path(module_name: str, relative_path: str):
    """Import a module by file path"""
    module_path = os.path.join(REPO_ROOT, relative_path)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Load environment variables
from dotenv import load_dotenv
load_dotenv(os.path.join(REPO_ROOT, '.env'))

# Import modules
supplier_db_module = _import_module_from_path("supplier_db", os.path.join("core", "supplier_db.py"))
page_extractors_module = _import_module_from_path("page_extractors", os.path.join("core", "page_extractors.py"))
queue_processor_module = _import_module_from_path("queue_processor", os.path.join("core", "queue_processor.py"))
confidence_scorer_module = _import_module_from_path("confidence_scorer", os.path.join("core", "confidence_scorer.py"))
data_validator_module = _import_module_from_path("data_validator", os.path.join("core", "data_validator.py"))
collection_detector_module = _import_module_from_path("collection_detector", os.path.join("core", "collection_detector.py"))

get_supplier_db = supplier_db_module.get_supplier_db
get_page_extractor = page_extractors_module.get_page_extractor
get_confidence_scorer = confidence_scorer_module.get_confidence_scorer
get_data_validator = data_validator_module.get_data_validator


class BatchProcessor:
    """Process products in batches with checkpoint saves"""

    def __init__(self, supplier: str, batch_size: int = 100, dry_run: bool = False):
        self.supplier = supplier
        self.batch_size = batch_size
        self.dry_run = dry_run

        self.db = get_supplier_db()
        self.page_extractor = get_page_extractor()
        self.processor = queue_processor_module.QueueProcessor(None, None, None)
        self.scorer = get_confidence_scorer()
        self.validator = get_data_validator()
        self.detect_collection = collection_detector_module.detect_collection

        self.checkpoint_dir = os.path.join(REPO_ROOT, 'checkpoints')
        os.makedirs(self.checkpoint_dir, exist_ok=True)

        self.state = {
            'supplier': supplier,
            'batch_size': batch_size,
            'started_at': None,
            'last_checkpoint_at': None,
            'processed_count': 0,
            'success_count': 0,
            'error_count': 0,
            'skipped_count': 0,
            'current_batch': 0,
            'total_batches': 0,
            'processed_skus': [],
            'errors': []
        }

    def process_all(self, limit: int = None):
        """Process all products for supplier in batches"""
        print("╔════════════════════════════════════════════════════════════╗")
        print("║  Batch Processor with Checkpoints                          ║")
        print("╚════════════════════════════════════════════════════════════╝\n")

        print(f"Supplier: {self.supplier}")
        print(f"Batch Size: {self.batch_size}")
        print(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}\n")

        # Get all products
        products = self._get_supplier_products(limit)
        if not products:
            print(f"❌ No products found for supplier '{self.supplier}'")
            return

        total_products = len(products)
        self.state['started_at'] = datetime.now().isoformat()
        self.state['total_batches'] = (total_products + self.batch_size - 1) // self.batch_size

        print(f"✅ Found {total_products} products")
        print(f"📦 Will process in {self.state['total_batches']} batches\n")

        # Process in batches
        for batch_num in range(0, total_products, self.batch_size):
            batch = products[batch_num:batch_num + self.batch_size]
            batch_index = (batch_num // self.batch_size) + 1

            self.state['current_batch'] = batch_index
            print(f"\n{'='*60}")
            print(f"BATCH {batch_index}/{self.state['total_batches']} (Products {batch_num+1}-{min(batch_num+self.batch_size, total_products)})")
            print(f"{'='*60}\n")

            try:
                self._process_batch(batch)
            except KeyboardInterrupt:
                print("\n\n⚠️  Interrupted by user, saving checkpoint...")
                self._save_checkpoint()
                print("💾 Checkpoint saved. Resume with --resume flag")
                sys.exit(0)
            except Exception as e:
                print(f"\n❌ Batch {batch_index} failed: {e}")
                self.state['errors'].append({
                    'batch': batch_index,
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                })

            # Save checkpoint after each batch
            self._save_checkpoint()

        # Final report
        self._print_summary()

    def _get_supplier_products(self, limit: int = None):
        """Get supplier products to process"""
        import sqlite3
        conn = sqlite3.connect(self.db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = '''
            SELECT * FROM supplier_products
            WHERE supplier_name LIKE ?
            ORDER BY updated_at DESC
        '''
        params = [f'%{self.supplier}%']

        if limit:
            query += ' LIMIT ?'
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def _process_batch(self, batch: List[Dict[str, Any]]):
        """Process a single batch of products"""
        for i, product in enumerate(batch, 1):
            sku = product['sku']

            # Skip if already processed
            if sku in self.state['processed_skus']:
                print(f"[{i}/{len(batch)}] {sku} - Skipped (already processed)")
                self.state['skipped_count'] += 1
                continue

            print(f"[{i}/{len(batch)}] {sku}...", end=" ")

            try:
                success = self._process_product(product)

                if success:
                    self.state['success_count'] += 1
                    print("✅")
                else:
                    self.state['error_count'] += 1
                    print("❌")

                self.state['processed_count'] += 1
                self.state['processed_skus'].append(sku)

            except Exception as e:
                print(f"❌ Error: {e}")
                self.state['error_count'] += 1
                self.state['errors'].append({
                    'sku': sku,
                    'error': str(e),
                    'batch': self.state['current_batch']
                })

    def _process_product(self, product: Dict[str, Any]) -> bool:
        """Process a single product (page + PDF extraction)"""
        sku = product['sku']
        product_url = product.get('product_url', '')
        spec_sheet_url = product.get('spec_sheet_url', '')
        title = product.get('product_name', '')
        supplier_name = product.get('supplier_name', '')

        # Detect collection
        collection = product.get('detected_collection')
        if not collection:
            detected_collection, _confidence = self.detect_collection(title, product_url)
            collection = detected_collection or 'sinks'

        extracted_data = {}

        # Step 1: Try page extraction
        if product_url:
            page_specs = self.page_extractor.extract_specs(product_url, supplier_hint=self.supplier)
            if page_specs:
                extracted_data.update(page_specs)

        # Step 2: Try PDF extraction for missing fields
        if spec_sheet_url:
            result = self.processor.extract_from_spec_sheet(
                spec_sheet_url,
                collection,
                product_title=title,
                vendor=supplier_name
            )

            if result.success:
                pdf_data = result.extracted_data or result.raw_extraction or {}
                # Merge: page specs take precedence
                for key, value in pdf_data.items():
                    if key not in extracted_data or not extracted_data[key]:
                        extracted_data[key] = value

        if not extracted_data:
            return False

        # Step 3: Validate data
        is_valid, errors, warnings = self.validator.validate_product_data(extracted_data, collection)

        if not is_valid:
            print(f"⚠️  Validation failed: {'; '.join(errors)}")
            return False

        # Step 4: Score confidence
        scored = self.scorer.score_extracted_data(extracted_data, collection)

        # Step 5: Save to processing queue (if not dry-run)
        if not self.dry_run:
            # Check for existing queue entry (deduplication)
            queue_id, created = self.db.get_or_create_processing_queue(
                sku,
                {
                    'variant_sku': sku,
                    'title': title,
                    'vendor': supplier_name,
                    'shopify_spec_sheet': spec_sheet_url,
                },
                target_collection=collection
            )

            # Update with extracted data
            self.db.update_processing_queue_extracted_data(queue_id, extracted_data)
            self.db.update_processing_queue_confidence(queue_id, scored)

        return True

    def _save_checkpoint(self):
        """Save current processing state to checkpoint file"""
        self.state['last_checkpoint_at'] = datetime.now().isoformat()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        checkpoint_file = os.path.join(
            self.checkpoint_dir,
            f"checkpoint_{self.supplier.replace('.', '_')}_{timestamp}.json"
        )

        with open(checkpoint_file, 'w') as f:
            json.dump(self.state, f, indent=2)

        print(f"\n💾 Checkpoint saved: {checkpoint_file}")

    def _print_summary(self):
        """Print final summary"""
        print("\n" + "="*60)
        print("BATCH PROCESSING COMPLETE")
        print("="*60)
        print(f"\n📊 Summary:")
        print(f"  Total Processed: {self.state['processed_count']}")
        print(f"  ✅ Success: {self.state['success_count']}")
        print(f"  ❌ Errors: {self.state['error_count']}")
        print(f"  ⏭️  Skipped: {self.state['skipped_count']}")

        if self.state['errors']:
            print(f"\n❌ Errors ({len(self.state['errors'])}):")
            for err in self.state['errors'][:10]:
                print(f"  • {err.get('sku', 'Unknown')}: {err['error']}")
            if len(self.state['errors']) > 10:
                print(f"  ... and {len(self.state['errors']) - 10} more")


def main():
    parser = argparse.ArgumentParser(
        description='Batch process products with checkpoints'
    )
    parser.add_argument(
        '--supplier',
        type=str,
        help='Supplier domain (e.g., abey.com.au)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Products per batch (default: 100)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit total products to process'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview without database changes'
    )
    parser.add_argument(
        '--resume',
        type=str,
        help='Resume from checkpoint file'
    )

    args = parser.parse_args()

    if args.resume:
        print("❌ Resume functionality not yet implemented")
        print("   Will be added in next iteration")
        sys.exit(1)

    if not args.supplier:
        print("❌ Error: --supplier required")
        sys.exit(1)

    processor = BatchProcessor(
        supplier=args.supplier,
        batch_size=args.batch_size,
        dry_run=args.dry_run
    )

    processor.process_all(limit=args.limit)


if __name__ == "__main__":
    main()
