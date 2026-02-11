import csv
import io

from flask import render_template, request, redirect, url_for, flash

from core.supplier_db import get_supplier_db


def setup_shopify_baseline_routes(app):
    db = get_supplier_db()

    @app.route('/shopify-baseline', methods=['GET'])
    def shopify_baseline():
        stats = db.get_shopify_baseline_stats()
        return render_template('shopify_baseline.html', stats=stats)

    @app.route('/shopify-baseline/import', methods=['POST'])
    def shopify_baseline_import():
        if 'baseline_csv' not in request.files:
            flash('Missing CSV file', 'error')
            return redirect(url_for('shopify_baseline'))

        file = request.files['baseline_csv']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(url_for('shopify_baseline'))

        try:
            content = file.read().decode('utf-8', errors='replace')
            reader = csv.DictReader(io.StringIO(content))
            rows = list(reader)
        except Exception as e:
            flash(f'Failed to read CSV: {e}', 'error')
            return redirect(url_for('shopify_baseline'))

        result = db.import_shopify_baseline_rows(rows)
        flash(f'Imported {result["imported"]} rows (skipped {result["skipped"]})', 'success')
        return redirect(url_for('shopify_baseline'))
