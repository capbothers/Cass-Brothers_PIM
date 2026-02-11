"""
Auto-approve low-risk fields in the review queue.

Usage:
    python scripts/auto_approve_low_risk.py
    python scripts/auto_approve_low_risk.py --fields title,brand_name,vendor
"""

import os
import sys
import json
import argparse
import importlib.util

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _import_module_from_path(module_name: str, relative_path: str):
    """Import a module by file path to avoid loading core/__init__.py."""
    module_path = os.path.join(REPO_ROOT, relative_path)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


supplier_db_module = _import_module_from_path("supplier_db", os.path.join("core", "supplier_db.py"))
get_supplier_db = supplier_db_module.get_supplier_db


DEFAULT_FIELDS = ["title", "brand_name", "vendor"]


def auto_approve(fields):
    db = get_supplier_db()

    import sqlite3
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, reviewed_data, confidence_summary
        FROM processing_queue
        WHERE confidence_summary IS NOT NULL
          AND confidence_summary != ''
        ORDER BY updated_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    updated = 0
    total_fields = 0

    for row in rows:
        queue_id = row["id"]
        reviewed_data = {}
        if row["reviewed_data"]:
            try:
                reviewed_data = json.loads(row["reviewed_data"])
            except (json.JSONDecodeError, TypeError):
                reviewed_data = {}

        try:
            conf_summary = json.loads(row["confidence_summary"])
        except (json.JSONDecodeError, TypeError):
            continue

        review_fields = conf_summary.get("review_fields", {})
        if not isinstance(review_fields, dict):
            continue

        auto_fields = {}
        for field in fields:
            value = review_fields.get(field)
            if value is not None and value != "":
                # Only fill if not already reviewed
                if field not in reviewed_data:
                    auto_fields[field] = value

        if auto_fields:
            reviewed_data.update(auto_fields)
            db.update_processing_queue_reviewed_data(queue_id, reviewed_data)
            updated += 1
            total_fields += len(auto_fields)

    print(f"Auto-approved {total_fields} fields across {updated} items.")


def main():
    parser = argparse.ArgumentParser(description="Auto-approve low-risk fields")
    parser.add_argument(
        "--fields",
        default=",".join(DEFAULT_FIELDS),
        help="Comma-separated list of fields to auto-approve"
    )
    args = parser.parse_args()

    fields = [f.strip() for f in args.fields.split(",") if f.strip()]
    auto_approve(fields)


if __name__ == "__main__":
    main()
