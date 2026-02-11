#!/usr/bin/env python3
"""
ML Category Predictor for Shopify Products

Trains on LLM-enriched products to predict categories for remaining products.
Uses product title + vendor as features to predict super_category and primary_category.
"""

import sqlite3
import json
import pickle
import argparse
import re
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.metrics import classification_report


DB_PATH = 'supplier_products.db'
MODEL_PATH = 'models/category_predictor.pkl'

# Must match SUPER_CATEGORY_MAP in enrich_shopify_products.py
SUPER_CATEGORY_MAP = {
    "Basin Tapware": "Tapware",
    "Kitchen Tapware": "Tapware",
    "Bath Tapware": "Tapware",
    "Shower Tapware": "Tapware",
    "Basins": "Basins",
    "Toilets": "Toilets",
    "Bidets": "Toilets",
    "Urinals": "Toilets",
    "Smart Toilets": "Smart Toilets",
    "Baths": "Baths",
    "Kitchen Sinks": "Sinks",
    "Laundry Sinks": "Sinks",
    "Vanities": "Furniture",
    "Mirrors & Cabinets": "Furniture",
    "Showers": "Showers",
    "Shower Screens": "Showers",
    "Bathroom Accessories": "Accessories",
    "Kitchen Accessories": "Accessories",
    "Boiling Water Taps": "Boiling, Chilled & Sparkling",
    "Chilled Water Taps": "Boiling, Chilled & Sparkling",
    "Sparkling Water Taps": "Boiling, Chilled & Sparkling",
    "Filtered Water Systems": "Boiling, Chilled & Sparkling",
    "Kitchen Appliances": "Appliances",
    "Laundry Appliances": "Appliances",
    "Hot Water Systems": "Hot Water Systems",
    "Air Conditioning": "Heating & Cooling",
    "Heaters": "Heating & Cooling",
    "Ventilation": "Heating & Cooling",
    "Outdoor Products": "Hardware & Outdoor",
    "Drainage": "Hardware & Outdoor",
    "Assisted Living": "Assisted Living",
    "Aged Care": "Assisted Living",
}


def clean_title(title: str) -> str:
    """Clean product title for feature extraction"""
    if not title:
        return ''
    # Remove SKU patterns (usually at end after " - ")
    title = re.sub(r'\s*-\s*[A-Z0-9][A-Z0-9\-\./ ]*$', '', title)
    # Remove dimensions like 900x500
    title = re.sub(r'\d+x\d+', '', title)
    # Lowercase
    title = title.lower().strip()
    return title


def load_training_data():
    """Load enriched products as training data"""
    conn = sqlite3.connect(DB_PATH)

    df = pd.read_sql_query("""
        SELECT
            s.sku,
            s.title,
            s.vendor,
            s.product_type,
            s.tags,
            s.super_category,
            s.primary_category,
            s.product_category_type
        FROM shopify_products s
        WHERE s.primary_category IS NOT NULL
        AND s.super_category IS NOT NULL
        AND s.status = 'active'
        AND s.enriched_confidence >= 0.5
    """, conn)

    conn.close()
    return df


def load_prediction_data():
    """Load products that need category predictions"""
    conn = sqlite3.connect(DB_PATH)

    df = pd.read_sql_query("""
        SELECT
            s.id,
            s.sku,
            s.title,
            s.vendor,
            s.product_type,
            s.tags
        FROM shopify_products s
        WHERE s.primary_category IS NULL
        AND s.status = 'active'
    """, conn)

    conn.close()
    return df


def build_features(df):
    """Combine title + vendor + product_type into a single text feature"""
    features = []
    for _, row in df.iterrows():
        title = clean_title(str(row.get('title', '')))
        vendor = str(row.get('vendor', '')).lower()
        product_type = str(row.get('product_type', '')).lower()
        # Combine features with vendor repeated for emphasis
        text = f"{title} {vendor} {vendor} {product_type}"
        features.append(text)
    return features


def train_model(df):
    """Train category prediction models"""
    print("=" * 80)
    print("ML CATEGORY PREDICTOR - TRAINING")
    print("=" * 80)

    # Build features
    X_text = build_features(df)

    # Only train primary_category - derive super_category from map
    target = 'primary_category'
    print(f"\n--- Training: {target} ---")

    y = df[target].values

    # Filter out classes with too few samples
    class_counts = pd.Series(y).value_counts()
    valid_classes = class_counts[class_counts >= 3].index
    mask = pd.Series(y).isin(valid_classes).values

    X_filtered = [X_text[i] for i in range(len(X_text)) if mask[i]]
    y_filtered = y[mask]

    print(f"  Training samples: {len(X_filtered)}")
    print(f"  Categories: {len(valid_classes)}")
    print(f"  Dropped (< 3 samples): {len(class_counts) - len(valid_classes)} categories")

    # Build pipeline
    pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(
            max_features=5000,
            ngram_range=(1, 3),
            sublinear_tf=True,
            min_df=1
        )),
        ('clf', LogisticRegression(
            max_iter=1000,
            C=5.0,
            class_weight='balanced',
            solver='lbfgs'
        ))
    ])

    # Cross-validation
    n_splits = min(5, min(class_counts[class_counts >= 3]))
    if n_splits >= 2:
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
        scores = cross_val_score(pipeline, X_filtered, y_filtered, cv=cv, scoring='accuracy')
        print(f"  Cross-val accuracy: {scores.mean():.1%} (+/- {scores.std():.1%})")

    # Train on full dataset
    pipeline.fit(X_filtered, y_filtered)

    # Show per-category performance
    y_pred = pipeline.predict(X_filtered)
    print(f"\n  Training accuracy: {(y_pred == y_filtered).mean():.1%}")

    return {
        'pipeline': pipeline,
        'classes': list(valid_classes)
    }


def predict_categories(model, df):
    """Predict categories for unenriched products"""
    print("\n" + "=" * 80)
    print("ML CATEGORY PREDICTOR - PREDICTIONS")
    print("=" * 80)

    X_text = build_features(df)
    pipeline = model['pipeline']

    # Predict primary_category
    preds = pipeline.predict(X_text)
    probs = pipeline.predict_proba(X_text)
    max_probs = probs.max(axis=1)

    # Derive super_category from primary using the map
    super_cats = [SUPER_CATEGORY_MAP.get(p, 'Other') for p in preds]

    df['ml_primary_category'] = preds
    df['ml_primary_confidence'] = max_probs
    df['ml_super_category'] = super_cats

    return df


def save_predictions(df, dry_run=False):
    """Save ML predictions to database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    high_conf = 0
    medium_conf = 0
    low_conf = 0

    for _, row in df.iterrows():
        primary_conf = row['ml_primary_confidence']

        if primary_conf >= 0.7:
            high_conf += 1
        elif primary_conf >= 0.4:
            medium_conf += 1
        else:
            low_conf += 1

        if not dry_run and primary_conf >= 0.4:
            cursor.execute("""
                UPDATE shopify_products
                SET super_category = ?,
                    primary_category = ?,
                    enriched_confidence = ?,
                    enriched_at = ?
                WHERE id = ?
            """, (
                row['ml_super_category'],
                row['ml_primary_category'],
                round(float(primary_conf), 3),
                datetime.now().isoformat(),
                row['id']
            ))

    if not dry_run:
        conn.commit()
    conn.close()

    print(f"\n  High confidence (>=0.7): {high_conf} products")
    print(f"  Medium confidence (0.4-0.7): {medium_conf} products")
    print(f"  Low confidence (<0.4, skipped): {low_conf} products")

    if not dry_run:
        print(f"\n  Saved {high_conf + medium_conf} predictions to database")
    else:
        print(f"\n  DRY RUN - no changes saved")

    return high_conf, medium_conf, low_conf


def show_sample_predictions(df, n=30):
    """Show sample predictions for review"""
    print(f"\n--- Sample Predictions (random {n}) ---\n")

    sample = df.sample(min(n, len(df)), random_state=42)

    for _, row in sample.iterrows():
        conf_marker = "HIGH" if row['ml_primary_confidence'] >= 0.7 else \
                      "MED" if row['ml_primary_confidence'] >= 0.4 else "LOW"
        print(f"  [{conf_marker} {row['ml_primary_confidence']:.0%}] {row['title'][:70]}")
        print(f"    → {row['ml_super_category']} > {row['ml_primary_category']}")
        print()


def main():
    parser = argparse.ArgumentParser(description='ML Category Predictor')
    parser.add_argument('--dry-run', action='store_true', help='Preview predictions without saving')
    parser.add_argument('--train-only', action='store_true', help='Only train, skip predictions')
    parser.add_argument('--save-model', action='store_true', help='Save trained model to disk')
    args = parser.parse_args()

    # Step 1: Load training data
    print("Loading training data...")
    train_df = load_training_data()
    print(f"  Found {len(train_df)} enriched products for training")

    if len(train_df) < 50:
        print("  Not enough training data (need >= 50 products)")
        return

    # Step 2: Train model
    model = train_model(train_df)

    # Save model if requested
    if args.save_model:
        Path('models').mkdir(exist_ok=True)
        with open(MODEL_PATH, 'wb') as f:
            pickle.dump(model, f)
        print(f"\n  Model saved to {MODEL_PATH}")

    if args.train_only:
        return

    # Step 3: Load prediction data
    print("\nLoading products for prediction...")
    pred_df = load_prediction_data()
    print(f"  Found {len(pred_df)} products needing categories")

    if len(pred_df) == 0:
        print("  No products need predictions!")
        return

    # Step 4: Predict
    pred_df = predict_categories(model, pred_df)

    # Step 5: Show samples
    show_sample_predictions(pred_df)

    # Step 6: Category distribution
    print("\n--- Predicted Category Distribution ---\n")
    dist = pred_df.groupby(['ml_super_category', 'ml_primary_category']).size().reset_index(name='count')
    dist = dist.sort_values('count', ascending=False)
    for _, row in dist.iterrows():
        print(f"  {row['ml_super_category']:>20s} > {row['ml_primary_category']:<25s} ({row['count']})")

    # Step 7: Save
    print("\n--- Saving Predictions ---")
    high, med, low = save_predictions(pred_df, dry_run=args.dry_run)

    total = high + med + low
    print(f"\n{'=' * 80}")
    print(f"SUMMARY: {high + med}/{total} products categorized ({high} high, {med} medium confidence)")
    print(f"{'=' * 80}")


if __name__ == '__main__':
    main()
