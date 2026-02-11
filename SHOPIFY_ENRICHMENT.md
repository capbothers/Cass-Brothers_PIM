# Shopify Product Enrichment Pipeline

Production LLM extraction pipeline that enriches your active Shopify products with supplier specifications.

## Overview

**Target:** 3,795 Shopify products with supplier URLs that need specification data

**Process:**
1. Query Shopify products missing specs but have supplier URLs
2. Extract specifications from supplier websites using Claude LLM
3. Standardize to your metafield schema
4. Validate with confidence scoring
5. Update database with enriched data

**Expected Results:**
- Success rate: ~70-100% (based on test of 20 products)
- Average specs per product: 8-15
- Auto-push rate: 60-70% (confidence ≥0.7)
- Cost: ~$34-76 for all 3,795 products ($0.02-0.05 per product)

## Quick Start

### Test Run (5 products)

```bash
export ANTHROPIC_API_KEY='sk-ant-api03-...'
python scripts/enrich_shopify_products.py --limit 5
```

### Full Production Run

```bash
# All 3,795 products
python scripts/enrich_shopify_products.py

# If interrupted, resume from checkpoint
python scripts/enrich_shopify_products.py --resume
```

## Features

### Progress Tracking
- Real-time progress display
- Checkpoint saves every 10 products
- Full resumption support

### Cost Tracking
- Per-product cost calculation
- Running total
- Final cost report

### Classification System
- **Auto-Push (≥0.7)**: High confidence, ready for Shopify
- **Needs Review (0.3-0.7)**: Medium confidence, manual review
- **Rejected (<0.3)**: Low confidence, insufficient data
- **Skipped**: Category pages or no specs found
- **Failed**: Extraction errors

### Database Updates
Only products classified as "Auto-Push" are updated in the database with:
- All validated specification fields
- `enriched_at`: timestamp
- `enriched_confidence`: average validation confidence

## Output Files

### Checkpoint File
`enrichment_checkpoint_YYYYMMDD_HHMMSS.json`
- Tracks progress for resumption
- Updated every 10 products

### Results File
`enrichment_results_YYYYMMDD_HHMMSS.json`
- Complete extraction results for all products
- Includes raw specs, standardized specs, validation results
- Classification and confidence scores
- Errors and issues
- Cost breakdown

## Example Output

```
================================================================================
SHOPIFY PRODUCT ENRICHMENT PIPELINE
================================================================================

Products to enrich: 3795
Estimated cost: $75.90 - $189.75

[1/3795] Processing ABC-123...
  ✓ auto_push: 12 specs, confidence 0.85, cost $0.0234

[2/3795] Processing ABC-124...
  ⊘ skipped: No specs found (likely category page), cost $0.0089

[3/3795] Processing ABC-125...
  ✓ needs_review: 8 specs, confidence 0.62, cost $0.0198

...

================================================================================
ENRICHMENT COMPLETE
================================================================================

Products Processed: 3795
  ✓ Successful: 2656 (70.0%)
  ⊘ Skipped (category pages): 892
  ✗ Failed: 247

Classification:
  Auto-Push (≥0.7): 1858 products
  Needs Review (0.3-0.7): 798 products

Costs:
  Total: $86.43
  Per Product: $0.0228

Specifications:
  Total Extracted: 29,484
  Average per Product: 11.1

Results saved to: enrichment_results_20260203_123456.json
================================================================================
```

## Workflow After Enrichment

### 1. Review Auto-Push Products (1,858 expected)
These were automatically updated in the database. Check:
```bash
sqlite3 supplier_products.db "
SELECT sku, title, enriched_confidence, overall_width_mm, material, colour_finish
FROM shopify_products
WHERE enriched_at IS NOT NULL
AND enriched_confidence >= 0.7
LIMIT 10
"
```

### 2. Manual Review Queue (798 expected)
Products with 0.3-0.7 confidence need human review:
```python
import json
with open('enrichment_results_TIMESTAMP.json') as f:
    data = json.load(f)
    needs_review = [r for r in data['results']
                   if r['classification'] == 'needs_review']
```

### 3. Failed Products (247 expected)
Review errors and determine next steps:
- Invalid supplier URLs
- Restricted/login-required pages
- Server errors
- Category pages (should be skipped, not failed)

### 4. Push to Shopify
Use existing metafield push system to sync enriched specs:
```bash
# Your existing Shopify sync script
python scripts/push_metafields_to_shopify.py
```

## Technical Details

### Extraction Strategy
1. **Fetch webpage** with proper User-Agent
2. **Parse HTML** - Extract og:description + product content divs
3. **LLM extraction** - Claude Haiku identifies specs from content
4. **LLM standardization** - Converts to your metafield schema
5. **Validation** - Existing confidence scorer validates fields

### Supported Specifications
- Dimensions (width, depth, height in mm)
- Material (standardized names)
- Color/Finish
- Weight (kg)
- Warranty (years)
- Installation type
- Technical specs (tap hole, flow rate, pressure)
- Standards/certifications

### Rate Limiting
- 0.5s between API calls (extraction → standardization)
- 1.0s between products
- ~1 product every 2-3 seconds
- Total runtime: ~2-3 hours for 3,795 products

### Error Handling
- Request timeouts (15s)
- JSON parse errors
- API failures
- Automatic checkpoint saves
- Resume capability

## Cost Breakdown

Based on test results:

| Scenario | Products | Success Rate | Cost per Product | Total Cost |
|----------|----------|--------------|------------------|------------|
| Optimistic | 3,795 | 100% | $0.02 | $75.90 |
| Expected | 3,795 | 70% | $0.025 | $94.88 |
| Conservative | 3,795 | 50% | $0.03 | $113.85 |

**Actual cost depends on:**
- Webpage size (token count)
- Number of specs extracted
- Standardization complexity

## Troubleshooting

### "No specs found" for many products
- Check if URLs are category pages vs product pages
- May need URL filtering/cleaning

### High failure rate
- Check API key validity
- Review error messages in results file
- Supplier websites may block automated requests

### Inconsistent standardization
- Review and refine standardization prompts
- Add more examples for edge cases
- Adjust validation thresholds

## Next Steps

1. **Test run** - 5 products to verify everything works
2. **Review test results** - Check quality of extracted specs
3. **Full production run** - All 3,795 products (~2-3 hours)
4. **Review auto-push products** - Validate quality
5. **Handle review queue** - Manual review medium confidence products
6. **Push to Shopify** - Sync enriched metafields

## Questions?

- How is this different from traditional scraping? → Works on ALL websites, not just JSON-LD
- Why not extract everything at once? → Checkpoint system allows resumption
- What about the 52,066 unmatched products? → Separate project to find/add supplier URLs
