#!/usr/bin/env python3
"""
Add enrichment tracking fields to shopify_products table

Adds:
- enriched_at: timestamp when specs were enriched
- enriched_confidence: average confidence score from validation
"""

import sqlite3

def migrate():
    conn = sqlite3.connect('supplier_products.db')
    cursor = conn.cursor()

    # Check if fields already exist
    cursor.execute("PRAGMA table_info(shopify_products)")
    columns = [row[1] for row in cursor.fetchall()]

    if 'enriched_at' not in columns:
        print("Adding enriched_at column...")
        cursor.execute("""
            ALTER TABLE shopify_products
            ADD COLUMN enriched_at TEXT
        """)
        print("✓ Added enriched_at")

    if 'enriched_confidence' not in columns:
        print("Adding enriched_confidence column...")
        cursor.execute("""
            ALTER TABLE shopify_products
            ADD COLUMN enriched_confidence REAL
        """)
        print("✓ Added enriched_confidence")

    conn.commit()
    conn.close()
    print("\n✓ Migration complete")

if __name__ == '__main__':
    migrate()
