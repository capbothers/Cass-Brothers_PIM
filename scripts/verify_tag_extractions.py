#!/usr/bin/env python3
"""
Verify tag extractions using LLM spot-checking.

Takes a sample of extracted values and verifies them against product titles
using Claude Haiku. Reports accuracy and flags suspicious extractions.

Usage:
    python scripts/verify_tag_extractions.py [--sample-size 50] [--collection COLLECTION]
"""

import sqlite3
import argparse
import os
import json
import random
from dotenv import load_dotenv
from anthropic import Anthropic

# Load environment variables
load_dotenv()

# Initialize Anthropic client
client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))


def verify_with_llm(products: list) -> dict:
    """
    Use Claude Haiku to verify tag extractions.

    Returns a dict with accuracy metrics and flagged products.
    """
    # Build verification prompt
    product_data = []
    for p in products:
        product_data.append({
            'sku': p['sku'],
            'title': p['title'],
            'extracted_colour': p.get('extracted_colour'),
            'extracted_mounting': p.get('extracted_mounting'),
            'extracted_material': p.get('extracted_material'),
        })

    prompt = f"""You are verifying data extracted from Shopify product tags against product titles.

For each product below, verify if the extracted values make sense for the product title.
Score each extraction as: correct, incorrect, or uncertain.

Products to verify:
{json.dumps(product_data, indent=2)}

Return a JSON array with your verification for each product:
[
  {{
    "sku": "...",
    "colour_correct": true/false/null,
    "colour_notes": "explanation if incorrect",
    "mounting_correct": true/false/null,
    "mounting_notes": "explanation if incorrect",
    "material_correct": true/false/null,
    "material_notes": "explanation if incorrect"
  }},
  ...
]

Use null if there was no extracted value to verify.
Be strict - if the extraction doesn't clearly match the title, mark it incorrect.
"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    # Extract JSON from response
    text = response.content[0].text

    # Try to find JSON in the response
    try:
        # Look for JSON array
        start = text.find('[')
        end = text.rfind(']') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except json.JSONDecodeError:
        pass

    return []


def main():
    parser = argparse.ArgumentParser(description='Verify tag extractions with LLM')
    parser.add_argument('--sample-size', type=int, default=50, help='Number of products to sample')
    parser.add_argument('--collection', type=str, help='Limit to specific super_category')
    args = parser.parse_args()

    conn = sqlite3.connect('supplier_products.db')
    cursor = conn.cursor()

    # Get products with recent tag extractions (have colour but may have been from tags)
    query = """
        SELECT id, sku, title, tags, colour_finish, installation_type, material
        FROM shopify_products
        WHERE status = 'active'
        AND tags IS NOT NULL AND tags != ''
        AND colour_finish IS NOT NULL
    """
    params = []

    if args.collection:
        query += " AND super_category = ?"
        params.append(args.collection)

    cursor.execute(query, params)
    products = cursor.fetchall()
    conn.close()

    print("=" * 80)
    print("TAG EXTRACTION VERIFICATION")
    print("=" * 80)
    print(f"\nProducts with tag-based extractions: {len(products)}")
    print(f"Sample size: {args.sample_size}")

    if len(products) == 0:
        print("No products to verify.")
        return

    # Random sample
    sample_size = min(args.sample_size, len(products))
    sample = random.sample(products, sample_size)

    # Prepare for verification
    to_verify = []
    for row in sample:
        pid, sku, title, tags, colour, mounting, material = row

        # Extract what was in the tags for comparison
        import re
        raw_colour = None
        raw_mounting = None
        raw_material = None

        colour_match = re.search(r'colour:\s*([^,]+)', tags, re.IGNORECASE)
        if colour_match:
            raw_colour = colour_match.group(1).strip()

        mounting_match = re.search(r'Mounting:\s*([^,]+)', tags, re.IGNORECASE)
        if mounting_match:
            raw_mounting = mounting_match.group(1).strip()

        material_match = re.search(r'Material:\s*([^,]+)', tags, re.IGNORECASE)
        if material_match:
            raw_material = material_match.group(1).strip()

        to_verify.append({
            'id': pid,
            'sku': sku,
            'title': title,
            'extracted_colour': colour,
            'extracted_mounting': mounting,
            'extracted_material': material,
            'raw_colour_tag': raw_colour,
            'raw_mounting_tag': raw_mounting,
            'raw_material_tag': raw_material,
        })

    # Verify in batches of 10
    all_verifications = []
    batch_size = 10

    print(f"\nVerifying {sample_size} products with LLM...")

    for i in range(0, len(to_verify), batch_size):
        batch = to_verify[i:i + batch_size]
        print(f"  Processing batch {i // batch_size + 1}/{(len(to_verify) + batch_size - 1) // batch_size}...")

        verifications = verify_with_llm(batch)
        all_verifications.extend(verifications)

    # Analyze results
    colour_correct = 0
    colour_incorrect = 0
    colour_checked = 0

    mounting_correct = 0
    mounting_incorrect = 0
    mounting_checked = 0

    material_correct = 0
    material_incorrect = 0
    material_checked = 0

    flagged = []

    for v in all_verifications:
        if v.get('colour_correct') is True:
            colour_correct += 1
            colour_checked += 1
        elif v.get('colour_correct') is False:
            colour_incorrect += 1
            colour_checked += 1
            flagged.append(v)

        if v.get('mounting_correct') is True:
            mounting_correct += 1
            mounting_checked += 1
        elif v.get('mounting_correct') is False:
            mounting_incorrect += 1
            mounting_checked += 1
            if v not in flagged:
                flagged.append(v)

        if v.get('material_correct') is True:
            material_correct += 1
            material_checked += 1
        elif v.get('material_correct') is False:
            material_incorrect += 1
            material_checked += 1
            if v not in flagged:
                flagged.append(v)

    # Results
    print(f"\n--- VERIFICATION RESULTS ---")

    if colour_checked > 0:
        colour_accuracy = colour_correct / colour_checked * 100
        print(f"\nColour extraction accuracy: {colour_correct}/{colour_checked} = {colour_accuracy:.1f}%")

    if mounting_checked > 0:
        mounting_accuracy = mounting_correct / mounting_checked * 100
        print(f"Mounting extraction accuracy: {mounting_correct}/{mounting_checked} = {mounting_accuracy:.1f}%")

    if material_checked > 0:
        material_accuracy = material_correct / material_checked * 100
        print(f"Material extraction accuracy: {material_correct}/{material_checked} = {material_accuracy:.1f}%")

    if flagged:
        print(f"\n--- FLAGGED PRODUCTS ({len(flagged)}) ---")
        for v in flagged[:20]:
            print(f"\n  {v.get('sku')}:")
            if v.get('colour_correct') is False:
                print(f"    Colour: {v.get('colour_notes', 'incorrect')}")
            if v.get('mounting_correct') is False:
                print(f"    Mounting: {v.get('mounting_notes', 'incorrect')}")
            if v.get('material_correct') is False:
                print(f"    Material: {v.get('material_notes', 'incorrect')}")

    # Overall assessment
    total_checked = colour_checked + mounting_checked + material_checked
    total_correct = colour_correct + mounting_correct + material_correct

    if total_checked > 0:
        overall_accuracy = total_correct / total_checked * 100
        print(f"\n--- OVERALL ---")
        print(f"Overall accuracy: {total_correct}/{total_checked} = {overall_accuracy:.1f}%")

        if overall_accuracy >= 95:
            print("\n✓ Extractions look accurate - safe to apply")
        elif overall_accuracy >= 85:
            print("\n⚠ Some issues detected - review flagged products")
        else:
            print("\n✗ Significant issues - review extraction logic")


if __name__ == '__main__':
    main()
