#!/usr/bin/env python3
"""
Add consolidated category fields to shopify_products table
"""

import sqlite3

def migrate():
    conn = sqlite3.connect('supplier_products.db')
    cursor = conn.cursor()

    # Check existing columns
    cursor.execute("PRAGMA table_info(shopify_products)")
    existing_columns = [row[1] for row in cursor.fetchall()]

    # Category fields to add
    category_fields = {
        'primary_category': 'TEXT',      # Basin Tapware, Kitchen Sinks, Toilets, etc.
        'product_category_type': 'TEXT', # For future subcategory (Wall Mounted, Bench Mount, etc.)
        'collection_name': 'TEXT',       # Alfresco, Urbane, etc.
    }

    added_count = 0
    for col_name, col_type in category_fields.items():
        if col_name not in existing_columns:
            print(f"Adding {col_name} ({col_type})...")
            cursor.execute(f"""
                ALTER TABLE shopify_products
                ADD COLUMN {col_name} {col_type}
            """)
            added_count += 1
            print(f"  ✓ Added {col_name}")

    if added_count > 0:
        conn.commit()
        print(f"\n✓ Added {added_count} category fields")
    else:
        print("✓ All category fields already exist")

    conn.close()

if __name__ == '__main__':
    migrate()
