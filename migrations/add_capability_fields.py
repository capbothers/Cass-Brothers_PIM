#!/usr/bin/env python3
"""
Add boolean capability columns to shopify_products table
for Billi/Zip filtered water system products.

These columns track what each product can do:
- is_boiling: provides boiling water
- is_chilled: provides chilled water
- is_sparkling: provides sparkling water
- is_filtered: provides filtered water
- is_ambient: provides ambient (room temp) water
"""

import sqlite3


def migrate():
    conn = sqlite3.connect('supplier_products.db')
    cursor = conn.cursor()

    # Check existing columns
    cursor.execute("PRAGMA table_info(shopify_products)")
    existing_columns = [row[1] for row in cursor.fetchall()]

    capability_columns = {
        'is_boiling': 'INTEGER',
        'is_chilled': 'INTEGER',
        'is_sparkling': 'INTEGER',
        'is_filtered': 'INTEGER',
        'is_ambient': 'INTEGER',
    }

    added_count = 0
    for col_name, col_type in capability_columns.items():
        if col_name not in existing_columns:
            print(f"Adding {col_name} ({col_type})...")
            cursor.execute(f"""
                ALTER TABLE shopify_products
                ADD COLUMN {col_name} {col_type}
            """)
            added_count += 1
            print(f"  Added {col_name}")

    if added_count > 0:
        conn.commit()
        print(f"\nAdded {added_count} capability columns")
    else:
        print("All capability columns already exist")

    conn.close()


if __name__ == '__main__':
    migrate()
