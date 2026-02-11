"""
Generate product descriptions and features from extracted data.

Usage:
    python scripts/generate_content.py --run-id 20260201_063403 --limit 20
    python scripts/generate_content.py --sku ABC-123
    python scripts/generate_content.py --dry-run
"""

import os
import sys
import json
import argparse
import importlib.util
from datetime import datetime
from typing import Dict, Any, List

import requests
from dotenv import load_dotenv

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(REPO_ROOT, '.env'))


def _import_module_from_path(module_name: str, relative_path: str):
    """Import a module by file path to avoid loading core/__init__.py."""
    module_path = os.path.join(REPO_ROOT, relative_path)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


supplier_db_module = _import_module_from_path("supplier_db", os.path.join("core", "supplier_db.py"))
get_supplier_db = supplier_db_module.get_supplier_db


def _merge_extracted_and_reviewed(item: Dict[str, Any]) -> Dict[str, Any]:
    extracted = {}
    reviewed = {}
    if item.get("extracted_data"):
        try:
            extracted = json.loads(item["extracted_data"])
        except (json.JSONDecodeError, TypeError):
            extracted = {}
    if item.get("reviewed_data"):
        try:
            reviewed = json.loads(item["reviewed_data"])
        except (json.JSONDecodeError, TypeError):
            reviewed = {}

    merged = dict(extracted)
    merged.update(reviewed)
    return merged


def _strip_supplier_refs(fields: Dict[str, Any]) -> Dict[str, Any]:
    """Remove supplier URL/domain references from field values."""
    cleaned = {}
    for k, v in fields.items():
        if isinstance(v, str):
            lower = v.lower()
            if "http://" in lower or "https://" in lower:
                continue
            if "abey.com.au" in lower:
                continue
            if "exclusive to" in lower:
                continue
        cleaned[k] = v
    return cleaned


def _build_prompt(item: Dict[str, Any], fields: Dict[str, Any]) -> str:
    title = item.get("title") or item.get("sku") or "Product"
    collection = item.get("target_collection") or "product"
    vendor = item.get("vendor") or ""

    # Keep fields concise for prompt
    important_fields = {k: v for k, v in fields.items() if v not in [None, "", []]}
    important_fields = _strip_supplier_refs(important_fields)

    prompt = f"""You are a product data writer. Write factual, neutral copy.

Product title: {title}
Collection: {collection}
Vendor/Brand: {vendor}
Specs (JSON): {json.dumps(important_fields, ensure_ascii=False)}

Rules:
- Description: 1-2 factual sentences, plain HTML <p>...</p> only.
- Features: 4-6 bullet points from specs only.
- Do NOT invent specs or marketing claims.
- Do NOT mention supplier URLs or domain names.
- If brand/vendor is a URL, omit it.
- Return JSON with keys: body_html (string), features (array of strings).
"""
    return prompt


def _call_openai(prompt: str) -> Dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")

    payload = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o"),
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 600,
        "response_format": {"type": "json_object"}
    }

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        },
        json=payload,
        timeout=60
    )
    response.raise_for_status()
    result = response.json()
    content = result["choices"][0]["message"]["content"]
    return json.loads(content)


def _clean_features(features: List[str]) -> List[str]:
    cleaned = []
    for f in features or []:
        lower = f.lower()
        if "abey.com.au" in lower or "http" in lower or "exclusive to" in lower:
            continue
        if "not specified" in lower or "unknown" in lower or "n/a" in lower:
            continue
        cleaned.append(f)
    return cleaned


def _update_content_in_db(db, queue_id: int, body_html: str, features: List[str], dry_run: bool):
    features = _clean_features(features)
    features_text = "\n".join([f"- {f}".strip() for f in features]) if features else ""
    if dry_run:
        return

    import sqlite3
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # Merge features into reviewed_data so export includes them
    cursor.execute("SELECT reviewed_data FROM processing_queue WHERE id = ?", (queue_id,))
    row = cursor.fetchone()
    reviewed = {}
    if row and row[0]:
        try:
            reviewed = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            reviewed = {}

    if features_text:
        reviewed["features"] = features_text

    cursor.execute('''
        UPDATE processing_queue
        SET body_html = ?, reviewed_data = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (body_html, json.dumps(reviewed), queue_id))

    conn.commit()
    conn.close()


def generate_for_items(items: List[Dict[str, Any]], dry_run: bool = False):
    db = get_supplier_db()
    successes = 0
    failures = 0

    for item in items:
        queue_id = item["id"]
        fields = _merge_extracted_and_reviewed(item)

        # Skip if no meaningful fields
        if not fields:
            failures += 1
            continue

        prompt = _build_prompt(item, fields)

        try:
            result = _call_openai(prompt)
            body_html = result.get("body_html", "")
            features = result.get("features", [])

            _update_content_in_db(db, queue_id, body_html, features, dry_run)
            successes += 1
        except Exception as e:
            print(f"⚠️  Failed for SKU {item.get('sku')}: {e}")
            failures += 1

    print(f"\nGenerated content for {successes} items, failed: {failures}")


def main():
    parser = argparse.ArgumentParser(description="Generate descriptions and features")
    parser.add_argument("--run-id", help="Only process items from a specific run_id")
    parser.add_argument("--sku", help="Process a specific SKU")
    parser.add_argument("--limit", type=int, default=50, help="Max items to process")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    db = get_supplier_db()

    if args.sku:
        item = db.get_processing_queue_by_sku(args.sku)
        if not item:
            print(f"SKU {args.sku} not found in processing_queue")
            sys.exit(1)
        items = [item]
    else:
        result = db.get_processing_queue(status=None, limit=args.limit)
        items = result["items"]
        if args.run_id:
            items = [i for i in items if i and i.get("run_id") == args.run_id]

    if not items:
        print("No items to process")
        return

    print(f"Processing {len(items)} items for content generation...")
    generate_for_items(items, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
