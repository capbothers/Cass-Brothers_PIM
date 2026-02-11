"""
Migration: Add spec_sheet_url, last_scraped_at, and confidence_summary fields
Date: 2026-02-01
"""

import sqlite3
import os
import logging

logger = logging.getLogger(__name__)


def run_migration(db_path: str = None):
    """
    Add new fields to support spec sheet discovery and confidence scoring:
    - supplier_products: spec_sheet_url, last_scraped_at
    - processing_queue: confidence_summary

    Args:
        db_path: Path to supplier_products.db (defaults to project root)
    """
    if db_path is None:
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(project_dir, 'supplier_products.db')

    if not os.path.exists(db_path):
        logger.warning(f"Database not found at {db_path}, skipping migration")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    migrations_applied = []

    try:
        # Add spec_sheet_url to supplier_products
        try:
            cursor.execute("ALTER TABLE supplier_products ADD COLUMN spec_sheet_url TEXT")
            migrations_applied.append("Added spec_sheet_url to supplier_products")
            logger.info("✅ Added spec_sheet_url column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("⏭️  spec_sheet_url already exists")
            else:
                raise

        # Add last_scraped_at to supplier_products
        try:
            cursor.execute("ALTER TABLE supplier_products ADD COLUMN last_scraped_at TIMESTAMP")
            migrations_applied.append("Added last_scraped_at to supplier_products")
            logger.info("✅ Added last_scraped_at column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("⏭️  last_scraped_at already exists")
            else:
                raise

        # Add confidence_summary to processing_queue
        try:
            cursor.execute("ALTER TABLE processing_queue ADD COLUMN confidence_summary TEXT")
            migrations_applied.append("Added confidence_summary to processing_queue")
            logger.info("✅ Added confidence_summary column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("⏭️  confidence_summary already exists")
            else:
                raise

        # Ensure extracted_data exists in processing_queue (should already be there)
        try:
            cursor.execute("ALTER TABLE processing_queue ADD COLUMN extracted_data TEXT")
            migrations_applied.append("Added extracted_data to processing_queue")
            logger.info("✅ Added extracted_data column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("⏭️  extracted_data already exists")
            else:
                raise

        conn.commit()

        if migrations_applied:
            logger.info(f"🎉 Migration complete! Applied {len(migrations_applied)} changes:")
            for change in migrations_applied:
                logger.info(f"   - {change}")
        else:
            logger.info("✅ All fields already exist, no migration needed")

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
    print("\n✅ Migration complete! New fields added:")
    print("   - supplier_products.spec_sheet_url")
    print("   - supplier_products.last_scraped_at")
    print("   - processing_queue.confidence_summary")
    print("   - processing_queue.extracted_data")
