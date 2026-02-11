# Abey.com.au Crawler Guide

Complete guide to crawling abey.com.au to discover products and import into the pipeline.

---

## Overview

The **Abey Crawler** (`scripts/crawl_abey.py`) automatically:
1. Discovers all product pages on abey.com.au
2. Extracts SKUs from each product page
3. Outputs a CSV file ready for import
4. Feeds into the existing enrichment pipeline

---

## Quick Start

```bash
# Basic crawl (all products)
python scripts/crawl_abey.py

# Crawl with limit
python scripts/crawl_abey.py --limit 100

# Custom output file
python scripts/crawl_abey.py --output my_abey_products.csv

# Faster crawling (0.5s between requests - be careful!)
python scripts/crawl_abey.py --rate-limit 0.5
```

---

## How It Works

### Discovery Strategy

**1. Sitemap First (Preferred)**
```
Try: https://www.abey.com.au/sitemap.xml
     https://www.abey.com.au/sitemap_products.xml
     https://www.abey.com.au/sitemap_index.xml

If found → Extract all product URLs directly
```

**2. Crawl Categories (Fallback)**
```
Start: https://www.abey.com.au/products
Crawl: Category pages → Product listing pages → Individual products
Follow: Pagination links
Limit: 50 pages max to prevent over-crawling
```

### SKU Extraction Strategy

The crawler tries multiple methods to find SKUs (in order):

1. **Meta Tags**
   ```html
   <meta property="product:sku" content="ABC-123">
   <meta name="sku" content="ABC-123">
   <meta itemprop="sku" content="ABC-123">
   ```

2. **JSON-LD Structured Data**
   ```html
   <script type="application/ld+json">
   {
     "@type": "Product",
     "sku": "ABC-123"
   }
   </script>
   ```

3. **Text Patterns**
   ```
   SKU: ABC-123
   Product Code: ABC-123
   Item #: ABC-123
   Model: ABC-123
   ```

4. **Data Attributes**
   ```html
   <div data-sku="ABC-123">
   ```

5. **CSS Selectors**
   ```html
   <span class="sku">ABC-123</span>
   <span class="product-sku">ABC-123</span>
   <span itemprop="sku">ABC-123</span>
   ```

6. **URL Pattern (Last Resort)**
   ```
   https://www.abey.com.au/products/ABC-123
                                     ↑ Extract from URL
   ```

---

## Output Format

### CSV File: `abey_supplier_urls.csv`

```csv
sku,supplier_name,product_url
ABC-123,abey.com.au,https://www.abey.com.au/products/sink-abc-123
ABC-124,abey.com.au,https://www.abey.com.au/products/tap-abc-124
ABC-125,abey.com.au,https://www.abey.com.au/products/basin-abc-125
```

**Fields:**
- `sku` - Product SKU/code extracted from page
- `supplier_name` - Always "abey.com.au"
- `product_url` - Full URL to product page

**Compatible With:**
- `supplier_db.import_from_csv()` - Direct database import
- Pipeline scripts - Automatic integration

---

## Usage Examples

### Example 1: Full Crawl

```bash
python scripts/crawl_abey.py
```

**Output:**
```
╔════════════════════════════════════════════════════════════╗
║  Abey.com.au Product Crawler                              ║
╚════════════════════════════════════════════════════════════╝

Starting crawl of https://www.abey.com.au
Rate limit: 1.0s between requests

Checking https://www.abey.com.au/sitemap.xml...
✅ Found 450 product URLs in sitemap

🔍 Extracting SKUs from product pages...
[1/450] https://www.abey.com.au/products/sink-abc-123
  ✅ Found SKU: ABC-123
[2/450] https://www.abey.com.au/products/tap-abc-124
  ✅ Found SKU: ABC-124
...

✅ Crawl complete! Found 445 products with SKUs

============================================================
CRAWL STATISTICS
============================================================
Pages Crawled: 0
Product URLs Found: 450
SKUs Extracted: 445
SKUs Failed: 5
Errors: 0

💾 Saved 445 products to abey_supplier_urls.csv

📋 Next Steps:
1. Review abey_supplier_urls.csv
2. Import to database
3. Run pilot
```

### Example 2: Test with Limit

```bash
# Test with 50 products first
python scripts/crawl_abey.py --limit 50 --output abey_test.csv
```

### Example 3: Custom Starting Point

```bash
# Start from specific category
python scripts/crawl_abey.py --start-url https://www.abey.com.au/sinks
```

---

## Integration with Pipeline

### Step 1: Crawl Products

```bash
python scripts/crawl_abey.py --output abey_supplier_urls.csv
```

### Step 2: Import to Database

```bash
python -c "
from core.supplier_db import get_supplier_db
import csv

db = get_supplier_db()

with open('abey_supplier_urls.csv') as f:
    reader = csv.DictReader(f)
    result = db.import_from_csv(list(reader), auto_extract_images=True)
    print(f'Imported: {result[\"imported\"]}, Updated: {result[\"updated\"]}')
"
```

**Or use Python script:**
```python
from core.supplier_db import get_supplier_db
import csv

db = get_supplier_db()

with open('abey_supplier_urls.csv') as f:
    reader = csv.DictReader(f)
    result = db.import_from_csv(list(reader), auto_extract_images=True)

print(f"Imported: {result['imported']}")
print(f"Updated: {result['updated']}")
print(f"Skipped: {result['skipped']}")
print(f"Images extracted: {result['images_extracted']}")
```

### Step 3: Run Pilot

```bash
# Run pilot on imported products
python scripts/run_pilot.py --supplier abey.com.au --limit 50
```

### Step 4: Complete Pipeline

```bash
# After pilot, run full enrichment
python scripts/export_review_queue.py
# (Review CSV)
python scripts/import_review_queue.py review_queue_*.csv
python scripts/apply_to_shopify.py --collection sinks
```

---

## Polite Crawling Features

### Rate Limiting

**Default:** 1 second between requests (60 requests/minute)

```bash
# Conservative (2 seconds)
python scripts/crawl_abey.py --rate-limit 2.0

# Moderate (1 second - default)
python scripts/crawl_abey.py --rate-limit 1.0

# Faster (0.5 seconds - use with caution)
python scripts/crawl_abey.py --rate-limit 0.5
```

### User Agent

**Identifies crawler:**
```
Mozilla/5.0 (compatible; CassBrothersPIM/1.0; +https://cassbrothers.com.au)
```

**Benefits:**
- Site owner can identify and contact you
- Respectful crawling practices
- Can be blocked if needed

### Respectful Practices

✅ **Does:**
- Rate limit requests (1s default)
- Use descriptive user agent
- Stop on errors
- Limit crawl depth
- Handle interruption gracefully (saves progress)

❌ **Doesn't:**
- Ignore robots.txt (manual check recommended)
- Make parallel requests
- Retry failed requests aggressively
- Crawl infinitely

---

## Troubleshooting

### No Products Found

**Check starting URL:**
```bash
# Try different entry points
python scripts/crawl_abey.py --start-url https://www.abey.com.au/all-products
python scripts/crawl_abey.py --start-url https://www.abey.com.au/shop
```

**Check if site structure changed:**
```python
# Test manually
from scripts.crawl_abey import AbeyCrawler

crawler = AbeyCrawler()
products = crawler._crawl_from_sitemap()
print(f"Found {len(products)} from sitemap")
```

### SKU Extraction Failing

**Test on specific product:**
```python
from scripts.crawl_abey import AbeyCrawler
from bs4 import BeautifulSoup
import requests

url = "https://www.abey.com.au/products/example-product"
response = requests.get(url)
soup = BeautifulSoup(response.content, 'html.parser')

crawler = AbeyCrawler()
sku = crawler._extract_sku(soup, url)
print(f"Extracted SKU: {sku}")

# If None, inspect page manually
print(soup.prettify()[:1000])
```

**Common issues:**
- JavaScript-rendered content (crawler doesn't execute JS)
- SKU in non-standard location
- Dynamic SKU generation

**Solutions:**
1. Update `_extract_sku()` method with new pattern
2. Add supplier-specific selector
3. Use manual extraction for problem products

### Crawl Too Slow

```bash
# Reduce rate limit (carefully!)
python scripts/crawl_abey.py --rate-limit 0.5

# Or limit crawl
python scripts/crawl_abey.py --limit 200
```

### Interrupted Crawl

```bash
# Crawler saves progress on interruption (Ctrl+C)
# Check if CSV was created
ls -lh abey_supplier_urls.csv

# Resume by importing existing CSV and crawling missing
```

---

## Advanced Usage

### Customize for Different Suppliers

Copy and modify for other suppliers:

```python
# scripts/crawl_supplier.py
class SupplierCrawler(AbeyCrawler):
    def __init__(self, **kwargs):
        super().__init__(
            base_url="https://www.example.com",
            **kwargs
        )

    def _extract_sku(self, soup, url):
        # Custom SKU extraction logic
        pass
```

### Validate CSV Before Import

```bash
# Check for duplicates
cut -d, -f1 abey_supplier_urls.csv | sort | uniq -d

# Check for missing SKUs
grep "^," abey_supplier_urls.csv

# Count products
wc -l abey_supplier_urls.csv
```

### Merge Multiple Crawls

```python
import csv

# Combine multiple CSV files
files = ['abey_batch1.csv', 'abey_batch2.csv']
all_products = {}

for file in files:
    with open(file) as f:
        reader = csv.DictReader(f)
        for row in reader:
            all_products[row['sku']] = row

# Write combined
with open('abey_combined.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['sku', 'supplier_name', 'product_url'])
    writer.writeheader()
    writer.writerows(all_products.values())

print(f"Combined: {len(all_products)} unique products")
```

---

## Performance

**Typical Performance:**
- **Sitemap discovery:** 2-5 seconds
- **Product URL discovery:** 1-2 minutes (if crawling)
- **SKU extraction:** 50 products/minute (with 1s rate limit)
- **Total for 500 products:** ~10-15 minutes

**Bottlenecks:**
- Rate limiting (intentional - be polite!)
- Network latency
- Page complexity

**Optimization:**
- Use sitemap (faster than crawling)
- Run during off-peak hours
- Reduce rate limit carefully

---

## Dependencies

**Required:**
- `requests` - HTTP client
- `beautifulsoup4` - HTML parsing

**Install:**
```bash
pip install requests beautifulsoup4

# Or if already in requirements.txt
pip install -r requirements.txt
```

**Optional:**
- `lxml` - Faster XML parsing (for sitemaps)

---

## Error Handling

**Graceful Degradation:**
1. Sitemap fails → Falls back to crawling
2. SKU extraction fails → Logs warning, continues
3. Network error → Logs error, continues
4. User interrupts (Ctrl+C) → Saves progress to CSV

**Logs:**
- `INFO` - Progress updates
- `WARNING` - SKU extraction failures
- `ERROR` - Network/parsing errors

---

## Assumptions

### Product URL Patterns

**Assumed:**
- Products in `/product/`, `/products/`, `/p/`, `/item/`
- Not in `/category/`, `/collection/`, `/search/`, etc.

**If different:**
Update `_is_product_url()` method:
```python
def _is_product_url(self, url: str) -> bool:
    # Add your patterns
    return '/your-pattern/' in url.lower()
```

### SKU Format

**Assumed:**
- Alphanumeric with hyphens: `ABC-123`, `SINK-450`, etc.
- 4+ characters
- Consistent across site

**If different:**
Update `_clean_sku()` or extraction patterns

---

## Next Steps

After crawling:

1. **Review CSV** - Check for quality
2. **Import to DB** - Load into supplier_products
3. **Run Pilot** - Test enrichment pipeline
4. **Export Review** - Handle low-confidence
5. **Apply to Shopify** - Push updates

See:
- [PILOT_GUIDE.md](PILOT_GUIDE.md) - Running pilot
- [DATA_ENRICHMENT_PIPELINE.md](DATA_ENRICHMENT_PIPELINE.md) - Full pipeline

---

## Files Reference

**Crawler:**
- [scripts/crawl_abey.py](scripts/crawl_abey.py) - Main crawler script

**Related:**
- [scripts/run_pilot.py](scripts/run_pilot.py) - Pilot orchestration
- [core/supplier_db.py](core/supplier_db.py) - Database import
- [core/spec_sheet_scraper.py](core/spec_sheet_scraper.py) - Spec sheet discovery

---

## Complete Workflow

```bash
# 1. Crawl abey.com.au
python scripts/crawl_abey.py --output abey_supplier_urls.csv

# 2. Import to database
python -c "
from core.supplier_db import get_supplier_db
import csv
db = get_supplier_db()
with open('abey_supplier_urls.csv') as f:
    reader = csv.DictReader(f)
    result = db.import_from_csv(list(reader), auto_extract_images=True)
    print(result)
"

# 3. Run pilot (spec sheet discovery + extraction)
python scripts/run_pilot.py --supplier abey.com.au --limit 50

# 4. Export low-confidence fields for review
python scripts/export_review_queue.py

# 5. Review manually in Excel
open review_queue_*.csv

# 6. Import reviewed data
python scripts/import_review_queue.py review_queue_*.csv

# 7. Apply to Shopify
python scripts/apply_to_shopify.py --collection sinks
```

---

## Summary

The Abey crawler provides:
- ✅ Automated product discovery
- ✅ SKU extraction (6 strategies)
- ✅ Polite crawling (rate limiting)
- ✅ CSV output for pipeline
- ✅ Error handling and recovery
- ✅ Progress tracking

**Result:** Ready-to-import CSV file that feeds directly into the enrichment pipeline!
