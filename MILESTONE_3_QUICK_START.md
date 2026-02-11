# Milestone 3 Quick Start - Conditional Shopify Auto-Apply

Get started with auto-applying high-confidence fields to Shopify in 5 minutes.

---

## Step 1: Run Migration

Add audit trail fields to your database:

```bash
python migrations/add_applied_fields.py
```

**Expected Output:**
```
✅ Added applied_fields column to processing_queue
✅ Added applied_at column to processing_queue
✅ Migration complete!
```

---

## Step 2: Test Merge Logic (Optional)

Preview how fields will be merged:

```python
from scripts.apply_to_shopify import merge_fields_for_shopify

# Test with a queue item
merged = merge_fields_for_shopify(queue_id=123, confidence_threshold=0.6)

print(f"Fields to apply: {merged['fields']}")
print(f"Auto-applied: {merged['auto_applied']}")
print(f"Reviewed: {merged['reviewed_applied']}")
print(f"Skipped: {merged['skipped']}")
```

---

## Step 3: Apply to Shopify (Dry-Run First)

### Option A: Single Product

```bash
# Preview changes (dry-run)
python scripts/apply_to_shopify.py --sku ABC-123 --dry-run

# Apply changes
python scripts/apply_to_shopify.py --sku ABC-123
```

### Option B: Batch by Collection

```bash
# Preview
python scripts/apply_to_shopify.py --collection sinks --limit 10 --dry-run

# Apply
python scripts/apply_to_shopify.py --collection sinks --limit 10
```

**Output:**
```
Applying to Shopify: ABC-123 (Product ID: 7891234567890)
────────────────────────────────────────────────────────────

✅ Auto-Applied Fields (3):
  • length_mm: 450
  • width_mm: 380
  • material: 304 Stainless Steel

✏️  Reviewed Fields (1):
  • installation_type: Undermount

⏭️  Skipped (Low Confidence) (2):
  • estimated_weight
  • unknown_dimension

✅ Successfully updated Shopify product 7891234567890
```

---

## Step 4: OR Export to CSV for Bulk Import

If you prefer manual control or large batches:

```bash
# Export high-confidence fields to CSV
python scripts/export_shopify_updates.py --collection sinks --output sinks.csv
```

**Output:**
```
📊 Found 150 items to export
✅ Exported 145 products to sinks.csv

Next steps:
1. Review sinks.csv
2. Import to Shopify: Products → Import
3. Upload the CSV file
```

Then in Shopify Admin:
1. Go to **Products** → **Import**
2. Upload `sinks.csv`
3. Click **Import products**

---

## Understanding the Output

### Auto-Applied Fields
These had **confidence ≥ 0.6** and were automatically included:
- Dimensions (450mm) → confidence 0.95
- Materials (Stainless Steel) → confidence 0.85
- Ratings (4 star) → confidence 0.90

### Reviewed Fields
These were **manually corrected** in the review queue (Milestone 2):
- Override extracted values
- Always included, regardless of confidence

### Skipped Fields
These had **confidence < 0.6** and were not applied:
- Guesses (approx 8kg) → confidence 0.20
- Free text (descriptions) → confidence 0.50
- Export to review queue to correct

---

## Common Use Cases

### 1. Process Single Product

```bash
# By SKU
python scripts/apply_to_shopify.py --sku ABC-123

# By queue ID
python scripts/apply_to_shopify.py --queue-id 123
```

### 2. Process Collection

```bash
# Process all sinks
python scripts/apply_to_shopify.py --collection sinks --limit 50
```

### 3. Use Stricter Threshold

```bash
# Only apply fields with confidence ≥ 70%
python scripts/apply_to_shopify.py --collection taps --threshold 0.7
```

### 4. Bulk CSV Export

```bash
# Export all ready items
python scripts/export_shopify_updates.py

# Export specific collection
python scripts/export_shopify_updates.py --collection basins --limit 100
```

---

## Complete Workflow Example

```bash
# 1. Run migrations (first time only)
python migrations/add_applied_fields.py

# 2. Extract and score data (Milestone 1)
# (Your existing extraction pipeline)

# 3. Export low-confidence fields for review (Milestone 2)
python scripts/export_review_queue.py

# 4. Review in Excel, fill approved_value column

# 5. Import reviewed data (Milestone 2)
python scripts/import_review_queue.py review_queue_20260201.csv

# 6. Apply to Shopify (Milestone 3)
python scripts/apply_to_shopify.py --collection sinks --dry-run
python scripts/apply_to_shopify.py --collection sinks

# OR export CSV for bulk import
python scripts/export_shopify_updates.py --collection sinks
```

---

## Troubleshooting

### "No shopify_product_id"
Product doesn't exist in Shopify yet. Create it first or skip.

### "All fields skipped"
All extracted fields below confidence threshold. Lower threshold or export review queue.

### Shopify API Error
Use CSV export as fallback:
```bash
python scripts/export_shopify_updates.py
```

### Want to Change Threshold
Default is 0.6 (balanced). Adjust with `--threshold`:
- **Conservative:** `--threshold 0.7` (fewer auto-applies)
- **Aggressive:** `--threshold 0.5` (more auto-applies)

---

## What Gets Applied?

### ✅ Always Applied
- **Reviewed fields** from manual review queue
- **High-confidence extracted fields** (≥ threshold)

### ❌ Never Applied
- **Low-confidence extracted fields** (< threshold)
- **Guessed values** (containing "approx", "estimated", etc.)
- **Placeholder values** ("TBD", "Unknown", etc.)

### Priority
1. **Reviewed** (human correction) - highest priority
2. **High-confidence extracted** (AI with confidence ≥ 0.6)
3. ~~Low-confidence extracted~~ (skipped, goes to review queue)

---

## Audit Trail

Check what was applied:

```python
from core.supplier_db import get_supplier_db
import json

db = get_supplier_db()
item = db.get_processing_queue_item(queue_id=123)

# Check applied fields
applied = json.loads(item['applied_fields'])
print(f"Last applied: {item['applied_at']}")
print(f"Fields applied: {applied['fields']}")
print(f"Auto: {applied['auto_applied']}")
print(f"Reviewed: {applied['reviewed_applied']}")
```

---

## Next Steps

See full documentation:
- **[MILESTONE_3_IMPLEMENTATION.md](MILESTONE_3_IMPLEMENTATION.md)** - Complete guide
- **[DATA_ENRICHMENT_PIPELINE.md](DATA_ENRICHMENT_PIPELINE.md)** - Overall architecture

All milestones complete! You now have:
- ✅ **M1:** Spec sheet discovery & confidence scoring
- ✅ **M2:** Manual review queue (CSV-based)
- ✅ **M3:** Conditional Shopify auto-apply

---

## Quick Reference

```bash
# Apply single product
python scripts/apply_to_shopify.py --sku ABC-123 [--dry-run]

# Apply collection batch
python scripts/apply_to_shopify.py --collection sinks --limit 50

# Export CSV for bulk import
python scripts/export_shopify_updates.py --collection taps

# Custom confidence threshold
python scripts/apply_to_shopify.py --threshold 0.7
```
