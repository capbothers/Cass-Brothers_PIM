#!/usr/bin/env python3
"""
Add metafield columns to shopify_products table for storing enriched specs
"""

import sqlite3

def migrate():
    conn = sqlite3.connect('supplier_products.db')
    cursor = conn.cursor()

    # Check existing columns
    cursor.execute("PRAGMA table_info(shopify_products)")
    existing_columns = [row[1] for row in cursor.fetchall()]

    # Metafield columns to add
    metafield_columns = {
        'overall_width_mm': 'INTEGER',
        'overall_depth_mm': 'INTEGER',
        'overall_height_mm': 'INTEGER',
        'material': 'TEXT',
        'colour_finish': 'TEXT',
        'warranty_years': 'INTEGER',
        'weight_kg': 'REAL',
        'tap_hole_size_mm': 'INTEGER',
        'installation_type': 'TEXT',
        'flow_rate_lpm': 'REAL',
        'water_pressure_min_kpa': 'INTEGER',
        'water_pressure_max_kpa': 'INTEGER',
    }

    added_count = 0
    for col_name, col_type in metafield_columns.items():
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
        print(f"\n✓ Added {added_count} metafield columns")
    else:
        print("✓ All metafield columns already exist")

    conn.close()

if __name__ == '__main__':
    migrate()
