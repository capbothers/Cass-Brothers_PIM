"""
Migration: Add reviewed_data field to processing_queue
Date: 2026-02-01
Part of Milestone 2: Manual Review Queue
"""

import sqlite3
import os
import logging

logger = logging.getLogger(__name__)


def run_migration(db_path: str = None):
    """
    Add reviewed_data field to processing_queue table

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
        # Add reviewed_data to processing_queue
        try:
            cursor.execute("ALTER TABLE processing_queue ADD COLUMN reviewed_data TEXT")
            conn.commit()
            logger.info("✅ Added reviewed_data column to processing_queue")
            print("✅ Added reviewed_data column to processing_queue")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("⏭️  reviewed_data column already exists")
                print("⏭️  reviewed_data column already exists")
            else:
                raise

        logger.info("🎉 Migration complete!")
        print("\n✅ Migration complete! New field added:")
        print("   - processing_queue.reviewed_data (stores manually reviewed field values)")

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
