"""
Migration: Add applied_fields and applied_at to processing_queue
Date: 2026-02-01
Part of Milestone 3: Conditional Shopify Auto-Apply
"""

import sqlite3
import os
import logging

logger = logging.getLogger(__name__)


def run_migration(db_path: str = None):
    """
    Add applied_fields and applied_at fields to processing_queue table

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

    try:
        # Add applied_fields to processing_queue
        try:
            cursor.execute("ALTER TABLE processing_queue ADD COLUMN applied_fields TEXT")
            conn.commit()
            logger.info("✅ Added applied_fields column to processing_queue")
            print("✅ Added applied_fields column to processing_queue")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("⏭️  applied_fields column already exists")
                print("⏭️  applied_fields column already exists")
            else:
                raise

        # Add applied_at to processing_queue
        try:
            cursor.execute("ALTER TABLE processing_queue ADD COLUMN applied_at TIMESTAMP")
            conn.commit()
            logger.info("✅ Added applied_at column to processing_queue")
            print("✅ Added applied_at column to processing_queue")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("⏭️  applied_at column already exists")
                print("⏭️  applied_at column already exists")
            else:
                raise

        logger.info("🎉 Migration complete!")
        print("\n✅ Migration complete! New fields added:")
        print("   - processing_queue.applied_fields (tracks fields pushed to Shopify)")
        print("   - processing_queue.applied_at (timestamp of last Shopify push)")

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
