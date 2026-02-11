# Pilot Guide: Running the Data Enrichment Pipeline on abey.com.au

**Purpose:** Test the complete data enrichment pipeline on a real supplier (abey.com.au) with 50-100 SKUs.

---

## Prerequisites

1. **Database Setup**
   ```bash
   # Run all migrations
   python migrations/add_confidence_fields.py
   python migrations/add_reviewed_data_field.py
   python migrations/add_applied_fields.py
   ```

2. **Supplier Data**
   - Ensure you have abey.com.au products in `supplier_products` table
   - Each product should have `product_url` populated

3. **Check Supplier Data**
   ```python
   from core.supplier_db import get_supplier_db
   db = get_supplier_db()

   # Check how many abey products you have
   import sqlite3
   conn = sqlite3.connect(db.db_path)
   cursor = conn.cursor()
   cursor.execute("SELECT COUNT(*) FROM supplier_products WHERE supplier_name LIKE '%abey%'")
   count = cursor.fetchone()[0]
   print(f"Found {count} abey.com.au products")
   conn.close()
   ```

---

## Pilot Workflow

### Step 1: Run Pilot Script (Dry-Run First)

```bash
# Dry-run to preview (no database changes)
python scripts/run_pilot.py --supplier abey.com.au --limit 50 --dry-run
```

**Expected Output:**
```
╔════════════════════════════════════════════════════════════╗
║  Pilot Batch Runner                                        ║
╚════════════════════════════════════════════════════════════╝

Supplier: abey.com.au
Limit: 50 SKUs
Mode: DRY RUN

✅ Found 50 products from abey.com.au

============================================================
PHASE 1: Spec Sheet Discovery
============================================================

Discovering spec sheets for 50 products...

[1/50] ABC-123... ✅ Found: https://abey.com.au/files/spec-ABC-123.pdf
[2/50] ABC-124... ⚠️  No spec sheet found
[3/50] ABC-125... ✅ Found: https://abey.com.au/files/spec-ABC-125.pdf
...

📊 Spec Sheet Discovery Complete:
  Found: 35
  Missing: 15

============================================================
PHASE 2: Data Extraction & Confidence Scoring
============================================================

Simulating extraction for products with spec sheets...

[1/10] ABC-123 (sinks)... ✅ Conf: 85.0% (7 auto)
[2/10] ABC-125 (taps)... ✅ Conf: 78.0% (5 auto)
[3/10] ABC-127 (sinks)... ⚠️  Conf: 45.0% (needs review)
...

============================================================
PHASE 3: Pilot Report
============================================================

PILOT REPORT
────────────────────────────────────────────────────────────

📊 Overall Metrics:
  Total SKUs Processed: 50
  Spec Sheets Found: 35 (70.0%)
  Spec Sheets Missing: 15 (30.0%)

🔬 Extraction & Scoring:
  Attempted: 10
  Success: 10
  Failed: 0

✅ Confidence Distribution:
  High Confidence (≥0.6): 7 (70.0%)
  Low Confidence (<0.6): 3 (30.0%)

🎯 Field-Level Metrics:
  Total Fields Extracted: 60
  Auto-Apply Fields: 45 (75.0%)
  Needs Review Fields: 15 (25.0%)

📋 Next Steps:
  1. Export review queue:
     python scripts/export_review_queue.py --threshold 0.6
  2. Apply high-confidence fields to Shopify:
     python scripts/apply_to_shopify.py --collection <collection>
  3. Manually add spec sheet URLs for 15 products
```

---

### Step 2: Run Live Pilot

```bash
# Live run (makes database changes)
python scripts/run_pilot.py --supplier abey.com.au --limit 50
```

This will:
1. ✅ Discover spec sheet URLs and store in database
2. ✅ Simulate extraction and scoring (update for production)
3. ✅ Generate `pilot_report_abey_com_au_YYYYMMDD_HHMMSS.json`

---

### Step 3: Review Pilot Report

Open the generated JSON report:

```bash
cat pilot_report_abey_com_au_*.json
```

**Report Structure:**
```json
{
  "supplier": "abey.com.au",
  "timestamp": "20260201_143022",
  "limit": 50,
  "metrics": {
    "total_skus": 50,
    "spec_sheets_found": 35,
    "spec_sheets_missing": 15,
    "extraction_attempted": 10,
    "extraction_success": 10,
    "extraction_failed": 0,
    "auto_apply_count": 45,
    "needs_review_count": 15,
    "high_confidence_products": 7,
    "low_confidence_products": 3,
    "errors": []
  }
}
```

---

### Step 4: Export Review Queue

For low-confidence fields, export to manual review:

```bash
python scripts/export_review_queue.py --threshold 0.6
```

**Output:**
```
📊 Found 3 items with low-confidence fields
✅ Exported 15 low-confidence fields from 3 products
📄 Output file: review_queue_20260201_143022.csv

Next steps:
1. Open review_queue_20260201_143022.csv in Excel/Google Sheets
2. Review each field and fill in 'approved_value' column
3. Save the CSV
4. Run: python scripts/import_review_queue.py review_queue_20260201_143022.csv
```

---

### Step 5: (Optional) Manual Review

```bash
# Open CSV in Excel or Google Sheets
open review_queue_20260201_143022.csv

# After reviewing, import corrections
python scripts/import_review_queue.py review_queue_20260201_143022.csv
```

---

### Step 6: Apply to Shopify (If Ready)

```bash
# Preview first
python scripts/apply_to_shopify.py --collection sinks --dry-run

# Apply
python scripts/apply_to_shopify.py --collection sinks --limit 10

# OR export CSV
python scripts/export_shopify_updates.py --collection sinks
```

---

## Production Integration

### Replace Simulated Extraction with Real Extraction

In `scripts/run_pilot.py`, replace `_simulate_extraction_and_scoring()` with:

```python
def _real_extraction_and_scoring(self, products: List[Dict[str, Any]]):
    """Real extraction using queue_processor"""
    from core.queue_processor import get_queue_processor

    processor = get_queue_processor()
    products_with_specs = [p for p in products if p.get('spec_sheet_url')]

    for product in products_with_specs:
        sku = product['sku']
        spec_sheet_url = product['spec_sheet_url']
        collection = product.get('detected_collection', 'sinks')

        try:
            # Real extraction
            extracted = processor.extract_from_spec_sheet(spec_sheet_url, collection)

            # Score confidence
            scored = self.scorer.score_extracted_data(extracted, collection)

            # Add to processing queue
            queue_id = self.db.add_to_processing_queue({
                'variant_sku': sku,
                'title': product.get('product_name', ''),
                'shopify_spec_sheet': spec_sheet_url
            }, target_collection=collection)

            # Store extraction results
            self.db.update_processing_queue_extracted_data(queue_id, extracted)
            self.db.update_processing_queue_confidence(queue_id, {
                'overall': scored['overall_confidence'],
                'field_scores': scored['field_scores']
            })

            # Update metrics
            self.metrics['extraction_success'] += 1
            # ... etc

        except Exception as e:
            self.metrics['extraction_failed'] += 1
            # ... etc
```

---

## Expected Metrics

### Good Pilot Results:
- **Spec Sheet Discovery:** 60-80% found
- **Extraction Success:** 90%+ of spec sheets
- **High Confidence:** 70-85% of products
- **Auto-Apply Rate:** 75-85% of fields
- **Review Rate:** 15-25% of fields

### Red Flags:
- **Spec Sheet Discovery:** <40% found → Review scraper patterns
- **Extraction Failures:** >20% → Check spec sheet format/quality
- **Low Confidence:** >50% → Review confidence scoring thresholds
- **Auto-Apply Rate:** <50% → Data quality issues

---

## Troubleshooting

### No Products Found

```python
# Check supplier name in database
from core.supplier_db import get_supplier_db
import sqlite3

db = get_supplier_db()
conn = sqlite3.connect(db.db_path)
cursor = conn.cursor()
cursor.execute("SELECT DISTINCT supplier_name FROM supplier_products LIMIT 10")
for row in cursor.fetchall():
    print(row[0])
conn.close()

# If supplier name doesn't match, adjust --supplier argument
python scripts/run_pilot.py --supplier "Abey Australia" --limit 50
```

### Spec Sheet Discovery Failing

```python
# Test on single product
from core.spec_sheet_scraper import get_spec_sheet_scraper

scraper = get_spec_sheet_scraper()
url = "https://abey.com.au/products/example-product"
spec_url = scraper.find_spec_sheet_url(url)
print(f"Found: {spec_url}")

# If not finding, check supplier_scrapers.py patterns
```

### Extraction Not Working

```bash
# Make sure you have Vision API credentials configured
echo $OPENAI_API_KEY

# Test extraction manually
python
>>> from core.queue_processor import get_queue_processor
>>> processor = get_queue_processor()
>>> result = processor.extract_from_spec_sheet("https://example.com/spec.pdf", "sinks")
>>> print(result)
```

---

## Manual Steps (If Needed)

### 1. Import Supplier Products

If you don't have abey.com.au products yet:

```python
from core.supplier_db import get_supplier_db

db = get_supplier_db()

# Import from CSV
csv_data = [
    {
        'sku': 'ABC-123',
        'supplier_name': 'abey.com.au',
        'product_url': 'https://abey.com.au/products/sink-abc-123',
        'product_name': 'Kitchen Sink 450mm'
    },
    # ... more products
]

result = db.import_from_csv(csv_data, auto_extract_images=True)
print(result)
```

### 2. Manually Add Spec Sheet URLs

If scraper can't find them automatically:

```python
from core.supplier_db import get_supplier_db

db = get_supplier_db()

# Update spec sheet URL
db.update_spec_sheet_url('ABC-123', 'https://abey.com.au/files/spec-ABC-123.pdf')
```

---

## Success Criteria

Pilot is successful if:
- ✅ 60%+ spec sheets discovered automatically
- ✅ 80%+ extraction success rate
- ✅ 70%+ fields auto-apply (high confidence)
- ✅ <5% critical errors
- ✅ Manual review queue is manageable (<50 fields)

If criteria met → Scale to 500+ SKUs → Full production rollout

---

## Files Reference

**Pilot Scripts:**
- [scripts/run_pilot.py](scripts/run_pilot.py) - Main pilot orchestration
- [core/supplier_scrapers.py](core/supplier_scrapers.py) - Supplier-specific patterns

**Related Scripts:**
- [scripts/export_review_queue.py](scripts/export_review_queue.py) - Export low-confidence fields
- [scripts/import_review_queue.py](scripts/import_review_queue.py) - Import reviewed fields
- [scripts/apply_to_shopify.py](scripts/apply_to_shopify.py) - Push to Shopify

**Core Modules:**
- [core/spec_sheet_scraper.py](core/spec_sheet_scraper.py) - Generic spec sheet discovery
- [core/confidence_scorer.py](core/confidence_scorer.py) - Confidence scoring
- [core/queue_processor.py](core/queue_processor.py) - AI extraction (production)

---

## Timeline

**Day 1:** Setup & Dry-Run
- Run migrations
- Import supplier data (if needed)
- Test pilot script in dry-run mode
- Review expected output

**Day 2:** Live Pilot
- Run live pilot (50 SKUs)
- Review pilot report
- Export review queue
- Manual review (if needed)

**Day 3:** Analysis & Scale
- Analyze metrics
- Tune thresholds if needed
- Scale to 100 SKUs
- Document any issues

**Day 4-5:** Production Ready
- Replace simulated extraction with real
- Full 500+ SKU batch
- Integrate with Shopify push

---

## Next Steps After Pilot

1. **Review metrics** - Check if success criteria met
2. **Tune confidence thresholds** - Adjust if too strict/loose
3. **Update supplier patterns** - Improve spec sheet discovery
4. **Scale up** - Run on 500+ SKUs
5. **Automate** - Schedule daily/weekly batches
6. **Monitor** - Track ongoing success rates

See also:
- [DATA_ENRICHMENT_PIPELINE.md](DATA_ENRICHMENT_PIPELINE.md) - Overall architecture
- [MILESTONE_3_IMPLEMENTATION.md](MILESTONE_3_IMPLEMENTATION.md) - Shopify integration
- [MANUAL_REVIEW_QUEUE.md](MANUAL_REVIEW_QUEUE.md) - Review workflow
