# Milestone 2 Quick Start - Manual Review Queue

Get started with CSV-based manual review in 5 minutes.

---

## Step 1: Run Migration

Add the `reviewed_data` field to your database:

```bash
python migrations/add_reviewed_data_field.py
```

**Expected Output:**
```
✅ Added reviewed_data column to processing_queue
✅ Migration complete!
```

---

## Step 2: Export Review Queue

Export all low-confidence fields to CSV:

```bash
python scripts/export_review_queue.py
```

**Output:**
```
📊 Found 15 items with low-confidence fields
✅ Exported 42 low-confidence fields from 15 products
📄 Output file: review_queue_20260201_143022.csv
```

If no items need review, you'll see:
```
✅ No items need review (all above 60% confidence)
```

---

## Step 3: Review in Excel/Google Sheets

Open the CSV file and review each field:

**Columns:**
- `sku`, `collection`, `title` - Product info
- `product_url`, `spec_sheet_url` - Source documents
- `field_name` - Field requiring review (e.g., `estimated_weight`)
- `extracted_value` - AI-extracted value (e.g., `approximately 8kg`)
- `confidence_score` - Why it needs review (e.g., `0.200`)
- `reason` - Explanation (e.g., `Contains guess indicator`)
- **`approved_value`** - **Fill this with correct value** (e.g., `8.5`)
- `notes` - Optional notes (e.g., `Verified from spec sheet`)

**Instructions:**
1. Check the `spec_sheet_url` or `product_url` to verify
2. Fill in the correct value in `approved_value`
3. Add optional `notes` explaining your decision
4. Save the CSV

---

## Step 4: Import Reviewed CSV

Import your reviewed data:

```bash
python scripts/import_review_queue.py review_queue_20260201_143022.csv
```

**Output:**
```
📊 Found 42 approved field values
📦 Updating 15 products

✅ Updated ABC-123 (queue_id=123):
  • estimated_weight: 'approximately 8kg' → '8.5'
  • finish: 'Brushed' → 'Brushed Chrome'

Summary:
  ✅ Updated: 15
  ❌ Errors: 0
```

**Dry Run (Preview First):**
```bash
python scripts/import_review_queue.py reviews.csv --dry-run
```

---

## Step 5: Use Reviewed Data

When pushing to Shopify, reviewed data automatically overrides extracted data:

```python
from scripts.import_review_queue import merge_reviewed_and_extracted

# Get final data for Shopify
queue_id = 123
final_data = merge_reviewed_and_extracted(queue_id)

# final_data contains:
# - All auto-applied fields from extracted_data
# - Corrected values from reviewed_data
```

---

## Example Workflow

```bash
# 1. Run migration (first time only)
python migrations/add_reviewed_data_field.py

# 2. Export review queue
python scripts/export_review_queue.py

# 3. Open CSV in Excel, fill in approved_value column, save

# 4. Import reviewed data
python scripts/import_review_queue.py review_queue_20260201_143022.csv

# Done! Reviewed values are now stored in processing_queue.reviewed_data
```

---

## Common Options

### Export Options

```bash
# Custom output file
python scripts/export_review_queue.py --output my_reviews.csv

# Different confidence threshold (export fields below 70% instead of 60%)
python scripts/export_review_queue.py --threshold 0.7
```

### Import Options

```bash
# Preview changes without applying
python scripts/import_review_queue.py reviews.csv --dry-run
```

---

## Troubleshooting

### "No items need review"
Your items have high confidence! Try lowering threshold: `--threshold 0.7`

### "No approved values found"
Fill in the `approved_value` column in the CSV before importing.

### See wrong data after import
Use `--dry-run` first to preview changes.

---

## What's Next?

See [MANUAL_REVIEW_QUEUE.md](MANUAL_REVIEW_QUEUE.md) for:
- Complete workflow documentation
- Google Sheets integration
- Best practices for reviewers
- Integration with queue processor

---

## Files Reference

**Scripts:**
- [scripts/export_review_queue.py](scripts/export_review_queue.py) - Export to CSV
- [scripts/import_review_queue.py](scripts/import_review_queue.py) - Import from CSV
- [migrations/add_reviewed_data_field.py](migrations/add_reviewed_data_field.py) - DB migration

**Examples:**
- [examples/manual_review_workflow_example.py](examples/manual_review_workflow_example.py) - Complete workflow demo

**Documentation:**
- [MANUAL_REVIEW_QUEUE.md](MANUAL_REVIEW_QUEUE.md) - Full documentation
- [DATA_ENRICHMENT_PIPELINE.md](DATA_ENRICHMENT_PIPELINE.md) - Overall plan
