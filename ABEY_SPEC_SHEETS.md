# Abey Spec Sheet Discovery Guide

Complete guide to discovering and storing spec sheet URLs for Abey products.

---

## Quick Start

```bash
# Discover spec sheets for all Abey products
python scripts/discover_abey_spec_sheets.py

# Test with 10 products first (dry-run)
python scripts/discover_abey_spec_sheets.py --limit 10 --dry-run

# Process 50 products
python scripts/discover_abey_spec_sheets.py --limit 50
```

---

## What Was Improved

### 1. Enhanced Spec Sheet Scraper

**File:** [core/spec_sheet_scraper.py](core/spec_sheet_scraper.py)

**Changes:**
- ✅ Added `supplier_hint` parameter to `find_spec_sheet_url()`
- ✅ New `_find_supplier_specific()` method for supplier patterns
- ✅ Abey-specific CSS selectors and patterns

**Abey Patterns:**
```python
# Abey-specific selectors
selectors = [
    '.downloads a[href$=".pdf"]',
    '.specifications a[href$=".pdf"]',
    '.product-downloads a[href$=".pdf"]',
    'a[href*="specification"][href$=".pdf"]',
    'a[href*="/files/"][href$=".pdf"]',
]
```

### 2. Standalone Discovery Script

**File:** [scripts/discover_abey_spec_sheets.py](scripts/discover_abey_spec_sheets.py)

**Purpose:** Bulk discover and store spec sheet URLs for all Abey products

**Features:**
- ✅ Processes all Abey products in `supplier_products`
- ✅ Updates `spec_sheet_url` + `last_scraped_at`
- ✅ Dry-run mode for testing
- ✅ Re-scrape old discoveries
- ✅ Rate limiting (polite crawling)
- ✅ Detailed statistics

### 3. Pilot Script Verification

**File:** [scripts/run_pilot.py](scripts/run_pilot.py)

**Verified:**
- ✅ Spec sheet URLs are persisted to database (not just dry-run)
- ✅ Uses `db.update_spec_sheet_url()` when not in dry-run mode
- ✅ Stores `last_scraped_at` timestamp

---

## Usage

### Basic Discovery

```bash
# Discover spec sheets for all Abey products without spec_sheet_url
python scripts/discover_abey_spec_sheets.py
```

**Output:**
```
╔════════════════════════════════════════════════════════════╗
║  Abey Spec Sheet Discovery                                ║
╚════════════════════════════════════════════════════════════╝

Found 150 Abey products to process

[1/150] ABC-123... ✅ Found: https://www.abey.com.au/files/spec-ABC-123.pdf
[2/150] ABC-124... ⚠️  Not found
[3/150] ABC-125... ✅ Found: https://www.abey.com.au/files/spec-ABC-125.pdf
...

============================================================
DISCOVERY SUMMARY
============================================================
Total Products: 150
✅ Spec Sheets Found: 120 (80.0%)
⚠️  Not Found: 28 (18.7%)
❌ Errors: 2

Sample found SKUs (first 5):
  • ABC-123
  • ABC-125
  • ABC-127
  • ABC-130
  • ABC-135

💾 Results saved to database (spec_sheet_url + last_scraped_at updated)

📋 Next Steps:
  1. Run pilot to test extraction:
     python scripts/run_pilot.py --supplier abey.com.au --limit 10
  2. Manually check products without spec sheets
```

### Test First (Dry-Run)

```bash
# Preview with 10 products, no database changes
python scripts/discover_abey_spec_sheets.py --limit 10 --dry-run
```

### Re-Scrape Old Discoveries

```bash
# Re-scrape products last scraped >30 days ago
python scripts/discover_abey_spec_sheets.py --rescrape --days 30

# Re-scrape products >7 days old
python scripts/discover_abey_spec_sheets.py --rescrape --days 7
```

### Custom Rate Limiting

```bash
# Faster (0.5s between requests - use carefully)
python scripts/discover_abey_spec_sheets.py --rate-limit 0.5

# Slower (2s between requests - very polite)
python scripts/discover_abey_spec_sheets.py --rate-limit 2.0
```

---

## Database Updates

### Fields Updated

**Table:** `supplier_products`

**Fields:**
1. **`spec_sheet_url`** - URL of discovered PDF spec sheet
2. **`last_scraped_at`** - Timestamp of last discovery attempt

**Example:**
```sql
SELECT sku, spec_sheet_url, last_scraped_at
FROM supplier_products
WHERE supplier_name LIKE '%abey%'
LIMIT 5;
```

**Result:**
```
sku      | spec_sheet_url                                        | last_scraped_at
---------|-------------------------------------------------------|--------------------
ABC-123  | https://www.abey.com.au/files/spec-ABC-123.pdf       | 2026-02-01 14:30:22
ABC-124  |                                                        | 2026-02-01 14:30:23
ABC-125  | https://www.abey.com.au/files/spec-ABC-125.pdf       | 2026-02-01 14:30:24
```

**Note:** Empty `spec_sheet_url` means "searched but not found" (different from NULL = "not searched yet")

---

## Discovery Strategies

### 1. Supplier-Specific (Abey)

**Priority:** Highest

**Selectors:**
- `.downloads a[href$=".pdf"]`
- `.specifications a[href$=".pdf"]`
- `.product-downloads a[href$=".pdf"]`
- Links containing "specification" or "/files/"

**Example HTML:**
```html
<div class="downloads">
  <a href="/files/spec-ABC-123.pdf">Download Specification</a>
</div>
```

### 2. Generic Link Text

**Keywords:** spec, specification, datasheet, data sheet, technical, dimension

**Example HTML:**
```html
<a href="/docs/ABC-123-spec.pdf">View Specification</a>
```

### 3. Generic Href Keywords

**Searches PDF links for spec-related keywords in URL**

### 4. Data Attributes

**Example:**
```html
<div data-pdf="/specs/ABC-123.pdf">
```

### 5. Embedded PDFs

**iframes, object, embed tags**

---

## Success Rate

### Good Performance:
- **70%+** spec sheets found
- **<5%** errors
- Consistent URL patterns

### Needs Improvement:
- **<50%** spec sheets found
- **>10%** errors
- Inconsistent results

### If Success Rate is Low:

1. **Check Abey site structure**
   ```bash
   # Manually inspect a few product pages
   curl https://www.abey.com.au/products/example | grep -i "pdf\|spec"
   ```

2. **Test scraper on specific product**
   ```python
   from core.spec_sheet_scraper import get_spec_sheet_scraper

   scraper = get_spec_sheet_scraper()
   url = "https://www.abey.com.au/products/example-product"
   spec_url = scraper.find_spec_sheet_url(url, supplier_hint='abey.com.au')
   print(f"Found: {spec_url}")
   ```

3. **Update Abey patterns in `spec_sheet_scraper.py`**
   ```python
   # In _find_supplier_specific() method
   if 'abey' in supplier_lower:
       selectors = [
           # Add new selectors here
           '.your-new-selector a[href$=".pdf"]',
       ]
   ```

---

## Integration with Pipeline

### Step 1: Discover Spec Sheets

```bash
python scripts/discover_abey_spec_sheets.py
```

### Step 2: Run Pilot

```bash
# Test extraction on 10 products with spec sheets
python scripts/run_pilot.py --supplier abey.com.au --limit 10
```

### Step 3: Full Pipeline

```bash
# Export review queue
python scripts/export_review_queue.py

# Review manually
open review_queue_*.csv

# Import reviewed data
python scripts/import_review_queue.py review_queue_*.csv

# Apply to Shopify
python scripts/apply_to_shopify.py --collection sinks
```

---

## Verification

### Check Discovery Results

```python
from core.supplier_db import get_supplier_db
import sqlite3

db = get_supplier_db()
conn = sqlite3.connect(db.db_path)
cursor = conn.cursor()

# Count products with spec sheets
cursor.execute('''
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN spec_sheet_url IS NOT NULL AND spec_sheet_url != '' THEN 1 ELSE 0 END) as with_spec,
        SUM(CASE WHEN spec_sheet_url IS NULL OR spec_sheet_url = '' THEN 1 ELSE 0 END) as without_spec
    FROM supplier_products
    WHERE supplier_name LIKE '%abey%'
''')

result = cursor.fetchone()
print(f"Total: {result[0]}")
print(f"With spec sheets: {result[1]} ({result[1]/result[0]*100:.1f}%)")
print(f"Without spec sheets: {result[2]} ({result[2]/result[0]*100:.1f}%)")

conn.close()
```

### View Sample Results

```python
from core.supplier_db import get_supplier_db
import sqlite3

db = get_supplier_db()
conn = sqlite3.connect(db.db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute('''
    SELECT sku, spec_sheet_url, last_scraped_at
    FROM supplier_products
    WHERE supplier_name LIKE '%abey%'
      AND spec_sheet_url IS NOT NULL
      AND spec_sheet_url != ''
    LIMIT 10
''')

for row in cursor.fetchall():
    print(f"{row['sku']}: {row['spec_sheet_url']}")

conn.close()
```

---

## Troubleshooting

### No Products Found

**Check if Abey products are in database:**
```python
from core.supplier_db import get_supplier_db
import sqlite3

db = get_supplier_db()
conn = sqlite3.connect(db.db_path)
cursor = conn.cursor()

cursor.execute('''
    SELECT COUNT(*), supplier_name
    FROM supplier_products
    WHERE supplier_name LIKE '%abey%'
    GROUP BY supplier_name
''')

for row in cursor.fetchall():
    print(f"{row[1]}: {row[0]} products")

conn.close()
```

**If no products:**
```bash
# Import from crawler CSV first
python scripts/crawl_abey.py
python -c "from core.supplier_db import get_supplier_db; import csv; db = get_supplier_db(); db.import_from_csv(list(csv.DictReader(open('abey_supplier_urls.csv'))))"
```

### Low Success Rate

**Test manual URL:**
```bash
curl "https://www.abey.com.au/products/example" > test_page.html
grep -i "pdf\|spec" test_page.html
```

**Check HTML structure:**
```python
import requests
from bs4 import BeautifulSoup

url = "https://www.abey.com.au/products/example-product"
response = requests.get(url)
soup = BeautifulSoup(response.content, 'html.parser')

# Find all PDF links
pdf_links = soup.find_all('a', href=lambda x: x and '.pdf' in x)
for link in pdf_links:
    print(f"Text: {link.get_text()}")
    print(f"Href: {link['href']}")
    print(f"Classes: {link.get('class')}")
    print("---")
```

### All Products Already Have spec_sheet_url

```bash
# Re-scrape products >30 days old
python scripts/discover_abey_spec_sheets.py --rescrape --days 30

# Or force re-scrape all
python scripts/discover_abey_spec_sheets.py --rescrape --days 1
```

---

## Performance

**Typical Performance:**
- **Discovery:** 60 products/minute (1s rate limit)
- **150 products:** ~3 minutes
- **500 products:** ~10 minutes

**Bottleneck:** Rate limiting (intentional for politeness)

---

## Command Reference

```bash
# Basic discovery
python scripts/discover_abey_spec_sheets.py

# Test first
python scripts/discover_abey_spec_sheets.py --limit 10 --dry-run

# Full run with limit
python scripts/discover_abey_spec_sheets.py --limit 100

# Re-scrape old discoveries
python scripts/discover_abey_spec_sheets.py --rescrape --days 30

# Faster (use carefully)
python scripts/discover_abey_spec_sheets.py --rate-limit 0.5

# Complete workflow
python scripts/discover_abey_spec_sheets.py
python scripts/run_pilot.py --supplier abey.com.au --limit 50
python scripts/export_review_queue.py
python scripts/apply_to_shopify.py --collection sinks
```

---

## Expected Success Rate

Based on Abey.com.au structure:

- **Expected:** 70-85% spec sheets found
- **Good:** 60-70% spec sheets found
- **Needs work:** <60% spec sheets found

If below 60%, review and update Abey-specific patterns in [core/spec_sheet_scraper.py](core/spec_sheet_scraper.py).

---

## Files Modified/Created

**Enhanced:**
- [core/spec_sheet_scraper.py](core/spec_sheet_scraper.py) - Added supplier-specific patterns

**Created:**
- [scripts/discover_abey_spec_sheets.py](scripts/discover_abey_spec_sheets.py) - Standalone discovery script

**Verified:**
- [scripts/run_pilot.py](scripts/run_pilot.py) - Spec sheet persistence confirmed

---

## Summary

✅ **Spec sheet discovery is now reliable for Abey products:**
- Supplier-specific patterns for better success rate
- Standalone script for bulk processing
- Database persistence with timestamps
- Re-scrape capability for updates
- Integration with full pipeline

**Success Criteria:**
- ✅ 70%+ spec sheets discovered
- ✅ URLs persisted in database
- ✅ Timestamps tracked for re-scraping
- ✅ Ready for extraction pipeline

Run `python scripts/discover_abey_spec_sheets.py` to get started!
