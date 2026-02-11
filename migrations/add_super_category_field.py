#!/usr/bin/env python3
"""
Add super_category field for 3-tier navigation hierarchy
"""

import sqlite3

def migrate():
    conn = sqlite3.connect('supplier_products.db')
    cursor = conn.cursor()

    # Check existing columns
    cursor.execute("PRAGMA table_info(shopify_products)")
    existing_columns = [row[1] for row in cursor.fetchall()]

    if 'super_category' not in existing_columns:
        print("Adding super_category field...")
        cursor.execute("""
            ALTER TABLE shopify_products
            ADD COLUMN super_category TEXT
        """)
        conn.commit()
        print("✓ Added super_category field")
    else:
        print("✓ super_category field already exists")

    conn.close()

if __name__ == '__main__':
    migrate()
