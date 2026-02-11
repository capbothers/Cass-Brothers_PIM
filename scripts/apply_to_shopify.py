"""
Apply Updates to Shopify

Pushes high-confidence and reviewed fields to Shopify via API.

Usage:
    python scripts/apply_to_shopify.py --queue-id 123
    python scripts/apply_to_shopify.py --sku ABC-123 --dry-run
    python scripts/apply_to_shopify.py --collection sinks --limit 10
"""

import sys
import os
import json
import argparse
from typing import Dict, Any, List, Optional
import importlib.util

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
shopify_manager_module = _import_module_from_path("shopify_manager", os.path.join("core", "shopify_manager.py"))
confidence_scorer_module = _import_module_from_path("confidence_scorer", os.path.join("core", "confidence_scorer.py"))

get_supplier_db = supplier_db_module.get_supplier_db
ShopifyManager = shopify_manager_module.ShopifyManager
get_confidence_scorer = confidence_scorer_module.get_confidence_scorer


def merge_fields_for_shopify(queue_id: int, confidence_threshold: float = 0.6) -> Dict[str, Any]:
    """
    Merge extracted_data and reviewed_data, applying confidence filtering

    Priority:
    1. Reviewed data (always included)
    2. Extracted data with confidence >= threshold

    Args:
        queue_id: Processing queue ID
        confidence_threshold: Only include extracted fields >= this confidence

    Returns:
        Dict with:
        {
            "fields": {...},  # Merged fields ready for Shopify
            "auto_applied": [...],  # Field names auto-applied
            "reviewed_applied": [...],  # Field names from review
            "skipped": [...]  # Low-confidence fields not applied
        }
    """
    db = get_supplier_db()
    item = db.get_processing_queue_item(queue_id)

    if not item:
        raise ValueError(f"Queue item {queue_id} not found")

    # Parse extracted data
    extracted_data = {}
    if item.get('extracted_data'):
        try:
            extracted_data = json.loads(item['extracted_data'])
        except (json.JSONDecodeError, TypeError):
            pass

    # Parse reviewed data
    reviewed_data = {}
    if item.get('reviewed_data'):
        try:
            reviewed_data = json.loads(item['reviewed_data'])
        except (json.JSONDecodeError, TypeError):
            pass

    # Parse confidence summary
    confidence_summary = {}
    if item.get('confidence_summary'):
        try:
            confidence_summary = json.loads(item['confidence_summary'])
        except (json.JSONDecodeError, TypeError):
            pass

    field_scores = confidence_summary.get('field_scores', {})

    # Start with empty fields
    final_fields = {}
    auto_applied = []
    reviewed_applied = []
    skipped = []

    # Add high-confidence extracted fields
    for field, value in extracted_data.items():
        # Check confidence
        field_score = field_scores.get(field, {})
        confidence = field_score.get('confidence', 0.0)

        if confidence >= confidence_threshold:
            final_fields[field] = value
            auto_applied.append(field)
        else:
            skipped.append(field)

    # Override with reviewed data (always included, regardless of confidence)
    for field, value in reviewed_data.items():
        if field in final_fields and field in auto_applied:
            auto_applied.remove(field)  # Was auto, now reviewed
        final_fields[field] = value
        if field not in reviewed_applied:
            reviewed_applied.append(field)

    return {
        "fields": final_fields,
        "auto_applied": auto_applied,
        "reviewed_applied": reviewed_applied,
        "skipped": skipped
    }


def apply_to_shopify_api(queue_id: int, dry_run: bool = False, confidence_threshold: float = 0.6) -> Dict[str, Any]:
    """
    Apply merged fields to Shopify product via API

    Args:
        queue_id: Processing queue ID
        dry_run: If True, show what would be updated without making changes
        confidence_threshold: Only auto-apply fields >= this confidence

    Returns:
        Dict with update result
    """
    db = get_supplier_db()
    item = db.get_processing_queue_item(queue_id)

    if not item:
        raise ValueError(f"Queue item {queue_id} not found")

    sku = item['sku']
    shopify_product_id = item.get('shopify_product_id')

    if not shopify_product_id:
        raise ValueError(f"SKU {sku} has no shopify_product_id")

    # Merge fields
    merged = merge_fields_for_shopify(queue_id, confidence_threshold)

    fields = merged['fields']
    auto_applied = merged['auto_applied']
    reviewed_applied = merged['reviewed_applied']
    skipped = merged['skipped']

    if not fields:
        print(f"⚠️  No fields to apply for {sku}")
        return {
            'success': False,
            'reason': 'no_fields',
            'sku': sku
        }

    # Show what will be updated
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Applying to Shopify: {sku} (Product ID: {shopify_product_id})")
    print(f"{'─' * 60}")

    print(f"\n✅ Auto-Applied Fields ({len(auto_applied)}):")
    for field in auto_applied:
        value = fields[field]
        print(f"  • {field}: {value}")

    print(f"\n✏️  Reviewed Fields ({len(reviewed_applied)}):")
    for field in reviewed_applied:
        value = fields[field]
        print(f"  • {field}: {value}")

    if skipped:
        print(f"\n⏭️  Skipped (Low Confidence) ({len(skipped)}):")
        for field in skipped[:5]:  # Show first 5
            print(f"  • {field}")
        if len(skipped) > 5:
            print(f"  ... and {len(skipped) - 5} more")

    if dry_run:
        print(f"\n💡 Run without --dry-run to apply changes")
        return {
            'success': True,
            'dry_run': True,
            'sku': sku,
            'fields_count': len(fields)
        }

    # Actually update Shopify
    try:
        from core.shopify_manager import ShopifyManager
        shopify = ShopifyManager()

        # Update product
        # Note: This assumes shopify_manager.update_product() exists
        # You may need to adapt this to your actual Shopify integration
        result = shopify.update_product(shopify_product_id, fields)

        # Track what was applied
        db.update_processing_queue_applied_fields(queue_id, {
            "fields": list(fields.keys()),
            "auto_applied": auto_applied,
            "reviewed_applied": reviewed_applied,
            "timestamp": "CURRENT_TIMESTAMP"
        })

        print(f"\n✅ Successfully updated Shopify product {shopify_product_id}")

        return {
            'success': True,
            'sku': sku,
            'product_id': shopify_product_id,
            'fields_applied': len(fields),
            'auto_applied_count': len(auto_applied),
            'reviewed_count': len(reviewed_applied)
        }

    except Exception as e:
        print(f"\n❌ Error updating Shopify: {e}")
        return {
            'success': False,
            'error': str(e),
            'sku': sku
        }


def apply_batch(queue_ids: List[int] = None, collection: str = None, limit: int = None,
                dry_run: bool = False, confidence_threshold: float = 0.6,
                run_id: str = None) -> Dict[str, Any]:
    """
    Apply multiple queue items to Shopify

    Args:
        queue_ids: Specific queue IDs to process
        collection: Process all items in this collection
        limit: Max number of items to process
        dry_run: Preview mode
        confidence_threshold: Confidence threshold

    Returns:
        Summary dict
    """
    db = get_supplier_db()

    # Get items to process
    if queue_ids:
        items = [db.get_processing_queue_item(qid) for qid in queue_ids]
        items = [i for i in items if i is not None]
    elif collection:
        result = db.get_processing_queue(collection=collection, status='ready', limit=limit or 100)
        items = result['items']
    else:
        result = db.get_processing_queue(status='ready', limit=limit or 50)
        items = result['items']
    if run_id:
        # When run_id is provided, ignore status gating
        conn_items = db.get_processing_queue(status=None, limit=limit or 500)
        items = [i for i in conn_items['items'] if i and i.get('run_id') == run_id]

    if not items:
        print("⚠️  No items to process")
        return {'total': 0, 'success': 0, 'failed': 0}

    print(f"{'[DRY RUN] ' if dry_run else ''}Processing {len(items)} items...\n")

    results = {
        'total': len(items),
        'success': 0,
        'failed': 0,
        'errors': []
    }

    for item in items:
        queue_id = item['id']
        try:
            result = apply_to_shopify_api(queue_id, dry_run=dry_run, confidence_threshold=confidence_threshold)
            if result.get('success'):
                results['success'] += 1
            else:
                results['failed'] += 1
                results['errors'].append({
                    'sku': item['sku'],
                    'error': result.get('error', result.get('reason', 'unknown'))
                })
        except Exception as e:
            print(f"❌ Error processing {item['sku']}: {e}")
            results['failed'] += 1
            results['errors'].append({
                'sku': item['sku'],
                'error': str(e)
            })

    print(f"\n{'─' * 60}")
    print(f"Summary:")
    print(f"  Total: {results['total']}")
    print(f"  ✅ Success: {results['success']}")
    print(f"  ❌ Failed: {results['failed']}")

    if results['errors']:
        print(f"\nErrors:")
        for err in results['errors'][:5]:
            print(f"  • {err['sku']}: {err['error']}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Apply updates to Shopify with confidence filtering'
    )
    parser.add_argument(
        '--queue-id',
        type=int,
        help='Process specific queue ID'
    )
    parser.add_argument(
        '--sku',
        help='Process specific SKU'
    )
    parser.add_argument(
        '--collection',
        help='Process all items in collection (e.g., sinks, taps)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=50,
        help='Max items to process (default: 50)'
    )
    parser.add_argument(
        '--threshold',
        type=float,
        default=0.6,
        help='Confidence threshold for auto-apply (default: 0.6)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without applying'
    )
    parser.add_argument(
        '--run-id',
        help='Only process items from a specific run_id'
    )

    args = parser.parse_args()

    print("╔════════════════════════════════════════════════════════════╗")
    print("║  Apply to Shopify - Conditional Auto-Apply                ║")
    print("╚════════════════════════════════════════════════════════════╝\n")

    try:
        if args.queue_id:
            # Single item by queue ID
            result = apply_to_shopify_api(
                args.queue_id,
                dry_run=args.dry_run,
                confidence_threshold=args.threshold
            )
        elif args.sku:
            # Single item by SKU
            db = get_supplier_db()
            item = db.get_processing_queue_by_sku(args.sku)
            if not item:
                print(f"❌ SKU {args.sku} not found in processing queue")
                sys.exit(1)
            result = apply_to_shopify_api(
                item['id'],
                dry_run=args.dry_run,
                confidence_threshold=args.threshold
            )
        else:
            # Batch processing
            result = apply_batch(
                collection=args.collection,
                limit=args.limit,
                dry_run=args.dry_run,
                confidence_threshold=args.threshold,
                run_id=args.run_id
            )

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
