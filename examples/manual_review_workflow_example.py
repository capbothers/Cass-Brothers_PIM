"""
Example: Complete Manual Review Workflow

Demonstrates the end-to-end manual review process:
1. Extract data and score confidence
2. Export low-confidence fields to CSV
3. (Human reviews CSV manually)
4. Import reviewed CSV
5. Merge reviewed and extracted data
"""

import sys
import os
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.supplier_db import get_supplier_db
from core.confidence_scorer import get_confidence_scorer
from scripts.export_review_queue import export_review_queue
from scripts.import_review_queue import merge_reviewed_and_extracted


def example_full_workflow():
    """Demonstrate complete workflow from extraction to final data"""
    print("╔════════════════════════════════════════════════════════════╗")
    print("║  Manual Review Workflow Example                           ║")
    print("╚════════════════════════════════════════════════════════════╝\n")

    db = get_supplier_db()
    scorer = get_confidence_scorer(threshold=0.6)

    # Simulate a processing queue item with extracted data
    print("Step 1: Simulating AI Extraction\n")
    print("─" * 60)

    simulated_extracted_data = {
        "length_mm": "450",
        "width_mm": "380",
        "depth_mm": "200",
        "material": "304 Stainless Steel",
        "installation_type": "Undermount",
        "bowl_count": "1",
        "estimated_weight": "approximately 8kg",  # Low confidence - guess
        "finish": "Brushed",  # Medium-low confidence - vague
        "warranty": "10 year",
        "unknown_dimension": "TBD"  # Very low confidence - placeholder
    }

    print("Extracted Data:")
    for field, value in simulated_extracted_data.items():
        print(f"  • {field}: {value}")

    # Score confidence
    print("\n" + "─" * 60)
    print("Step 2: Confidence Scoring\n")

    scored = scorer.score_extracted_data(simulated_extracted_data, collection_name='sinks')

    print(f"Overall Confidence: {scored['overall_confidence']:.2%}\n")

    print(f"✅ Auto-Apply Fields ({len(scored['auto_apply_fields'])} fields):")
    for field in scored['auto_apply_fields']:
        conf = scored['field_scores'][field]['confidence']
        print(f"  • {field}: {conf:.2f}")

    print(f"\n⚠️  Needs Review ({len(scored['review_fields'])} fields):")
    for field in scored['review_fields']:
        conf = scored['field_scores'][field]['confidence']
        value = scored['field_scores'][field]['value']
        print(f"  • {field}: {conf:.2f} - '{value}'")

    # Simulate storing in database
    print("\n" + "─" * 60)
    print("Step 3: Store in Processing Queue\n")

    # This would normally be done by queue_processor.py
    print("Would execute:")
    print("  db.update_processing_queue_extracted_data(queue_id, extracted_data)")
    print("  db.update_processing_queue_confidence(queue_id, scored)")

    # Export review queue
    print("\n" + "─" * 60)
    print("Step 4: Export Review Queue\n")

    print("Would execute:")
    print("  python scripts/export_review_queue.py")
    print("\nThis creates a CSV with low-confidence fields:")
    print("  review_queue_YYYYMMDD_HHMMSS.csv\n")

    print("CSV would contain:")
    print("  queue_id | sku | field_name | extracted_value | confidence | approved_value | notes")
    print("  ─" * 70)
    for field in scored['review_fields']:
        conf = scored['field_scores'][field]['confidence']
        value = scored['field_scores'][field]['value']
        print(f"  123 | ABC-123 | {field} | {value} | {conf:.3f} | [TO FILL] | [NOTES]")

    # Simulate human review
    print("\n" + "─" * 60)
    print("Step 5: Human Review (Manual)\n")

    print("Human reviewer opens CSV in Excel/Google Sheets and fills in:")
    print("  • estimated_weight: 'approximately 8kg' → '8.5'")
    print("  • finish: 'Brushed' → 'Brushed Chrome'")
    print("  • unknown_dimension: 'TBD' → (left empty - skip)")

    # Simulate reviewed data
    simulated_reviewed_data = {
        "estimated_weight": "8.5",
        "finish": "Brushed Chrome"
    }

    # Import reviewed data
    print("\n" + "─" * 60)
    print("Step 6: Import Reviewed CSV\n")

    print("Would execute:")
    print("  python scripts/import_review_queue.py review_queue_20260201.csv")
    print("\nThis updates processing_queue.reviewed_data with:")
    print(f"  {json.dumps(simulated_reviewed_data, indent=2)}")

    # Merge final data
    print("\n" + "─" * 60)
    print("Step 7: Merge for Shopify Push\n")

    # Simulate merging
    final_data = simulated_extracted_data.copy()
    final_data.update(simulated_reviewed_data)  # Reviewed takes precedence

    # Remove low-confidence fields that weren't reviewed
    final_data = {k: v for k, v in final_data.items() if k not in scored['review_fields'] or k in simulated_reviewed_data}

    print("Final merged data (for Shopify):")
    for field, value in final_data.items():
        source = "REVIEWED" if field in simulated_reviewed_data else "AUTO"
        print(f"  • {field}: {value} [{source}]")

    print("\n" + "─" * 60)
    print("Summary\n")

    auto_count = len(scored['auto_apply_fields'])
    review_count = len(scored['review_fields'])
    reviewed_count = len(simulated_reviewed_data)
    skipped_count = review_count - reviewed_count

    print(f"  Total fields extracted: {len(simulated_extracted_data)}")
    print(f"  ✅ Auto-applied: {auto_count} ({auto_count/len(simulated_extracted_data)*100:.0f}%)")
    print(f"  ⚠️  Needed review: {review_count} ({review_count/len(simulated_extracted_data)*100:.0f}%)")
    print(f"  ✏️  Reviewed by human: {reviewed_count}")
    print(f"  ⏭️  Skipped: {skipped_count}")
    print(f"  📤 Final fields to Shopify: {len(final_data)}")


def example_query_review_queue():
    """Example: Check how many items need review"""
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║  Query Review Queue Status                                ║")
    print("╚════════════════════════════════════════════════════════════╝\n")

    db = get_supplier_db()

    # Get items needing review
    items = db.get_items_needing_review(confidence_threshold=0.6)

    if not items:
        print("✅ No items need review!")
        return

    print(f"⚠️  Found {len(items)} items needing review:\n")

    for item in items[:5]:  # Show first 5
        sku = item['sku']
        collection = item['target_collection']

        # Parse confidence summary
        conf_summary = {}
        if item.get('confidence_summary'):
            try:
                conf_summary = json.loads(item['confidence_summary'])
            except (json.JSONDecodeError, TypeError):
                pass

        overall = conf_summary.get('overall', 0)
        review_count = conf_summary.get('review_count', 0)

        print(f"  • {sku} ({collection})")
        print(f"    Overall Confidence: {overall:.2%}")
        print(f"    Fields Needing Review: {review_count}")
        print()

    if len(items) > 5:
        print(f"  ... and {len(items) - 5} more")

    print("\nTo export for review:")
    print("  python scripts/export_review_queue.py")


if __name__ == "__main__":
    # Run example workflow
    example_full_workflow()

    # Query review queue
    # example_query_review_queue()  # Commented out - requires DB with data

    print("\n✅ Example complete!")
    print("\nNext steps:")
    print("  1. Run migration: python migrations/add_reviewed_data_field.py")
    print("  2. Process some products through extraction pipeline")
    print("  3. Export review queue: python scripts/export_review_queue.py")
    print("  4. Review CSV in Excel/Google Sheets")
    print("  5. Import reviewed CSV: python scripts/import_review_queue.py <file>")
