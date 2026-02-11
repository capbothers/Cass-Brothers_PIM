# Quick Start Guide - Milestone 1

Get started with spec sheet discovery and confidence scoring in 5 minutes.

---

## Step 1: Run Database Migration

Update your existing database to add new fields:

```bash
cd /workspaces/Cass-Brothers_PIM
python migrations/add_confidence_fields.py
```

**Expected Output:**
```
✅ Added spec_sheet_url column
✅ Added last_scraped_at column
✅ Added confidence_summary column
✅ Migration complete!
```

---

## Step 2: Test Spec Sheet Discovery

Try discovering a spec sheet from a real product URL:

```python
from core.spec_sheet_scraper import get_spec_sheet_scraper

scraper = get_spec_sheet_scraper()

# Example product URL (replace with your supplier URL)
product_url = "https://example-supplier.com/products/sink-abc123"

spec_url = scraper.find_spec_sheet_url(product_url)

if spec_url:
    print(f"✅ Found spec sheet: {spec_url}")
else:
    print("⚠️  No spec sheet found")
```

---

## Step 3: Test Confidence Scoring

Score some sample extracted data:

```python
from core.confidence_scorer import get_confidence_scorer

scorer = get_confidence_scorer(threshold=0.6)

# Sample extracted data
extracted = {
    "length_mm": "450",                    # High confidence
    "width_mm": "380",                     # High confidence
    "material": "Stainless Steel",         # High confidence
    "estimated_weight": "approx 8kg"       # Low confidence (guessed)
}

result = scorer.score_extracted_data(extracted)

print(f"Overall Confidence: {result['overall_confidence']:.2%}")
print(f"\n✅ Auto-Apply ({len(result['auto_apply_fields'])} fields):")
for field in result['auto_apply_fields']:
    print(f"   - {field}")

print(f"\n⚠️  Manual Review ({len(result['review_fields'])} fields):")
for field in result['review_fields']:
    print(f"   - {field}")
```

---

## Step 4: Run Complete Examples

```bash
python examples/spec_sheet_enrichment_example.py
```

---

## Step 5: Integrate with Your Workflow

### Option A: Batch Discover Spec Sheets

```python
from core.supplier_db import get_supplier_db
from core.spec_sheet_scraper import get_spec_sheet_scraper

db = get_supplier_db()
scraper = get_spec_sheet_scraper()

# Get products without spec sheets
products = db.get_products_without_spec_sheets(limit=50)

# Batch scrape (respects rate limits)
results = scraper.batch_scrape(products, rate_limit=1.0)

print(f"Found {results['found']} spec sheets out of {results['total']} products")
```

### Option B: Add Confidence Scoring to Existing Extraction

```python
from core.queue_processor import get_queue_processor
from core.confidence_scorer import get_confidence_scorer
from core.supplier_db import get_supplier_db

processor = get_queue_processor()
scorer = get_confidence_scorer()
db = get_supplier_db()

# Get item from processing queue
queue_items = db.get_processing_queue(status='pending', limit=1)
item = queue_items['items'][0]

# Extract data (existing workflow)
extracted = processor.extract_from_spec_sheet(
    item['shopify_spec_sheet'],
    item['target_collection']
)

# NEW: Score confidence
scored = scorer.score_extracted_data(extracted, item['target_collection'])

# Store confidence summary
db.update_processing_queue_confidence(item['id'], {
    "overall": scored['overall_confidence'],
    "auto_apply_count": len(scored['auto_apply_fields']),
    "review_count": len(scored['review_fields'])
})

# Use auto_apply_fields for Shopify push
# Use review_fields for manual review queue
```

---

## Common Use Cases

### Reject Guessed Fields

```python
from core.confidence_scorer import get_confidence_scorer

scorer = get_confidence_scorer()

# Filter out guessed values
filtered = scorer.reject_guessed_fields({
    "length_mm": "450",           # ✅ Keep
    "width_mm": "approx 380"      # ❌ Reject (contains "approx")
})
# Result: {"length_mm": "450"}
```

### Find Products Needing Re-Scraping

```python
from core.supplier_db import get_supplier_db

db = get_supplier_db()

# Get products scraped >30 days ago
old_products = db.get_products_for_rescraping(days_old=30, limit=100)
```

---

## Troubleshooting

### "No such column: spec_sheet_url"
Run the migration: `python migrations/add_confidence_fields.py`

### Scraper times out
Increase timeout: `SpecSheetScraper(timeout=30)`

### Import errors
Run from project root or use: `python -m core.spec_sheet_scraper`

---

## Next Steps

1. ✅ **You are here** - Milestone 1 complete
2. ⏭️ **Milestone 2** - Build manual review queue UI
3. ⏭️ **Milestone 3** - Integrate with Shopify auto-apply
4. ⏭️ **Milestone 4** - Add CSV export

See [DATA_ENRICHMENT_PIPELINE.md](DATA_ENRICHMENT_PIPELINE.md) for the full roadmap.

---

## API Quick Reference

### SupplierDatabase
```python
db.update_spec_sheet_url(sku, spec_url)
db.get_products_without_spec_sheets(limit=100)
db.update_processing_queue_confidence(queue_id, summary)
```

### SpecSheetScraper
```python
scraper.find_spec_sheet_url(product_url)
scraper.batch_scrape(products, rate_limit=1.0)
```

### ConfidenceScorer
```python
scorer.score_extracted_data(extracted, collection_name)
scorer.reject_guessed_fields(extracted)
```

Full API docs: [MILESTONE_1_IMPLEMENTATION.md](MILESTONE_1_IMPLEMENTATION.md)
