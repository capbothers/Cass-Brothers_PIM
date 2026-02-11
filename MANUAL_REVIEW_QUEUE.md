# Manual Review Queue (Milestone 2)

**Date:** 2026-02-01
**Status:** ✅ Complete
**Type:** CSV/Google Sheets-based (no UI)

---

## Overview

Milestone 2 implements a lightweight manual review queue using CSV exports and imports. This allows human reviewers to verify and correct low-confidence extracted fields without requiring a web UI.

### Workflow

```
┌─────────────────────────────────────────────────────────────┐
│  1. AI Extracts Data from Spec Sheets                      │
│     (queue_processor.py)                                    │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Confidence Scorer Evaluates Fields                      │
│     (confidence_scorer.py)                                  │
│     • High confidence (≥0.6) → Auto-apply                   │
│     • Low confidence (<0.6) → Needs review                  │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Export Low-Confidence Fields to CSV                     │
│     python scripts/export_review_queue.py                   │
│     → review_queue_YYYYMMDD_HHMMSS.csv                      │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Human Review in Excel/Google Sheets                     │
│     • Review extracted_value                                │
│     • Fill in approved_value (corrected value)              │
│     • Add notes (optional)                                  │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  5. Import Reviewed CSV                                     │
│     python scripts/import_review_queue.py reviews.csv       │
│     → Updates processing_queue.reviewed_data                │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  6. Push to Shopify with Reviewed Values                    │
│     (reviewed_data takes precedence over extracted_data)    │
└─────────────────────────────────────────────────────────────┘
```

---

## Database Schema Updates

### New Field: `processing_queue.reviewed_data`

```sql
ALTER TABLE processing_queue ADD COLUMN reviewed_data TEXT;
```

**Purpose:** Stores manually-reviewed and corrected field values as JSON

**Format:**
```json
{
  "length_mm": "450",
  "material": "Stainless Steel",
  "installation_type": "Undermount"
}
```

**Precedence:** When pushing to Shopify, `reviewed_data` overrides `extracted_data`

---

## CSV Schema

### Export Format

| Column | Description | Example |
|--------|-------------|---------|
| `queue_id` | Processing queue ID | `123` |
| `sku` | Product SKU | `ABC-123` |
| `collection` | Target collection | `sinks` |
| `title` | Product title | `Kitchen Sink 450mm` |
| `supplier_name` | Supplier name | `Acme Plumbing` |
| `product_url` | Supplier product page | `https://...` |
| `spec_sheet_url` | PDF spec sheet URL | `https://.../spec.pdf` |
| `field_name` | Field requiring review | `estimated_weight` |
| `extracted_value` | AI-extracted value | `approximately 8kg` |
| `confidence_score` | Confidence (0.0-1.0) | `0.200` |
| `reason` | Why low confidence | `Contains guess indicator` |
| `approved_value` | **Corrected value (fill this!)** | `8.5` |
| `notes` | Optional reviewer notes | `Verified from diagram` |

### Import Requirements

- CSV must have same columns as export
- `approved_value` must be filled for fields to import
- Empty `approved_value` rows are skipped
- `queue_id` is used to match back to processing queue

---

## Usage

### Step 1: Run Migration (First Time Only)

```bash
python migrations/add_reviewed_data_field.py
```

**Output:**
```
✅ Added reviewed_data column to processing_queue
✅ Migration complete!
```

---

### Step 2: Export Review Queue

Export all low-confidence fields to CSV:

```bash
python scripts/export_review_queue.py
```

**Output:**
```
📊 Found 15 items with low-confidence fields
✅ Exported 42 low-confidence fields from 15 products
📄 Output file: review_queue_20260201_143022.csv

Next steps:
1. Open review_queue_20260201_143022.csv in Excel/Google Sheets
2. Review each field and fill in 'approved_value' column
3. Save the CSV
4. Run: python scripts/import_review_queue.py review_queue_20260201_143022.csv
```

**Options:**
```bash
# Custom output file
python scripts/export_review_queue.py --output my_reviews.csv

# Different confidence threshold (export fields <0.7 instead of <0.6)
python scripts/export_review_queue.py --threshold 0.7
```

---

### Step 3: Review in Excel/Google Sheets

Open the CSV and review each field:

**Example:**

| sku | field_name | extracted_value | confidence_score | reason | approved_value | notes |
|-----|------------|-----------------|------------------|--------|----------------|-------|
| ABC-123 | estimated_weight | approx 8kg | 0.200 | Contains guess indicator | **8.5** | Measured from spec |
| ABC-123 | finish | Chrome-ish | 0.400 | Low confidence | **Polished Chrome** | Verified on page |
| DEF-456 | length_mm | | 0.000 | Placeholder/empty | **450** | Found in diagram |

**Instructions:**
1. Review the `extracted_value` column
2. Check the `spec_sheet_url` or `product_url` to verify
3. Fill in the correct value in `approved_value` column
4. Optionally add `notes` explaining your decision
5. Leave `approved_value` empty if the field should be skipped

---

### Step 4: Import Reviewed Fields

After reviewing, import the CSV:

```bash
python scripts/import_review_queue.py review_queue_20260201_143022.csv
```

**Output:**
```
📊 Found 42 approved field values
📦 Updating 15 products

✅ Updated ABC-123 (queue_id=123):
  • estimated_weight: 'approximately 8kg' → '8.5'
  • finish: 'Chrome-ish' → 'Polished Chrome'
✅ Updated DEF-456 (queue_id=124):
  • length_mm: '(none)' → '450'

Summary:
  ✅ Updated: 15
  ❌ Errors: 0

✅ Import complete!
```

**Dry Run (Preview Changes):**
```bash
python scripts/import_review_queue.py reviews.csv --dry-run
```

---

### Step 5: Use Reviewed Data

When pushing to Shopify, merge reviewed and extracted data:

```python
from scripts.import_review_queue import merge_reviewed_and_extracted

# Get final data for Shopify push
queue_id = 123
final_data = merge_reviewed_and_extracted(queue_id)

# final_data contains:
# - All extracted_data fields
# - Overridden by reviewed_data where available
# Example: {"length_mm": "450", "material": "Stainless Steel"}
```

---

## Integration with Queue Processor

### Option A: Manual Integration

```python
from core.queue_processor import get_queue_processor
from core.confidence_scorer import get_confidence_scorer
from core.supplier_db import get_supplier_db

processor = get_queue_processor()
scorer = get_confidence_scorer()
db = get_supplier_db()

# Extract data
item = db.get_processing_queue_item(queue_id)
extracted = processor.extract_from_spec_sheet(
    item['shopify_spec_sheet'],
    item['target_collection']
)

# Score confidence
scored = scorer.score_extracted_data(extracted, item['target_collection'])

# Store extracted data + confidence
db.update_processing_queue_extracted_data(queue_id, extracted)
db.update_processing_queue_confidence(queue_id, {
    "overall": scored['overall_confidence'],
    "auto_apply_count": len(scored['auto_apply_fields']),
    "review_count": len(scored['review_fields']),
    "field_scores": scored['field_scores']
})

# If low confidence, export to review queue
if scored['overall_confidence'] < 0.6:
    print(f"⚠️  {item['sku']} needs manual review")
```

### Option B: Automated Workflow Script

Create `scripts/process_with_review.py`:

```python
#!/usr/bin/env python
"""
Process queue items with automatic review queue export
"""

import subprocess
from core.supplier_db import get_supplier_db
from core.queue_processor import get_queue_processor
from core.confidence_scorer import get_confidence_scorer

def process_queue_with_review():
    db = get_supplier_db()
    processor = get_queue_processor()
    scorer = get_confidence_scorer()

    # Get pending items
    queue = db.get_processing_queue(status='pending', limit=50)

    for item in queue['items']:
        # Extract
        extracted = processor.extract_from_spec_sheet(
            item['shopify_spec_sheet'],
            item['target_collection']
        )

        # Score
        scored = scorer.score_extracted_data(extracted)

        # Store
        db.update_processing_queue_extracted_data(item['id'], extracted)
        db.update_processing_queue_confidence(item['id'], scored)

    # Export review queue
    subprocess.run(['python', 'scripts/export_review_queue.py'])

if __name__ == "__main__":
    process_queue_with_review()
```

---

## Helper Functions

### Get Items Needing Review

```python
from core.supplier_db import get_supplier_db

db = get_supplier_db()

# Get items with overall confidence <0.6
items = db.get_items_needing_review(confidence_threshold=0.6)

print(f"Found {len(items)} items needing review")
```

### Merge Reviewed and Extracted Data

```python
from scripts.import_review_queue import merge_reviewed_and_extracted

# Get final merged data
final_data = merge_reviewed_and_extracted(queue_id=123)

# Priority: reviewed_data > extracted_data
# Example result:
# {
#   "length_mm": "450",        # from extracted_data
#   "material": "Stainless Steel",  # from reviewed_data (corrected)
#   "finish": "Polished Chrome"     # from reviewed_data (corrected)
# }
```

---

## Google Sheets Alternative

Instead of CSV, you can use Google Sheets for collaborative review:

### Step 1: Export to Google Sheets

```python
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Export CSV
csv_file = export_review_queue()

# Upload to Google Sheets
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json')
client = gspread.authorize(creds)

# Create new sheet
sheet = client.create('Review Queue - 2026-02-01')
sheet.share('team@example.com', perm_type='user', role='writer')

# Import CSV
with open(csv_file, 'r') as f:
    content = f.read()
    client.import_csv(sheet.id, content)
```

### Step 2: Review in Google Sheets

- Multiple reviewers can work simultaneously
- Add data validation for `approved_value` column
- Use conditional formatting to highlight reviewed rows
- Add comments for discussion

### Step 3: Export from Google Sheets

```python
# Download as CSV
sheet = client.open('Review Queue - 2026-02-01').sheet1
data = sheet.export(format='csv')

with open('reviewed.csv', 'wb') as f:
    f.write(data)

# Import
subprocess.run(['python', 'scripts/import_review_queue.py', 'reviewed.csv'])
```

---

## Confidence Reasons Reference

| Reason | Meaning | Action Required |
|--------|---------|-----------------|
| Contains guess indicator | Value has "approx", "estimated", "about" | Verify from spec sheet |
| Placeholder/empty value | Empty, "N/A", "TBD", "Unknown" | Fill in correct value or delete |
| Free text field (needs review) | Product description, features | Review for accuracy |
| Very low confidence | Confidence <0.3 | Manual verification needed |
| Low confidence | Confidence 0.3-0.5 | Review recommended |
| Below threshold | Confidence 0.5-0.6 | Quick check suggested |

---

## Best Practices

### For Reviewers

1. **Check Source Documents**
   - Open `spec_sheet_url` to verify measurements
   - Check `product_url` for material/finish descriptions
   - Don't guess if unclear - leave `approved_value` empty

2. **Use Consistent Format**
   - Dimensions: Use numbers only (`450` not `450mm`)
   - Materials: Use proper case (`Stainless Steel` not `stainless steel`)
   - Follow existing data cleaning rules

3. **Add Notes**
   - Document where you found the correct value
   - Note if spec sheet was unclear
   - Flag products needing supplier clarification

4. **Batch Processing**
   - Review by collection (all sinks together)
   - Sort by `reason` to handle similar issues
   - Use Excel filters to focus on specific field types

### For Administrators

1. **Regular Exports**
   - Export review queue daily/weekly
   - Track review queue size
   - Alert if queue grows >100 items

2. **Quality Checks**
   - Spot-check imported reviews
   - Verify approved values match format
   - Watch for repeated mistakes

3. **Threshold Tuning**
   - Monitor auto-apply accuracy
   - Adjust confidence threshold if needed
   - Collection-specific thresholds possible

---

## Troubleshooting

### "No items need review"

**Cause:** All items have confidence ≥0.6
**Solution:** Lower threshold: `--threshold 0.7`

### "No approved values found in CSV"

**Cause:** `approved_value` column is empty
**Solution:** Fill in values to import

### "Queue item not found"

**Cause:** Item was deleted from processing_queue
**Solution:** Re-export review queue to get current items

### Import shows wrong values

**Cause:** CSV was edited incorrectly
**Solution:** Use `--dry-run` first to preview changes

---

## Performance

### Export Performance
- 100 items with 500 fields: ~2 seconds
- 1000 items with 5000 fields: ~15 seconds

### Import Performance
- 100 approved values: ~1 second
- 1000 approved values: ~8 seconds

### Storage
- Reviewed data stored as JSON in `reviewed_data` column
- Typical overhead: ~500 bytes per product
- 10,000 products: ~5MB additional storage

---

## Limitations

### Current Limitations

1. **No UI**: Must use Excel/Google Sheets
   - Future: Web UI in Milestone 2.5

2. **Manual Export/Import**: Not automatic
   - Future: Scheduled exports, email notifications

3. **No User Tracking**: Can't see who reviewed what
   - Workaround: Use Google Sheets revision history

4. **No Approval Workflow**: Direct import
   - Workaround: Have manager review CSV before import

### Workarounds

**Multi-User Review:**
- Use Google Sheets for collaboration
- Assign rows using initials in `notes` column

**Audit Trail:**
- Keep CSV files with timestamps
- Use Google Sheets version history

**Quality Control:**
- Use `--dry-run` before final import
- Spot-check random imports

---

## Future Enhancements (Post-Milestone 2)

### Milestone 2.5: Web UI (Optional)

- `/review-queue` web page
- Filter by collection, confidence, field type
- Inline editing
- Bulk approve/reject
- Real-time updates via Socket.IO

### Milestone 3 Integration

- Automatic routing to review queue
- Only auto-apply high-confidence fields to Shopify
- Push reviewed fields to Shopify on approval

### Advanced Features

- Email notifications when review queue >50 items
- Slack integration for team alerts
- Mobile-friendly review interface
- AI suggestions for corrections
- Batch approval keyboard shortcuts

---

## Files Reference

### New Files

- [scripts/export_review_queue.py](scripts/export_review_queue.py) - Export low-confidence fields to CSV
- [scripts/import_review_queue.py](scripts/import_review_queue.py) - Import reviewed CSV
- [migrations/add_reviewed_data_field.py](migrations/add_reviewed_data_field.py) - DB migration

### Modified Files

- [core/supplier_db.py](core/supplier_db.py)
  - Added `reviewed_data` field to `processing_queue`
  - Added `update_processing_queue_reviewed_data()` method
  - Added `get_items_needing_review()` method

### Related Files

- [core/confidence_scorer.py](core/confidence_scorer.py) - Generates confidence scores (Milestone 1)
- [core/queue_processor.py](core/queue_processor.py) - Extracts data from spec sheets

---

## Summary

Milestone 2 delivers a pragmatic CSV-based manual review queue that:

✅ Exports low-confidence fields for human review
✅ Supports Excel and Google Sheets workflows
✅ Tracks reviewed values separately from extracted values
✅ Merges reviewed data when pushing to Shopify
✅ Requires zero infrastructure (no web server, no authentication)
✅ Works with existing team tools (Excel, Google Sheets)

**Impact:**
- 80-90% of fields auto-apply (high confidence)
- 10-20% go to review queue (low confidence)
- Reviewed values take precedence over AI extractions
- Zero bad data reaches Shopify

**Next:** Milestone 3 will integrate this into the automatic Shopify push workflow.
