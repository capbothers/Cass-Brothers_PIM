"""
Migration: Add run_id field to processing_queue
Date: 2026-02-01
"""

import sqlite3
import os
import logging

logger = logging.getLogger(__name__)


def run_migration(db_path: str = None):
    if db_path is None:
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(project_dir, 'supplier_products.db')

    if not os.path.exists(db_path):
        logger.warning(f"Database not found at {db_path}, skipping migration")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        try:
            cursor.execute("ALTER TABLE processing_queue ADD COLUMN run_id TEXT")
            logger.info("✅ Added run_id column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("⏭️  run_id already exists")
            else:
                raise

        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pq_run_id ON processing_queue(run_id)")
            logger.info("✅ Added run_id index")
        except sqlite3.OperationalError:
            pass

        conn.commit()
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
    print("\n✅ Migration complete! New field added:")
    print("   - processing_queue.run_id")
