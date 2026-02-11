# Pilot Quick Start - abey.com.au

Run the complete data enrichment pipeline pilot in 5 commands.

---

## Prerequisites

```bash
# 1. Run migrations (first time only)
python migrations/add_confidence_fields.py
python migrations/add_reviewed_data_field.py
python migrations/add_applied_fields.py
```

---

## Run Pilot

### Option 1: Dry-Run (Preview Only)

```bash
# Preview with 50 SKUs, no database changes
python scripts/run_pilot.py --supplier abey.com.au --limit 50 --dry-run
```

### Option 2: Live Run

```bash
# Process 50 SKUs, save results
python scripts/run_pilot.py --supplier abey.com.au --limit 50

# Process 100 SKUs
python scripts/run_pilot.py --supplier abey.com.au --limit 100
```

---

## Expected Output

```
╔════════════════════════════════════════════════════════════╗
║  Pilot Batch Runner                                        ║
╚════════════════════════════════════════════════════════════╝

Supplier: abey.com.au
Limit: 50 SKUs
Mode: LIVE

✅ Found 50 products from abey.com.au

============================================================
PHASE 1: Spec Sheet Discovery
============================================================

[1/50] ABC-123... ✅ Found: https://abey.com.au/.../spec.pdf
[2/50] ABC-124... ⚠️  No spec sheet found
...

📊 Spec Sheet Discovery Complete:
  Found: 35 (70.0%)
  Missing: 15 (30.0%)

============================================================
PHASE 2: Data Extraction & Confidence Scoring
============================================================

[1/10] ABC-123 (sinks)... ✅ Conf: 85.0% (7 auto)
[2/10] ABC-125 (taps)... ✅ Conf: 78.0% (5 auto)
[3/10] ABC-127 (sinks)... ⚠️  Conf: 45.0% (needs review)
...

============================================================
PHASE 3: Pilot Report
============================================================

📊 Overall Metrics:
  Total SKUs: 50
  Spec Sheets Found: 35 (70.0%)
  High Confidence: 7 (70.0%)
  Auto-Apply Fields: 45 (75.0%)
  Needs Review Fields: 15 (25.0%)

📋 Next Steps:
  1. Export review queue
  2. Review and import corrections
  3. Apply to Shopify

💾 Report saved to: pilot_report_abey_com_au_20260201_143022.json
```

---

## Next Steps

### 1. Export Review Queue

```bash
python scripts/export_review_queue.py --threshold 0.6
```

### 2. Review in Excel

```bash
open review_queue_20260201_143022.csv
# Fill in 'approved_value' column
```

### 3. Import Reviewed Data

```bash
python scripts/import_review_queue.py review_queue_20260201_143022.csv
```

### 4. Apply to Shopify

```bash
# Preview
python scripts/apply_to_shopify.py --collection sinks --dry-run

# Apply
python scripts/apply_to_shopify.py --collection sinks
```

---

## Success Criteria

Pilot is successful if:
- ✅ **60%+** spec sheets found
- ✅ **80%+** extraction success
- ✅ **70%+** high-confidence products
- ✅ **75%+** fields auto-apply
- ✅ **<5%** critical errors

---

## Troubleshooting

### No products found?
```bash
# Check supplier name in DB
python
>>> from core.supplier_db import get_supplier_db
>>> import sqlite3
>>> db = get_supplier_db()
>>> conn = sqlite3.connect(db.db_path)
>>> cursor = conn.cursor()
>>> cursor.execute("SELECT DISTINCT supplier_name FROM supplier_products")
>>> for row in cursor.fetchall(): print(row[0])
```

### Spec sheets not found?
Check [core/supplier_scrapers.py](core/supplier_scrapers.py) for abey.com.au patterns

### Extraction failing?
Ensure OpenAI API key is configured:
```bash
echo $OPENAI_API_KEY
```

---

## Full Documentation

See [PILOT_GUIDE.md](PILOT_GUIDE.md) for complete guide.

---

## Quick Commands

```bash
# Full pilot workflow
python migrations/add_confidence_fields.py
python migrations/add_reviewed_data_field.py
python migrations/add_applied_fields.py
python scripts/run_pilot.py --supplier abey.com.au --limit 50
python scripts/export_review_queue.py
# (Review CSV manually)
python scripts/import_review_queue.py review_queue_*.csv
python scripts/apply_to_shopify.py --collection sinks
```
