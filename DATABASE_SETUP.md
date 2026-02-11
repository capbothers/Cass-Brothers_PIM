# Database Setup

The PIM database is stored compressed in git due to GitHub's 100MB file size limit.

## First Time Setup

After cloning the repo, decompress the database:

```bash
gunzip supplier_products.db.gz
```

This will create `supplier_products.db` (147MB) with all 16,496 products.

## Database Contents

- **16,496 active products** across Tapware, Sinks, Basins, Baths, etc.
- **Enriched categories**: super_category → primary_category → product_category_type
- **Specifications**: dimensions, materials, colours, installation types, warranties
- **Supplier URLs**: 9,153 products (55.5% coverage)
- **WELS ratings**: imported and matched
- **Billi/Zip capabilities**: boolean capability flags for filtered water systems

## Database Files

- `supplier_products.db.gz` - Compressed main database (committed to git)
- `supplier_products.db` - Uncompressed working database (147MB, in .gitignore)
- `supplier_data.db` - Original supplier data (40MB, committed)

## Tables

- `shopify_products` - Main product table with all enriched data
- `supplier_products` - Supplier URLs and extracted specifications  
- `processing_queue` - Manual review queue
- `collection_overrides` - Custom collection assignments

See `SCHEMA_REPORT.md` for full schema documentation.
