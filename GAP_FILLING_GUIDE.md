## Gap-Filling & Error Correction Guide

Complete guide to filling missing data and fixing incorrect data in your existing 16k Shopify products.

---

## Overview

The gap-filling workflow fetches existing product data from Shopify, extracts specs from supplier URLs, and intelligently merges them to:

1. **Fill gaps** - Add missing data to empty fields
2. **Fix errors** - Correct incorrect data (high confidence only)
3. **Preserve good data** - Never overwrite good existing values

---

## Quick Start

### Prerequisites

Add Shopify credentials to `.env`:

```bash
# Shopify API credentials
SHOPIFY_SHOP_URL=your-store.myshopify.com
SHOPIFY_ACCESS_TOKEN=your_admin_api_token
```

### Test with 10 Products (Dry-Run)

```bash
# Preview changes without actually updating Shopify
python scripts/fix_existing_products.py --supplier abey.com.au --limit 10 --dry-run
```

Expected output:
```
================================================================================
FIXING EXISTING PRODUCTS: abey.com.au
================================================================================
Mode: DRY RUN
Fill empty fields: True
Fix errors: False (confidence >= 0.8)
Batch size: 50

Found 10 products to process

[1/10] Processing ABL0901...
  ✓ 3 changes:
    - Filled overall_width_mm: 360
    - Filled bowl_depth_mm: 160
    - Filled product_material: Stainless Steel 304

[2/10] Processing ABL0902...
  → No changes needed
```

### Fill Gaps Only (Conservative, Recommended)

```bash
# Only fill empty fields, don't touch existing data
python scripts/fix_existing_products.py --supplier abey.com.au --limit 50 --fill-empty
```

**Safe because:**
- Only updates fields that are empty/null
- Never overwrites existing values
- Validation prevents invalid data

### Fill Gaps AND Fix Errors (Aggressive)

```bash
# Fill empty fields + fix incorrect data (requires confidence >= 0.8)
python scripts/fix_existing_products.py --supplier abey.com.au --limit 50 --fill-empty --fix-errors
```

**Use when:**
- Existing data is known to be incorrect
- Want to correct dimension errors
- Trust high-confidence extractions

---

## Command Reference

### Basic Usage

```bash
# Process all products from supplier
python scripts/fix_existing_products.py --supplier DOMAIN

# Limit number of products
python scripts/fix_existing_products.py --supplier DOMAIN --limit 100

# Process single product by SKU
python scripts/fix_existing_products.py --supplier DOMAIN --sku ABC-123
```

### Mode Options

```bash
# Fill empty fields only (default)
--fill-empty

# Don't fill empty fields
--no-fill-empty

# Fix errors with high confidence
--fix-errors

# Set confidence threshold for fixes (default: 0.8)
--confidence-threshold 0.85
```

### Batch Options

```bash
# Set batch size (default: 50)
--batch-size 100

# Dry-run (preview changes without updating)
--dry-run
```

### Full Examples

```bash
# Conservative: Fill empty fields only, batch of 100
python scripts/fix_existing_products.py \
  --supplier abey.com.au \
  --limit 100 \
  --fill-empty \
  --batch-size 100

# Aggressive: Fill + fix errors, high confidence required
python scripts/fix_existing_products.py \
  --supplier abey.com.au \
  --limit 50 \
  --fill-empty \
  --fix-errors \
  --confidence-threshold 0.85

# Single product dry-run
python scripts/fix_existing_products.py \
  --supplier abey.com.au \
  --sku ABL0901 \
  --dry-run
```

---

## How It Works

### Step 1: Fetch Shopify Data

```python
shopify_data = shopify_fetcher.get_product_by_sku('ABL0901')
# Returns: {
#   'sku': 'ABL0901',
#   'overall_width_mm': 360,
#   'overall_depth_mm': None,  # Empty field
#   'product_material': 'Steel',  # Potentially wrong
#   ...
# }
```

### Step 2: Extract Supplier Data

```python
# Try page extraction first
page_specs = page_extractor.extract_specs(product_url, supplier_hint='abey.com.au')

# Fall back to PDF for missing fields
pdf_specs = queue_processor.extract_from_spec_sheet(spec_sheet_url, collection)

# Merge: page takes precedence
extracted_data = {**pdf_specs, **page_specs}
```

### Step 3: Score Confidence

```python
scoring_result = confidence_scorer.score_extracted_data(extracted_data, collection)
field_confidence = {
    field: scores['confidence']
    for field, scores in scoring_result.get('field_scores', {}).items()
}
# Returns: {
#   'overall_depth_mm': 0.9,  # High confidence
#   'product_material': 0.85,  # High confidence
#   'warranty_years': 0.5,  # Low confidence
# }
```

### Step 4: Smart Merge

#### Fill Empty Fields (fill_empty=True)

```python
# Existing Shopify data
existing = {'overall_depth_mm': None}

# Extracted data
extracted = {'overall_depth_mm': 160}

# Result: Fill the empty field
merged = {'overall_depth_mm': 160}
changes = ['Filled overall_depth_mm: 160']
```

#### Fix Errors (fix_errors=True, confidence >= 0.8)

```python
# Existing Shopify data
existing = {'product_material': 'Steel'}

# Extracted data with high confidence
extracted = {'product_material': 'Stainless Steel 304'}
field_confidence = {'product_material': 0.85}

# Result: Fix the incorrect value
merged = {'product_material': 'Stainless Steel 304'}
changes = ['Fixed product_material: Steel → Stainless Steel 304']
```

#### Keep Good Data

```python
# Existing Shopify data
existing = {'overall_width_mm': 360}

# Extracted data (similar value)
extracted = {'overall_width_mm': 365}

# Result: Keep existing (too similar to justify change)
merged = {'overall_width_mm': 360}
changes = []
```

### Step 5: Validate

```python
is_valid, errors, warnings = data_validator.validate_product_data(merged_data, collection)

if not is_valid:
    print(f"Validation failed: {errors}")
    # Skip this product, log error
else:
    # Proceed to update Shopify
```

### Step 6: Update Shopify

```python
if not dry_run:
    success = shopify_fetcher.update_product(sku, merged_data)
```

**What gets updated:**
- ✅ Product fields (title, vendor, product_type, body_html, tags)
- ✅ Variant fields (price, compare_at_price, weight, SKU)
- ✅ Metafields (dimensions and specs stored as `specs.field_name`)

**Metafields updated:**
- Dimensions: `overall_width_mm`, `overall_depth_mm`, `overall_height_mm`, `bowl_width_mm`, `bowl_depth_mm`, `bowl_height_mm`, `min_cabinet_size_mm`
- Specs: `product_material`, `installation_type`, `warranty_years`, `colour_finish`, `drain_position`, `brand_name`

---

## Merge Strategies

### Conservative (Fill Empty Only)

**When to use:** First run, low risk

**What it does:**
- ✅ Fills empty/null fields
- ✅ Keeps all existing values
- ❌ Doesn't fix incorrect data

**Example:**
```python
existing = {
    'overall_width_mm': 360,     # Keep
    'overall_depth_mm': None,    # Fill with 160
    'product_material': 'Steel'  # Keep (even if wrong)
}
```

### Aggressive (Fill Empty + Fix Errors)

**When to use:** Known data quality issues, trust extractions

**What it does:**
- ✅ Fills empty/null fields
- ✅ Fixes incorrect values (if confidence >= 0.8)
- ✅ Keeps good existing values

**Example:**
```python
existing = {
    'overall_width_mm': 360,      # Keep (accurate)
    'overall_depth_mm': None,     # Fill with 160
    'product_material': 'Steel'   # Fix to 'SS304' (confidence 0.85)
}
```

---

## Safety Features

### 1. Confidence Thresholds

Only fix existing data if confidence >= threshold (default 0.8):

```python
# Will fix if confidence >= 0.8
--fix-errors --confidence-threshold 0.8

# More strict: only fix if confidence >= 0.9
--fix-errors --confidence-threshold 0.9
```

### 2. Value Similarity Detection

Prevents fixing minor variations:

```python
# Too similar - don't change
existing: "360mm"
extracted: "365mm"
→ Keep existing (5mm difference < 10% tolerance)

# Clearly different - fix it
existing: "Steel"
extracted: "Stainless Steel 304"
→ Update with high confidence
```

### 3. Validation Before Update

All data validated before pushing to Shopify:

```python
# Invalid dimensions blocked
overall_width_mm: -500  # ❌ Negative
overall_depth_mm: 50000 # ❌ Unreasonably large (50m)

# Invalid prices blocked
shopify_price: -100  # ❌ Negative price

# Invalid materials blocked
product_material: "N/A"  # ❌ Placeholder value
```

### 4. Dry-Run Mode

Preview all changes before committing:

```bash
python scripts/fix_existing_products.py --supplier abey.com.au --limit 10 --dry-run
```

### 5. Batch Processing with Checkpoints

Process in batches, save progress:

```python
# Process 500 products in batches of 100
--limit 500 --batch-size 100

# If interrupted, checkpoint saved at:
fix_checkpoint_abey_com_au_20260201_123456.json
```

---

## Metrics & Reporting

### Progress Output

```
[1/50] Processing ABL0901...
  ✓ 3 changes:
    - Filled overall_width_mm: 360
    - Filled bowl_depth_mm: 160
    - Fixed product_material: Steel → Stainless Steel 304

[2/50] Processing ABL0902...
  → No changes needed

[3/50] Processing ABL0903...
  ✗ Failed
    Validation failed:
      - overall_depth_mm: Invalid value (-500mm)
```

### Final Report

```
================================================================================
PROCESSING COMPLETE
================================================================================

Total products: 50
  Shopify found: 48
  Shopify not found: 2

Extraction:
  Success: 45
  Failed: 3

Changes:
  Fields filled: 127
  Fields fixed: 23

Validation:
  Passed: 45
  Failed: 3

Shopify updates: 45

Errors: 5
  - ABL0920: Product not found in Shopify
  - ABL0925: Validation failed: negative dimensions
  ... and 3 more

Checkpoint saved: fix_checkpoint_abey_com_au_20260201_123456.json
```

---

## Common Workflows

### Workflow 1: First-Time Gap Fill (Safest)

Start with conservative approach:

```bash
# 1. Dry-run on 10 products
python scripts/fix_existing_products.py --supplier abey.com.au --limit 10 --dry-run

# 2. Review changes, then run live on 50
python scripts/fix_existing_products.py --supplier abey.com.au --limit 50 --fill-empty

# 3. Check results in Shopify, then scale up
python scripts/fix_existing_products.py --supplier abey.com.au --limit 500 --fill-empty --batch-size 100
```

### Workflow 2: Fix Known Errors

Use aggressive mode for known data quality issues:

```bash
# 1. Dry-run to see what would change
python scripts/fix_existing_products.py --supplier abey.com.au --limit 50 --fill-empty --fix-errors --dry-run

# 2. Review changes carefully
# 3. Run live with high confidence threshold
python scripts/fix_existing_products.py --supplier abey.com.au --limit 50 --fill-empty --fix-errors --confidence-threshold 0.85
```

### Workflow 3: Single Product Testing

Test on specific problematic products:

```bash
# 1. Test single product
python scripts/fix_existing_products.py --supplier abey.com.au --sku ABL0901 --dry-run --fill-empty --fix-errors

# 2. Review output
# 3. Apply if looks good
python scripts/fix_existing_products.py --supplier abey.com.au --sku ABL0901 --fill-empty --fix-errors
```

### Workflow 4: Batch Processing All Products

Process your entire catalog:

```bash
# 1. Start with small batch dry-run
python scripts/fix_existing_products.py --supplier abey.com.au --limit 100 --batch-size 50 --dry-run

# 2. Run first real batch
python scripts/fix_existing_products.py --supplier abey.com.au --limit 100 --batch-size 50 --fill-empty

# 3. Check checkpoint and results
cat fix_checkpoint_*.json | tail -1 | python -m json.tool

# 4. Scale up to full catalog
python scripts/fix_existing_products.py --supplier abey.com.au --batch-size 100 --fill-empty
```

---

## Troubleshooting

### Problem: "Product not found in Shopify"

**Cause:** SKU in database doesn't match Shopify

**Solution:**
```bash
# Check SKU in Shopify admin
# OR: Update SKU in database
UPDATE supplier_products SET sku = 'CORRECT-SKU' WHERE sku = 'WRONG-SKU';
```

### Problem: "Validation failed: negative dimensions"

**Cause:** Extracted data has invalid values

**Solution:**
- Extraction error (wrong spec sheet, OCR failure)
- Skip this product, review manually
- Consider improving extraction logic

### Problem: "No data could be extracted"

**Cause:** Can't extract from product_url or spec_sheet_url

**Solution:**
```bash
# Check if URLs are valid
python -c "
from core.supplier_db import get_supplier_db
db = get_supplier_db()
product = db.get_product_by_sku('ABL0901')
print(f'Product URL: {product.get(\"product_url\")}')
print(f'Spec URL: {product.get(\"spec_sheet_url\")}')
"
```

### Problem: Too many changes in dry-run

**Cause:** Existing data is poor quality or extraction is off

**Solution:**
```bash
# Increase confidence threshold
--confidence-threshold 0.9

# Or: Only fill empty, don't fix
--fill-empty --no-fix-errors
```

---

## Best Practices

### 1. Always Dry-Run First

```bash
# Before any real update
python scripts/fix_existing_products.py ... --dry-run
```

### 2. Start Small, Scale Up

```bash
# Test on 10, then 50, then 500, then all
--limit 10  # Test
--limit 50  # Verify
--limit 500 # Batch test
# (no limit) # Full run
```

### 3. Use Conservative Mode First

```bash
# Fill gaps first
--fill-empty

# Then fix errors if needed
--fill-empty --fix-errors
```

### 4. Monitor Checkpoints

```bash
# Check progress
cat fix_checkpoint_*.json | tail -1 | python -m json.tool

# Count errors
jq '.metrics.errors | length' fix_checkpoint_*.json
```

### 5. Batch Appropriately

```bash
# For fill-empty: larger batches OK
--batch-size 100

# For fix-errors: smaller batches safer
--batch-size 50
```

---

## Next Steps

1. **Add Shopify credentials** to `.env`
2. **Test with dry-run** on 10 products
3. **Review changes** in output
4. **Run live** on 50 products
5. **Check Shopify** for accuracy
6. **Scale up** to 500+ products
7. **Process full catalog** in batches

---

## Files Reference

- [core/shopify_fetcher.py](core/shopify_fetcher.py) - Shopify data fetcher
- [scripts/fix_existing_products.py](scripts/fix_existing_products.py) - Gap-filling script
- [PRODUCTION_READY.md](PRODUCTION_READY.md) - Production guide
- [ABEY_PAGE_EXTRACTION.md](ABEY_PAGE_EXTRACTION.md) - Extraction guide

---

Run `python scripts/fix_existing_products.py --supplier abey.com.au --limit 10 --dry-run` to get started!
