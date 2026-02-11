# LLM Extraction Test Pipeline

## What This Does

Tests LLM-based spec extraction on 10-20 sample products before scaling to production.

**Test Flow:**
```
1. Select 15 diverse products from different suppliers
2. Extract specs using LLM (Claude API + web browsing)
3. Standardize to your metafield schema using LLM
4. Validate with existing confidence scorer
5. Generate report with success rates and costs
```

## Setup

### 1. Get Anthropic API Key

```bash
# Sign up at https://console.anthropic.com/
# Get your API key
export ANTHROPIC_API_KEY='sk-ant-...'
```

### 2. Run Test

```bash
# Test with 15 products (default)
python scripts/test_llm_extraction.py

# Test with custom sample size
python scripts/test_llm_extraction.py --samples 20

# Pass API key directly
python scripts/test_llm_extraction.py --api-key 'sk-ant-...'
```

## What The Test Will Show

### Success Metrics:
- ✅ **Extraction success rate** - % of products where specs were found
- ✅ **Spec count** - Average number of specs extracted per product
- ✅ **Confidence scores** - Average confidence (0.0-1.0)
- ✅ **Classification breakdown**:
  - Auto-Push (≥0.7 confidence) - Ready for Shopify
  - Needs Review (0.3-0.7) - Manual review required
  - Rejected (<0.3) - Insufficient data

### Cost Analysis:
- 💰 Total cost for test run
- 💰 Cost per product
- 💰 **Projected cost for 14,845 products**

### Output Files:
- `llm_extraction_test_TIMESTAMP.json` - Detailed results
  - Each product's extracted specs
  - Confidence scores
  - Validation issues
  - Costs

## Expected Test Results

Based on our Caroma/Fienza proofs:

| Metric | Expected |
|--------|----------|
| Success Rate | 85-95% |
| Avg Specs per Product | 8-15 |
| Auto-Push Rate | 60-70% |
| Cost per Product | $0.02-0.05 |
| **Total Production Cost** | **$300-750** |

## Next Steps

### If Test Succeeds (>80% success):
1. Review sample extractions for quality
2. Adjust standardization prompts if needed
3. Scale to production (14,845 products)

### If Test Fails (<80% success):
1. Review failed products
2. Identify common issues
3. Refine prompts/approach
4. Re-test on 10 products

## Implementation Status

⚠️ **CURRENT:** Script framework with placeholders
🔧 **TODO:** Implement actual Claude API calls

The script needs:
- Claude API integration for web fetching + extraction
- Claude API calls for standardization
- Error handling and retries
- Rate limiting (to avoid API throttling)

**Estimated time to complete:** 2-3 hours

## Questions?

- What's the difference vs traditional scraping? → See main README
- Why test first? → Validates approach, estimates costs, finds issues early
- Can we test without API key? → No, LLM extraction requires API access
