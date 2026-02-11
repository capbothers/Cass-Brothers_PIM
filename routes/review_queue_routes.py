import json

from flask import render_template, request, redirect, url_for, flash

from core.supplier_db import get_supplier_db


def setup_review_queue_routes(app):
    db = get_supplier_db()

    @app.route('/review-queue', methods=['GET'])
    def review_queue():
        threshold = float(request.args.get('threshold', '0.6'))
        limit = int(request.args.get('limit', '200'))

        items = db.get_items_needing_review(confidence_threshold=threshold)
        rows = []

        for item in items[:limit]:
            extracted_data = {}
            reviewed_data = {}
            confidence_summary = {}

            if item.get('extracted_data'):
                try:
                    extracted_data = json.loads(item['extracted_data'])
                except (TypeError, json.JSONDecodeError):
                    extracted_data = {}

            if item.get('reviewed_data'):
                try:
                    reviewed_data = json.loads(item['reviewed_data'])
                except (TypeError, json.JSONDecodeError):
                    reviewed_data = {}

            if item.get('confidence_summary'):
                try:
                    confidence_summary = json.loads(item['confidence_summary'])
                except (TypeError, json.JSONDecodeError):
                    confidence_summary = {}

            review_fields = confidence_summary.get('review_fields', {}) or {}
            for field_name, field_info in review_fields.items():
                rows.append({
                    'queue_id': item.get('id'),
                    'sku': item.get('sku'),
                    'collection': item.get('target_collection'),
                    'title': item.get('title'),
                    'supplier_name': item.get('supplier_name'),
                    'product_url': item.get('product_url'),
                    'spec_sheet_url': item.get('spec_sheet_url'),
                    'field_name': field_name,
                    'extracted_value': extracted_data.get(field_name),
                    'confidence_score': field_info.get('confidence', ''),
                    'reason': field_info.get('reason', ''),
                    'approved_value': reviewed_data.get(field_name, ''),
                })

        return render_template(
            'review_queue.html',
            rows=rows,
            threshold=threshold,
            limit=limit,
            total_items=len(items),
        )

    @app.route('/review-queue/approve', methods=['POST'])
    def review_queue_approve():
        queue_id = request.form.get('queue_id')
        field_name = request.form.get('field_name')
        approved_value = request.form.get('approved_value', '').strip()

        if not queue_id or not field_name:
            flash('Missing queue_id or field_name', 'error')
            return redirect(url_for('review_queue'))

        if approved_value == '':
            flash('Approved value is required', 'error')
            return redirect(url_for('review_queue'))

        item = db.get_processing_queue_item(int(queue_id))
        reviewed_data = {}
        if item and item.get('reviewed_data'):
            try:
                reviewed_data = json.loads(item['reviewed_data'])
            except (TypeError, json.JSONDecodeError):
                reviewed_data = {}

        reviewed_data[field_name] = approved_value
        db.update_processing_queue_reviewed_data(int(queue_id), reviewed_data)

        flash(f'Approved {field_name} for SKU {item.get("sku") if item else queue_id}', 'success')
        return redirect(url_for('review_queue'))
