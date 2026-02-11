"""
Supplier Product Database Manager
Handles supplier product catalog and work-in-progress tracking
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
import logging

logger = logging.getLogger(__name__)


class SupplierDatabase:
    """Manage supplier products and WIP tracking"""

    def __init__(self, db_path: str = None):
        """Initialize supplier database"""
        if db_path is None:
            # Store in project directory alongside main cache
            project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(project_dir, 'supplier_products.db')

        self.db_path = db_path
        self._init_database()
        logger.info(f"✅ Supplier database initialized: {db_path}")

    def _init_database(self):
        """Create database tables if they don't exist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Supplier product catalog
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS supplier_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                supplier_name TEXT NOT NULL,
                product_url TEXT NOT NULL,
                product_name TEXT,
                image_url TEXT,
                spec_sheet_url TEXT,
                last_scraped_at TIMESTAMP,
                detected_collection TEXT,
                confidence_score REAL,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create indexes for fast lookups
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_sku ON supplier_products(sku)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_supplier ON supplier_products(supplier_name)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_collection ON supplier_products(detected_collection)
        ''')

        # Work-in-progress products
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS wip_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_product_id INTEGER NOT NULL,
                collection_name TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                sheet_row_number INTEGER,
                extracted_data TEXT,
                generated_content TEXT,
                error_message TEXT,
                user_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (supplier_product_id) REFERENCES supplier_products(id)
            )
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_wip_collection ON wip_products(collection_name)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_wip_status ON wip_products(status)
        ''')

        # Collection overrides for unassigned products
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS collection_overrides (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                collection_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_override_sku ON collection_overrides(sku)
        ''')

        # Processing queue for staging products before moving to collections
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processing_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                target_collection TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                run_id TEXT,
                shopify_product_id TEXT,
                shopify_handle TEXT,
                title TEXT,
                vendor TEXT,
                shopify_images TEXT,
                shopify_price TEXT,
                shopify_compare_price TEXT,
                shopify_status TEXT,
                shopify_weight TEXT,
                shopify_spec_sheet TEXT,
                body_html TEXT,
                extracted_images TEXT,
                extracted_data TEXT,
                confidence_summary TEXT,
                reviewed_data TEXT,
                applied_fields TEXT,
                applied_at TIMESTAMP,
                processing_notes TEXT,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP,
                approved_at TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_pq_sku ON processing_queue(sku)
        ''')

        # Shopify baseline snapshot (from export_shopify_products.py)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS shopify_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT,
                product_id TEXT,
                variant_id TEXT UNIQUE,
                vendor TEXT,
                title TEXT,
                product_type TEXT,
                status TEXT,
                handle TEXT,
                tags TEXT,
                price TEXT,
                compare_at_price TEXT,
                weight TEXT,
                image_src TEXT,
                body_html_length INTEGER,
                created_at TEXT,
                updated_at TEXT,
                meta_json TEXT,
                raw_json TEXT,
                imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_shopify_sku ON shopify_products(sku)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_shopify_vendor ON shopify_products(vendor)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_pq_collection ON processing_queue(target_collection)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_pq_status ON processing_queue(status)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_pq_run_id ON processing_queue(run_id)
        ''')

        conn.commit()
        conn.close()

    def import_from_csv(self, csv_data: List[Dict[str, str]], auto_extract_images: bool = True) -> Dict[str, Any]:
        """
        Import supplier products from CSV data

        Expected CSV columns:
        - sku: Product SKU
        - supplier_name: Supplier name
        - product_url: Product page URL
        - product_name: (optional) Product name
        - image_url: (optional) Direct image URL

        Args:
            csv_data: List of product dictionaries
            auto_extract_images: If True, automatically extract images from product URLs

        Returns dict with import statistics
        """
        from .image_extractor import extract_og_image
        from .collection_detector import detect_collection

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        imported = 0
        updated = 0
        skipped = 0
        images_extracted = 0
        errors = []

        for row in csv_data:
            try:
                sku = row.get('sku', '').strip()
                supplier_name = row.get('supplier_name', '').strip()
                product_url = row.get('product_url', '').strip()
                product_name = row.get('product_name', '').strip()
                image_url = row.get('image_url', '').strip()

                if not sku or not supplier_name or not product_url:
                    skipped += 1
                    continue

                # Auto-extract image if not provided and auto_extract is enabled
                if auto_extract_images and not image_url and product_url:
                    try:
                        logger.info(f"Extracting image for {sku}...")
                        extracted_image = extract_og_image(product_url, timeout=15)
                        if extracted_image:
                            image_url = extracted_image
                            images_extracted += 1
                            logger.info(f"✅ Extracted image for {sku}")
                    except Exception as e:
                        logger.warning(f"Failed to extract image for {sku}: {e}")

                # Auto-detect collection
                detected_collection = None
                confidence_score = 0.0
                if product_name or product_url:
                    detected_collection, confidence_score = detect_collection(
                        product_name or '', product_url
                    )

                # Check if SKU already exists
                cursor.execute('SELECT id FROM supplier_products WHERE sku = ?', (sku,))
                existing = cursor.fetchone()

                if existing:
                    # Update existing record
                    cursor.execute('''
                        UPDATE supplier_products
                        SET supplier_name = ?, product_url = ?, product_name = ?,
                            image_url = ?, detected_collection = ?, confidence_score = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE sku = ?
                    ''', (supplier_name, product_url, product_name, image_url,
                          detected_collection, confidence_score, sku))
                    updated += 1
                else:
                    # Insert new record
                    cursor.execute('''
                        INSERT INTO supplier_products
                        (sku, supplier_name, product_url, product_name, image_url,
                         detected_collection, confidence_score)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (sku, supplier_name, product_url, product_name, image_url,
                          detected_collection, confidence_score))
                    imported += 1

            except Exception as e:
                errors.append(f"Row {row}: {str(e)}")
                logger.error(f"Error importing row: {e}")

        conn.commit()
        conn.close()

        result = {
            'imported': imported,
            'updated': updated,
            'skipped': skipped,
            'images_extracted': images_extracted,
            'errors': errors,
            'total_processed': imported + updated + skipped
        }

        logger.info(f"📊 Import complete: {result}")
        return result

    def search_by_sku(self, sku_list: List[str]) -> List[Dict[str, Any]]:
        """Search for products by SKU list"""
        if not sku_list:
            return []

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        placeholders = ','.join('?' * len(sku_list))
        query = f'''
            SELECT * FROM supplier_products
            WHERE sku IN ({placeholders})
        '''

        cursor.execute(query, sku_list)
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_by_collection(self, collection_name: str, confidence_threshold: float = 0.9) -> List[Dict[str, Any]]:
        """Get products detected for a specific collection with high confidence"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM supplier_products
            WHERE detected_collection = ? AND confidence_score >= ?
            ORDER BY confidence_score DESC
        ''', (collection_name, confidence_threshold))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def update_collection_detection(self, sku: str, collection_name: str, confidence: float):
        """Update the detected collection for a product"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE supplier_products
            SET detected_collection = ?, confidence_score = ?, updated_at = CURRENT_TIMESTAMP
            WHERE sku = ?
        ''', (collection_name, confidence, sku))

        conn.commit()
        conn.close()

    def add_manual_product(self, sku: str, product_url: str, product_name: Optional[str] = None,
                          supplier_name: str = 'Manual Entry') -> int:
        """Add a manually entered product to supplier_products table"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT id FROM supplier_products WHERE sku = ?', (sku,))
        existing = cursor.fetchone()

        if existing:
            product_id = existing[0]
            cursor.execute('''
                UPDATE supplier_products
                SET product_url = ?, product_name = ?, supplier_name = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (product_url, product_name, supplier_name, product_id))
        else:
            cursor.execute('''
                INSERT INTO supplier_products (sku, product_url, product_name, supplier_name, image_url)
                VALUES (?, ?, ?, ?, NULL)
            ''', (sku, product_url, product_name, supplier_name))
            product_id = cursor.lastrowid

        conn.commit()
        conn.close()

        return product_id

    def add_to_wip(self, supplier_product_id: int, collection_name: str,
                    extracted_data: Dict[str, Any] = None) -> int:
        """Add a supplier product to work-in-progress

        Args:
            supplier_product_id: ID of the supplier product
            collection_name: Name of the target collection
            extracted_data: Optional pre-extracted data from spec sheet

        Returns:
            The ID of the new WIP entry
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if extracted_data:
            cursor.execute('''
                INSERT INTO wip_products (supplier_product_id, collection_name, status, extracted_data)
                VALUES (?, ?, 'pending', ?)
            ''', (supplier_product_id, collection_name, json.dumps(extracted_data)))
        else:
            cursor.execute('''
                INSERT INTO wip_products (supplier_product_id, collection_name, status)
                VALUES (?, ?, 'pending')
            ''', (supplier_product_id, collection_name))

        wip_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return wip_id

    def get_wip_products(self, collection_name: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get work-in-progress products for a collection

        Args:
            collection_name: Name of the collection
            status: Optional status filter. Can be:
                - Single status: 'pending'
                - Multiple statuses (comma-separated): 'pending,extracting,generating'
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if status:
            # Handle multiple statuses separated by commas
            statuses = [s.strip() for s in status.split(',')]

            if len(statuses) == 1:
                # Single status - simple query
                cursor.execute('''
                    SELECT
                        w.id as id,
                        w.supplier_product_id,
                        w.collection_name,
                        w.status,
                        w.sheet_row_number,
                        w.extracted_data,
                        w.generated_content,
                        w.error_message,
                        w.user_notes,
                        w.created_at,
                        w.updated_at,
                        w.completed_at,
                        s.sku,
                        s.supplier_name,
                        s.product_url,
                        s.product_name,
                        s.image_url,
                        s.detected_collection,
                        s.confidence_score
                    FROM wip_products w
                    JOIN supplier_products s ON w.supplier_product_id = s.id
                    WHERE w.collection_name = ? AND w.status = ?
                    ORDER BY w.created_at DESC
                ''', (collection_name, statuses[0]))
            else:
                # Multiple statuses - use IN clause
                placeholders = ','.join('?' * len(statuses))
                query = f'''
                    SELECT
                        w.id as id,
                        w.supplier_product_id,
                        w.collection_name,
                        w.status,
                        w.sheet_row_number,
                        w.extracted_data,
                        w.generated_content,
                        w.error_message,
                        w.user_notes,
                        w.created_at,
                        w.updated_at,
                        w.completed_at,
                        s.sku,
                        s.supplier_name,
                        s.product_url,
                        s.product_name,
                        s.image_url,
                        s.detected_collection,
                        s.confidence_score
                    FROM wip_products w
                    JOIN supplier_products s ON w.supplier_product_id = s.id
                    WHERE w.collection_name = ? AND w.status IN ({placeholders})
                    ORDER BY w.created_at DESC
                '''
                cursor.execute(query, [collection_name] + statuses)
        else:
            cursor.execute('''
                SELECT
                    w.id as id,
                    w.supplier_product_id,
                    w.collection_name,
                    w.status,
                    w.sheet_row_number,
                    w.extracted_data,
                    w.generated_content,
                    w.error_message,
                    w.user_notes,
                    w.created_at,
                    w.updated_at,
                    w.completed_at,
                    s.sku,
                    s.supplier_name,
                    s.product_url,
                    s.product_name,
                    s.image_url,
                    s.detected_collection,
                    s.confidence_score
                FROM wip_products w
                JOIN supplier_products s ON w.supplier_product_id = s.id
                WHERE w.collection_name = ?
                ORDER BY w.created_at DESC
            ''', (collection_name,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def update_wip_status(self, wip_id: int, status: str, extracted_data: Optional[Dict] = None):
        """Update WIP product status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if extracted_data:
            cursor.execute('''
                UPDATE wip_products
                SET status = ?, extracted_data = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (status, json.dumps(extracted_data), wip_id))
        else:
            cursor.execute('''
                UPDATE wip_products
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (status, wip_id))

        conn.commit()
        conn.close()

    def update_wip_sheet_row(self, wip_id: int, row_number: int):
        """Update WIP with Google Sheets row number"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE wip_products
            SET sheet_row_number = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (row_number, wip_id))

        conn.commit()
        conn.close()

    def update_wip_error(self, wip_id: int, error_message: str):
        """Update WIP with error message"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE wip_products
            SET error_message = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (error_message, wip_id))

        conn.commit()
        conn.close()

    def update_wip_generated_content(self, wip_id: int, generated_content: Dict):
        """Update WIP with generated content (descriptions, FAQs, etc)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE wip_products
            SET generated_content = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (json.dumps(generated_content), wip_id))

        conn.commit()
        conn.close()

    def remove_from_wip(self, wip_id: int) -> Optional[int]:
        """Remove product from WIP and return sheet row number if exists"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get sheet row number before deleting
        cursor.execute('SELECT sheet_row_number FROM wip_products WHERE id = ?', (wip_id,))
        result = cursor.fetchone()
        sheet_row = result[0] if result else None

        # Delete WIP entry
        cursor.execute('DELETE FROM wip_products WHERE id = ?', (wip_id,))

        conn.commit()
        conn.close()

        return sheet_row

    def complete_wip(self, wip_id: int):
        """Mark WIP product as completed and ready for approval"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE wip_products
            SET status = 'ready', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (wip_id,))

        conn.commit()
        conn.close()

    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Total supplier products
        cursor.execute('SELECT COUNT(*) FROM supplier_products')
        total_products = cursor.fetchone()[0]

        # Products by collection
        cursor.execute('''
            SELECT detected_collection, COUNT(*) as count
            FROM supplier_products
            WHERE detected_collection IS NOT NULL
            GROUP BY detected_collection
        ''')
        by_collection = {row[0]: row[1] for row in cursor.fetchall()}

        # WIP statistics
        cursor.execute('''
            SELECT status, COUNT(*) as count
            FROM wip_products
            GROUP BY status
        ''')
        wip_by_status = {row[0]: row[1] for row in cursor.fetchall()}

        conn.close()

        return {
            'total_products': total_products,
            'by_collection': by_collection,
            'wip_by_status': wip_by_status
        }

    # ==========================================================================
    # Spec Sheet Discovery Methods
    # ==========================================================================

    def update_spec_sheet_url(self, sku: str, spec_sheet_url: str) -> bool:
        """Update spec sheet URL for a supplier product"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE supplier_products
            SET spec_sheet_url = ?, last_scraped_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE sku = ?
        ''', (spec_sheet_url, sku))

        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return updated

    def get_products_without_spec_sheets(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get supplier products that don't have spec sheet URLs yet"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM supplier_products
            WHERE spec_sheet_url IS NULL OR spec_sheet_url = ''
            ORDER BY created_at DESC
            LIMIT ?
        ''', (limit,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_products_for_rescraping(self, days_old: int = 30, limit: int = 100) -> List[Dict[str, Any]]:
        """Get products whose spec sheets should be re-scraped (older than X days)"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM supplier_products
            WHERE last_scraped_at IS NULL
               OR last_scraped_at < datetime('now', '-' || ? || ' days')
            ORDER BY last_scraped_at ASC NULLS FIRST
            LIMIT ?
        ''', (days_old, limit))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    # ==========================================================================
    # Collection Override Methods
    # ==========================================================================

    def set_collection_override(self, sku: str, collection_name: str) -> bool:
        """Set or update a collection override for a SKU"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO collection_overrides (sku, collection_name, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(sku) DO UPDATE SET
                    collection_name = excluded.collection_name,
                    updated_at = CURRENT_TIMESTAMP
            ''', (sku, collection_name))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error setting collection override for {sku}: {e}")
            return False
        finally:
            conn.close()

    def get_collection_override(self, sku: str) -> Optional[str]:
        """Get collection override for a SKU, returns None if not set"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT collection_name FROM collection_overrides WHERE sku = ?
        ''', (sku,))
        row = cursor.fetchone()
        conn.close()

        return row[0] if row else None

    def get_all_collection_overrides(self) -> Dict[str, str]:
        """Get all collection overrides as a dict of sku -> collection_name"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT sku, collection_name FROM collection_overrides')
        rows = cursor.fetchall()
        conn.close()

        return {row[0]: row[1] for row in rows}

    def delete_collection_override(self, sku: str) -> bool:
        """Remove a collection override"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('DELETE FROM collection_overrides WHERE sku = ?', (sku,))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return deleted

    # ==========================================================================
    # Processing Queue Methods
    # ==========================================================================

    def add_to_processing_queue(self, product_data: Dict[str, Any], target_collection: str, run_id: str = None) -> int:
        """
        Add a product to the processing queue.

        Args:
            product_data: Dict with product info from unassigned products
            target_collection: The collection to move this product to after processing

        Returns:
            The ID of the new queue entry
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO processing_queue (
                sku, target_collection, status, run_id,
                shopify_product_id, shopify_handle, title, vendor,
                shopify_images, shopify_price, shopify_compare_price,
                shopify_status, shopify_weight, shopify_spec_sheet, body_html
            ) VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            product_data.get('variant_sku', ''),
            target_collection,
            run_id,
            product_data.get('id', ''),
            product_data.get('handle', ''),
            product_data.get('title', ''),
            product_data.get('vendor', ''),
            product_data.get('shopify_images', ''),
            product_data.get('shopify_price', ''),
            product_data.get('shopify_compare_price', ''),
            product_data.get('shopify_status', ''),
            product_data.get('shopify_weight', ''),
            product_data.get('shopify_spec_sheet', ''),
            product_data.get('body_html', '')
        ))

        queue_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return queue_id

    def add_batch_to_processing_queue(self, products: List[Dict[str, Any]], target_collection: str, run_id: str = None) -> Dict[str, Any]:
        """
        Add multiple products to the processing queue.

        Returns:
            Dict with added_count and skipped_skus (already in queue)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        added = 0
        skipped_skus = []

        for product in products:
            sku = product.get('variant_sku', '')
            if not sku:
                continue

            # Check if already in queue
            cursor.execute('SELECT id FROM processing_queue WHERE sku = ?', (sku,))
            if cursor.fetchone():
                skipped_skus.append(sku)
                continue

            cursor.execute('''
                INSERT INTO processing_queue (
                    sku, target_collection, status, run_id,
                    shopify_product_id, shopify_handle, title, vendor,
                    shopify_images, shopify_price, shopify_compare_price,
                    shopify_status, shopify_weight, shopify_spec_sheet, body_html
                ) VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                sku,
                target_collection,
                run_id,
                product.get('id', ''),
                product.get('handle', ''),
                product.get('title', ''),
                product.get('vendor', ''),
                product.get('shopify_images', ''),
                product.get('shopify_price', ''),
                product.get('shopify_compare_price', ''),
                product.get('shopify_status', ''),
                product.get('shopify_weight', ''),
                product.get('shopify_spec_sheet', ''),
                product.get('body_html', '')
            ))
            added += 1

        conn.commit()
        conn.close()

        return {
            'added_count': added,
            'skipped_skus': skipped_skus
        }

    def get_processing_queue(self, collection: str = None, status: str = None,
                             page: int = 1, limit: int = 50) -> Dict[str, Any]:
        """
        Get items from the processing queue with optional filtering.

        Args:
            collection: Filter by target collection
            status: Filter by status (pending, processing, ready, approved, error)
            page: Page number (1-indexed)
            limit: Items per page

        Returns:
            Dict with items, total, page, total_pages
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Build query with filters
        where_clauses = []
        params = []

        if collection:
            where_clauses.append('target_collection = ?')
            params.append(collection)

        if status:
            statuses = [s.strip() for s in status.split(',')]
            if len(statuses) == 1:
                where_clauses.append('status = ?')
                params.append(statuses[0])
            else:
                placeholders = ','.join('?' * len(statuses))
                where_clauses.append(f'status IN ({placeholders})')
                params.extend(statuses)

        where_sql = ' AND '.join(where_clauses) if where_clauses else '1=1'

        # Get total count
        cursor.execute(f'SELECT COUNT(*) FROM processing_queue WHERE {where_sql}', params)
        total = cursor.fetchone()[0]

        # Calculate pagination
        total_pages = max(1, (total + limit - 1) // limit)
        offset = (page - 1) * limit

        # Get items
        cursor.execute(f'''
            SELECT * FROM processing_queue
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        ''', params + [limit, offset])

        rows = cursor.fetchall()
        conn.close()

        return {
            'items': [dict(row) for row in rows],
            'total': total,
            'page': page,
            'total_pages': total_pages
        }

    def get_processing_queue_item(self, queue_id: int) -> Optional[Dict[str, Any]]:
        """Get a single item from the processing queue"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM processing_queue WHERE id = ?', (queue_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            item = dict(row)
            # Parse extracted_data JSON if present
            if item.get('extracted_data'):
                try:
                    item['extracted_data'] = json.loads(item['extracted_data'])
                except (json.JSONDecodeError, TypeError):
                    pass
            return item
        return None

    def update_processing_queue_status(self, queue_id: int, status: str,
                                       error_message: str = None,
                                       extracted_images: str = None,
                                       processing_notes: str = None) -> bool:
        """Update the status of a processing queue item"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        update_fields = ['status = ?', 'updated_at = CURRENT_TIMESTAMP']
        params = [status]

        if status == 'processing':
            update_fields.append('processed_at = CURRENT_TIMESTAMP')
        elif status == 'approved':
            update_fields.append('approved_at = CURRENT_TIMESTAMP')

        if error_message is not None:
            update_fields.append('error_message = ?')
            params.append(error_message)

        if extracted_images is not None:
            update_fields.append('extracted_images = ?')
            params.append(extracted_images)

        if processing_notes is not None:
            update_fields.append('processing_notes = ?')
            params.append(processing_notes)

        params.append(queue_id)

        cursor.execute(f'''
            UPDATE processing_queue
            SET {', '.join(update_fields)}
            WHERE id = ?
        ''', params)

        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return updated

    def remove_from_processing_queue(self, queue_id: int) -> bool:
        """Remove an item from the processing queue"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('DELETE FROM processing_queue WHERE id = ?', (queue_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return deleted

    def get_processing_queue_stats(self) -> Dict[str, Any]:
        """Get statistics for the processing queue"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Count by status
        cursor.execute('''
            SELECT status, COUNT(*) as count
            FROM processing_queue
            GROUP BY status
        ''')
        by_status = {row[0]: row[1] for row in cursor.fetchall()}

        # Count by collection
        cursor.execute('''
            SELECT target_collection, COUNT(*) as count
            FROM processing_queue
            GROUP BY target_collection
        ''')
        by_collection = {row[0]: row[1] for row in cursor.fetchall()}

        # Total
        cursor.execute('SELECT COUNT(*) FROM processing_queue')
        total = cursor.fetchone()[0]

        conn.close()

        return {
            'total': total,
            'by_status': by_status,
            'by_collection': by_collection
        }

    def import_shopify_baseline_rows(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Import Shopify baseline rows into shopify_products table."""
        if not rows:
            return {'imported': 0, 'skipped': 0}

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        imported = 0
        skipped = 0

        for row in rows:
            sku = row.get('sku', '') or None
            product_id = row.get('product_id', '') or None
            variant_id = row.get('variant_id', '') or None
            vendor = row.get('vendor', '') or None
            title = row.get('title', '') or None
            product_type = row.get('product_type', '') or None
            status = row.get('status', '') or None
            handle = row.get('handle', '') or None
            tags = row.get('tags', '') or None
            price = row.get('price', '') or None
            compare_at_price = row.get('compare_at_price', '') or None
            weight = row.get('weight', '') or None
            image_src = row.get('image_src', '') or None
            body_html_length = row.get('body_html_length') or None
            created_at = row.get('created_at', '') or None
            updated_at = row.get('updated_at', '') or None

            meta = {}
            for key, value in row.items():
                if key.startswith('meta_') and value not in (None, ''):
                    meta[key[5:]] = value

            if not variant_id and not sku:
                skipped += 1
                continue

            cursor.execute('''
                INSERT OR REPLACE INTO shopify_products (
                    sku, product_id, variant_id, vendor, title, product_type, status, handle,
                    tags, price, compare_at_price, weight, image_src, body_html_length,
                    created_at, updated_at, meta_json, raw_json, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                sku, product_id, variant_id, vendor, title, product_type, status, handle,
                tags, price, compare_at_price, weight, image_src, body_html_length,
                created_at, updated_at, json.dumps(meta), json.dumps(row)
            ))
            imported += 1

        conn.commit()
        conn.close()

        return {'imported': imported, 'skipped': skipped}

    def get_shopify_baseline_stats(self) -> Dict[str, Any]:
        """Get summary stats for the Shopify baseline table."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM shopify_products')
        total = cursor.fetchone()[0] or 0

        cursor.execute('SELECT COUNT(DISTINCT sku) FROM shopify_products')
        distinct_skus = cursor.fetchone()[0] or 0

        cursor.execute('SELECT COUNT(DISTINCT vendor) FROM shopify_products')
        distinct_vendors = cursor.fetchone()[0] or 0

        cursor.execute('SELECT MAX(imported_at) FROM shopify_products')
        last_imported = cursor.fetchone()[0]

        conn.close()

        return {
            'total_rows': total,
            'distinct_skus': distinct_skus,
            'distinct_vendors': distinct_vendors,
            'last_imported_at': last_imported,
        }

    def get_processing_queue_by_sku(self, sku: str) -> Optional[Dict[str, Any]]:
        """Check if a SKU is already in the processing queue"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM processing_queue WHERE sku = ?', (sku,))
        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None

    def update_processing_queue_extracted_data(self, queue_id: int, extracted_data: Dict[str, Any]) -> bool:
        """Update the extracted data for a processing queue item"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Ensure the extracted_data column exists
        try:
            cursor.execute("ALTER TABLE processing_queue ADD COLUMN extracted_data TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            # Column already exists
            pass

        cursor.execute('''
            UPDATE processing_queue
            SET extracted_data = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (json.dumps(extracted_data), queue_id))

        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return updated

    def update_processing_queue_notes(self, queue_id: int, notes: str) -> bool:
        """Update the notes field for a processing queue item (used for audit trail)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Ensure the notes column exists
        try:
            cursor.execute("ALTER TABLE processing_queue ADD COLUMN notes TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            # Column already exists
            pass

        cursor.execute('''
            UPDATE processing_queue
            SET notes = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (notes, queue_id))

        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return updated

    def update_processing_queue_confidence(self, queue_id: int, confidence_summary: Dict[str, Any]) -> bool:
        """Update confidence summary for a processing queue item"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE processing_queue
            SET confidence_summary = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (json.dumps(confidence_summary), queue_id))

        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return updated

    def update_processing_queue_reviewed_data(self, queue_id: int, reviewed_data: Dict[str, Any]) -> bool:
        """Update reviewed/corrected data for a processing queue item"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE processing_queue
            SET reviewed_data = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (json.dumps(reviewed_data), queue_id))

        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return updated

    def get_items_needing_review(self, confidence_threshold: float = 0.6) -> List[Dict[str, Any]]:
        """
        Get processing queue items with low-confidence fields needing manual review

        Args:
            confidence_threshold: Only return items with overall confidence below this

        Returns:
            List of queue items with their confidence summaries
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT pq.*, sp.supplier_name, sp.product_url, sp.spec_sheet_url
            FROM processing_queue pq
            LEFT JOIN supplier_products sp ON pq.sku = sp.sku
            WHERE pq.confidence_summary IS NOT NULL
              AND pq.confidence_summary != ''
            ORDER BY pq.created_at DESC
        ''')

        rows = cursor.fetchall()
        conn.close()

        # Filter items with low confidence
        items = []
        for row in rows:
            item = dict(row)
            # Parse confidence summary
            if item.get('confidence_summary'):
                try:
                    conf_summary = json.loads(item['confidence_summary'])
                    overall = conf_summary.get('overall_confidence', 1.0)
                    review_fields = conf_summary.get('review_fields', {})
                    review_count = len(review_fields) if isinstance(review_fields, dict) else 0
                    # Include if overall is low OR there are review fields
                    if overall < confidence_threshold or review_count > 0:
                        items.append(item)
                except (json.JSONDecodeError, TypeError):
                    pass

        return items

    def update_processing_queue_applied_fields(self, queue_id: int, applied_fields: Dict[str, Any]) -> bool:
        """
        Update applied_fields to track what was pushed to Shopify

        Args:
            queue_id: Processing queue ID
            applied_fields: Dict of field_name -> value that was applied

        Returns:
            True if updated successfully
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE processing_queue
            SET applied_fields = ?, applied_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (json.dumps(applied_fields), queue_id))

        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return updated

    def merge_extracted_data(self, existing: Dict[str, Any], extracted: Dict[str, Any],
                            strategy: str = 'conservative') -> Dict[str, Any]:
        """
        Merge extracted data with existing data using specified strategy.

        Args:
            existing: Existing data (e.g., from Shopify or previous extraction)
            extracted: Newly extracted data
            strategy: Merge strategy ('conservative', 'aggressive', 'reviewed_priority')

        Returns:
            Merged data dictionary

        Strategies:
            - conservative: Only update if existing field is empty/None
            - aggressive: Always use extracted data (overwrite)
            - reviewed_priority: Prefer reviewed_data > extracted > existing
        """
        merged = existing.copy() if existing else {}

        if strategy == 'conservative':
            # Only add new fields if they don't exist or are empty
            for key, value in extracted.items():
                if value is not None and value != '':
                    # Only update if existing is None, empty, or doesn't exist
                    existing_value = merged.get(key)
                    if existing_value is None or existing_value == '':
                        merged[key] = value

        elif strategy == 'aggressive':
            # Always use extracted data (overwrite everything)
            merged.update(extracted)

        elif strategy == 'reviewed_priority':
            # This will be used with reviewed_data
            # For now, same as conservative
            for key, value in extracted.items():
                if value is not None and value != '':
                    existing_value = merged.get(key)
                    if existing_value is None or existing_value == '':
                        merged[key] = value

        return merged

    def get_or_create_processing_queue(self, sku: str, product_data: Dict[str, Any],
                                      target_collection: str) -> Tuple[int, bool]:
        """
        Get existing processing queue item or create new one.

        Args:
            sku: Product SKU
            product_data: Product data dict
            target_collection: Target collection

        Returns:
            Tuple of (queue_id, created)
            - queue_id: ID of the processing queue item
            - created: True if new item was created, False if existing item was returned
        """
        # Check if SKU already exists in processing queue
        existing = self.get_processing_queue_by_sku(sku)

        if existing:
            logger.info(f"SKU {sku} already in processing queue (ID: {existing['id']})")
            return existing['id'], False

        # Create new entry
        queue_id = self.add_to_processing_queue(product_data, target_collection)
        logger.info(f"Created new processing queue entry for {sku} (ID: {queue_id})")
        return queue_id, True

    def get_product_by_sku(self, sku: str) -> Optional[Dict[str, Any]]:
        """Get a supplier product by SKU"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM supplier_products WHERE sku = ?', (sku,))
        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None


# Singleton instance
_supplier_db_instance = None


def get_supplier_db() -> SupplierDatabase:
    """Get singleton supplier database instance"""
    global _supplier_db_instance
    if _supplier_db_instance is None:
        _supplier_db_instance = SupplierDatabase()
    return _supplier_db_instance
