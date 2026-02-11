"""
Example: Spec Sheet Discovery and Confidence Scoring Pipeline

This example demonstrates the complete workflow:
1. Discover spec sheet URLs on supplier product pages
2. Extract data from spec sheets (using existing queue_processor)
3. Score confidence of extracted fields
4. Split into auto-apply vs manual review
"""

import sys
import os
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.supplier_db import get_supplier_db
from core.spec_sheet_scraper import get_spec_sheet_scraper
from core.confidence_scorer import get_confidence_scorer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def example_discover_spec_sheets():
    """Example: Discover spec sheet URLs for products without them"""
    logger.info("=== EXAMPLE 1: Spec Sheet Discovery ===\n")

    db = get_supplier_db()
    scraper = get_spec_sheet_scraper()

    # Get products without spec sheets
    products = db.get_products_without_spec_sheets(limit=10)
    logger.info(f"Found {len(products)} products without spec sheets\n")

    if not products:
        logger.info("No products need spec sheet discovery. Import some products first!\n")
        return

    # Batch scrape
    results = scraper.batch_scrape(products, rate_limit=1.0)

    logger.info(f"\n📊 Discovery Results:")
    logger.info(f"   Total: {results['total']}")
    logger.info(f"   ✅ Found: {results['found']}")
    logger.info(f"   ⚠️  Not Found: {results['not_found']}")
    logger.info(f"   ❌ Errors: {results['errors']}\n")

    if results['found_skus']:
        logger.info(f"SKUs with spec sheets found:")
        for sku in results['found_skus'][:5]:  # Show first 5
            logger.info(f"   - {sku}")


def example_score_extraction():
    """Example: Score confidence of extracted data"""
    logger.info("\n=== EXAMPLE 2: Confidence Scoring ===\n")

    # Sample extracted data (simulating AI extraction results)
    extracted_data = {
        "length_mm": "450",
        "overall_width_mm": "380",
        "overall_depth_mm": "200",
        "material": "304 Stainless Steel",
        "installation_type": "Undermount",
        "bowl_count": "1",
        "warranty": "10 year",
        "finish": "Brushed Chrome",
        "product_description": "This is a high-quality kitchen sink...",  # Free text
        "estimated_weight": "approximately 8kg",  # Contains "approximately" - low confidence
        "unknown_field": "TBD"  # Placeholder - very low confidence
    }

    scorer = get_confidence_scorer(threshold=0.6)
    result = scorer.score_extracted_data(extracted_data, collection_name='sinks')

    logger.info(f"Overall Confidence: {result['overall_confidence']:.2%}\n")
    logger.info(f"Summary: {result['summary']}\n")

    logger.info("Field Scores:")
    for field, score_data in result['field_scores'].items():
        status = "✅ AUTO" if score_data['auto_apply'] else "⚠️  REVIEW"
        logger.info(f"   {status} {field}: {score_data['confidence']:.2f} - {score_data['value']}")

    logger.info(f"\n✅ Auto-Apply Fields ({len(result['auto_apply_fields'])}):")
    for field, value in result['auto_apply_fields'].items():
        logger.info(f"   - {field}: {value}")

    logger.info(f"\n⚠️  Manual Review Required ({len(result['review_fields'])}):")
    for field, value in result['review_fields'].items():
        logger.info(f"   - {field}: {value}")


def example_reject_guessed_fields():
    """Example: Filter out guessed/low-confidence fields"""
    logger.info("\n=== EXAMPLE 3: Reject Guessed Fields ===\n")

    extracted_data = {
        "length_mm": "450",  # High confidence - keep
        "width_mm": "approx 380",  # Guessed - reject
        "material": "Stainless Steel",  # High confidence - keep
        "finish": "estimated to be Chrome",  # Guessed - reject
        "weight": "about 5kg"  # Guessed - reject
    }

    scorer = get_confidence_scorer()
    filtered = scorer.reject_guessed_fields(extracted_data)

    logger.info("Original Data:")
    for field, value in extracted_data.items():
        logger.info(f"   - {field}: {value}")

    logger.info("\nFiltered Data (guesses removed):")
    for field, value in filtered.items():
        logger.info(f"   ✅ {field}: {value}")

    logger.info(f"\n{len(filtered)}/{len(extracted_data)} fields passed confidence threshold")


def example_complete_workflow():
    """Example: Complete workflow from discovery to scoring"""
    logger.info("\n=== EXAMPLE 4: Complete Workflow ===\n")

    db = get_supplier_db()

    # Step 1: Get a product from processing queue
    queue_items = db.get_processing_queue(status='pending', limit=1)

    if not queue_items['items']:
        logger.info("No items in processing queue. Add some products first!")
        return

    item = queue_items['items'][0]
    logger.info(f"Processing: {item['sku']} - {item['title']}\n")

    # Step 2: Simulate extracted data (in real workflow, this comes from queue_processor)
    simulated_extraction = {
        "length_mm": "1200",
        "width_mm": "600",
        "material": "Vitreous China",
        "installation_type": "Wall Hung",
        "wels_rating": "4 star"
    }

    logger.info("Simulated Extraction:")
    for field, value in simulated_extraction.items():
        logger.info(f"   - {field}: {value}")

    # Step 3: Score confidence
    scorer = get_confidence_scorer()
    scored = scorer.score_extracted_data(simulated_extraction, item['target_collection'])

    logger.info(f"\n📊 Confidence: {scored['overall_confidence']:.2%}")
    logger.info(f"   {scored['summary']}\n")

    # Step 4: Update database with confidence summary
    confidence_summary = {
        "overall": scored['overall_confidence'],
        "auto_apply_count": len(scored['auto_apply_fields']),
        "review_count": len(scored['review_fields']),
        "threshold": scorer.threshold
    }

    db.update_processing_queue_confidence(item['id'], confidence_summary)
    logger.info(f"✅ Updated queue item {item['id']} with confidence summary\n")


if __name__ == "__main__":
    print("╔════════════════════════════════════════════════════════════════╗")
    print("║  Spec Sheet Discovery & Confidence Scoring Examples           ║")
    print("╚════════════════════════════════════════════════════════════════╝\n")

    # Run examples
    try:
        # Example 1: Discover spec sheets
        # example_discover_spec_sheets()  # Commented out to avoid hitting real URLs

        # Example 2: Score extracted data
        example_score_extraction()

        # Example 3: Reject guessed fields
        example_reject_guessed_fields()

        # Example 4: Complete workflow
        # example_complete_workflow()  # Commented out - requires DB setup

        print("\n✅ All examples completed successfully!")

    except Exception as e:
        logger.error(f"Error running examples: {e}", exc_info=True)
