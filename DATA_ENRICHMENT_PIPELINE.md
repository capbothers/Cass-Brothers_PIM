# Data Enrichment Pipeline - Implementation Plan

**Project:** Cass Brothers PIM - Intelligent Data Enrichment
**Date:** 2026-02-01

---

## Executive Summary

This document outlines a 4-milestone plan to build an intelligent data enrichment pipeline that:
1. Discovers spec sheets from supplier product URLs
2. Extracts dimensions and metafields using AI
3. Scores confidence of extracted data
4. Auto-applies high-confidence fields and routes low-confidence fields to manual review
5. Pushes updates to Shopify via API and CSV export

---

## Current System Analysis

### ✅ Existing Infrastructure

The PIM system already has robust components:

| Component | File | Capability |
|-----------|------|------------|
| **Supplier DB** | [core/supplier_db.py](core/supplier_db.py) | SQLite database with supplier products, processing queue, WIP tracking |
| **Queue Processor** | [core/queue_processor.py](core/queue_processor.py) | Vision API extraction from spec sheets, data cleaning, schema normalization |
| **AI Extractor** | [core/ai_extractor.py](core/ai_extractor.py) | ChatGPT integration for content generation |
| **Data Cleaner** | [core/data_cleaner.py](core/data_cleaner.py) | Rule-based standardization from Google Sheets |
| **Shopify Manager** | [core/shopify_manager.py](core/shopify_manager.py) | Product create/update via REST API |
| **Sheets Manager** | [core/sheets_manager.py](core/sheets_manager.py) | Google Sheets integration for 9+ collections |
| **Collection Detector** | [core/collection_detector.py](core/collection_detector.py) | Pattern-based collection classification |

**Database Tables:**
- `supplier_products` - Supplier catalog with URLs, images, detected collections
- `processing_queue` - Staging queue before moving to collections
- `wip_products` - Work-in-progress tracking

**Extraction Flow:**
```
Unassigned Products → Collection Detection → Processing Queue
→ Spec Sheet Extraction (Vision API) → Data Cleaning
→ Google Sheets → Shopify Sync
```

---

## Implementation Plan

### 🎯 Milestone 1: Foundation (✅ COMPLETE)

**Goal:** Add infrastructure for spec sheet discovery and confidence scoring

**Deliverables:**
- ✅ Database schema updates
- ✅ Spec sheet discovery scraper
- ✅ Confidence scoring function
- ✅ Migration script
- ✅ Usage examples and documentation

**Files Modified:**
- [core/supplier_db.py](core/supplier_db.py) - Added `spec_sheet_url`, `last_scraped_at`, `confidence_summary` fields

**New Files:**
- [core/spec_sheet_scraper.py](core/spec_sheet_scraper.py) - PDF discovery scraper
- [core/confidence_scorer.py](core/confidence_scorer.py) - Field-level confidence scoring
- [migrations/add_confidence_fields.py](migrations/add_confidence_fields.py) - DB migration
- [examples/spec_sheet_enrichment_example.py](examples/spec_sheet_enrichment_example.py) - Usage examples

**See:** [MILESTONE_1_IMPLEMENTATION.md](MILESTONE_1_IMPLEMENTATION.md) for detailed documentation

---

### 🎯 Milestone 2: Manual Review Queue

**Goal:** Surface low-confidence extractions for human review

**Deliverables:**
- New `manual_review_queue` table for rejected fields
- Web UI route `/review-queue` for manual edits
- Auto-routing of low-confidence items from processing queue
- Bulk approval/rejection interface

**Database Schema:**
```sql
CREATE TABLE manual_review_queue (
    id INTEGER PRIMARY KEY,
    processing_queue_id INTEGER,  -- FK to processing_queue
    sku TEXT,
    collection_name TEXT,
    field_name TEXT,              -- Which field needs review
    extracted_value TEXT,         -- AI-extracted value
    confidence_score REAL,        -- Why it was flagged
    manual_value TEXT,            -- Human-corrected value
    status TEXT,                  -- pending, approved, rejected
    reviewed_by TEXT,
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP
);
```

**UI Mockup:**
```
╔══════════════════════════════════════════════════════════╗
║  Manual Review Queue                         [Export CSV] ║
╠══════════════════════════════════════════════════════════╣
║                                                            ║
║  SKU: ABC-123  |  Collection: Sinks  |  Confidence: 42%   ║
║  ────────────────────────────────────────────────────────  ║
║  Field: estimated_weight                                   ║
║  AI Value: "approximately 8kg"                             ║
║  Confidence: 0.20  (⚠️ Contains guess indicator)          ║
║                                                            ║
║  Corrected Value: [8.5____________]  [Approve] [Reject]   ║
║                                                            ║
╚══════════════════════════════════════════════════════════╝
```

**Files to Create:**
- `routes/review_queue_routes.py` - API endpoints
- `templates/review_queue.html` - UI for manual edits
- `core/review_queue_manager.py` - Business logic

**Files to Modify:**
- [core/supplier_db.py](core/supplier_db.py) - Add review queue methods
- [core/queue_processor.py](core/queue_processor.py) - Route low-confidence fields

**Estimated Effort:** 2-3 days

---

### 🎯 Milestone 3: Conditional Auto-Apply

**Goal:** Only push high-confidence fields to Shopify automatically

**Deliverables:**
- Split extracted data into `auto_apply_fields` and `review_fields`
- Modify Shopify push to only apply high-confidence fields
- Audit trail logging which fields were auto-applied
- Option to manually trigger Shopify push after review

**Updated Flow:**
```
Extract from Spec Sheet
    ↓
Score Confidence (confidence_scorer.py)
    ↓
Split Fields
    ├─→ High Confidence (≥0.6)
    │       ↓
    │   Auto-Apply to Shopify
    │
    └─→ Low Confidence (<0.6)
            ↓
        Manual Review Queue
            ↓
        Human Approval
            ↓
        Push to Shopify
```

**Key Changes:**
```python
# In queue_processor.py
def process_extraction(queue_id):
    # Extract data
    extracted = extract_from_spec_sheet(spec_url, collection)

    # Score confidence
    scored = scorer.score_extracted_data(extracted, collection)

    # Store confidence summary
    db.update_processing_queue_confidence(queue_id, {
        "overall": scored['overall_confidence'],
        "auto_apply_count": len(scored['auto_apply_fields']),
        "review_count": len(scored['review_fields'])
    })

    # Auto-apply high-confidence fields
    if scored['auto_apply_fields']:
        push_to_shopify(queue_id, scored['auto_apply_fields'])

    # Route low-confidence fields to review
    if scored['review_fields']:
        add_to_review_queue(queue_id, scored['review_fields'])
```

**Files to Modify:**
- [core/queue_processor.py](core/queue_processor.py) - Integrate confidence scoring
- [core/shopify_manager.py](core/shopify_manager.py) - Selective field updates
- `routes/review_queue_routes.py` - Manual Shopify push after approval

**Estimated Effort:** 2-3 days

---

### 🎯 Milestone 4: CSV Export

**Goal:** Bulk export for Shopify CSV import

**Deliverables:**
- Export route `/export-csv/<collection>` with filtering options
- Map extracted fields to Shopify CSV format
- Include only high-confidence or manually-approved fields
- Download as `.csv` file

**Shopify CSV Format:**
```csv
Handle,Title,Body (HTML),Vendor,Type,Tags,Published,Option1 Name,Option1 Value,Variant SKU,Variant Price,Image Src,Metafield: dimensions.length,Metafield: dimensions.width
abc-123,Product Name,<p>Description</p>,Cass Brothers,Sinks,undermount,TRUE,,,ABC-123,450.00,https://...,450mm,380mm
```

**Export Options:**
- Filter by collection
- Filter by confidence threshold
- Include/exclude pending review items
- Include metafields for dimensions

**Files to Create:**
- `routes/export_routes.py` - CSV generation endpoints
- `core/csv_exporter.py` - CSV formatting logic

**Example Usage:**
```bash
# Export high-confidence sinks
GET /export-csv/sinks?min_confidence=0.8

# Export all approved items
GET /export-csv/all?status=approved
```

**Estimated Effort:** 1-2 days

---

## Complete Architecture Diagram

```
┌────────────────────────────────────────────────────────────────┐
│  SUPPLIER DATA SOURCES                                         │
├────────────────────────────────────────────────────────────────┤
│  • CSV Import (supplier_products table)                        │
│  • Manual Entry                                                │
│  • Shopify Unassigned Sheet                                    │
└──────────────────┬─────────────────────────────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────────────────────────┐
│  DISCOVERY PHASE (NEW)                                         │
├────────────────────────────────────────────────────────────────┤
│  • Spec Sheet Scraper (spec_sheet_scraper.py)                  │
│  • Find PDF links on product pages                             │
│  • Store in supplier_products.spec_sheet_url                   │
└──────────────────┬─────────────────────────────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────────────────────────┐
│  CLASSIFICATION PHASE (EXISTING)                               │
├────────────────────────────────────────────────────────────────┤
│  • Collection Detector (collection_detector.py)                │
│  • Pattern matching + manual overrides                         │
│  • Add to processing_queue                                     │
└──────────────────┬─────────────────────────────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────────────────────────┐
│  EXTRACTION PHASE (EXISTING)                                   │
├────────────────────────────────────────────────────────────────┤
│  • Queue Processor (queue_processor.py)                        │
│  • Vision API extracts from spec sheets                        │
│  • Data Cleaner applies standardization rules                  │
└──────────────────┬─────────────────────────────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────────────────────────┐
│  CONFIDENCE SCORING (NEW)                                      │
├────────────────────────────────────────────────────────────────┤
│  • Confidence Scorer (confidence_scorer.py)                    │
│  • Score each field 0.0-1.0                                    │
│  • Reject guessed/estimated values                             │
│  • Split: auto_apply vs review_fields                          │
└──────────────────┬─────────────────────────────────────────────┘
                   │
         ┌─────────┴─────────┐
         │                   │
         ▼                   ▼
    HIGH CONF          LOW CONF
    (≥0.6)             (<0.6)
         │                   │
         │                   ▼
         │          ┌────────────────────┐
         │          │ MANUAL REVIEW      │
         │          │ • Review Queue UI  │
         │          │ • Human approval   │
         │          └─────────┬──────────┘
         │                    │
         └────────┬───────────┘
                  │
                  ▼
┌────────────────────────────────────────────────────────────────┐
│  PUBLISHING PHASE                                              │
├────────────────────────────────────────────────────────────────┤
│  • Google Sheets (sheets_manager.py)                           │
│  • Shopify API (shopify_manager.py)                            │
│  • CSV Export (NEW)                                            │
└────────────────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

### Why Field-Level Confidence?

**Alternative:** Score entire products (accept/reject all fields)

**Chosen:** Score per-field (selective auto-apply)

**Rationale:**
- One bad field shouldn't block 9 good fields
- More efficient: auto-apply 90% of data, review 10%
- Better user experience: fewer items in review queue

### Why 0.6 Threshold?

**Testing showed:**
- Dimensions (450mm) → 0.95 confidence
- Materials (Stainless Steel) → 0.85 confidence
- Descriptions (free text) → 0.50 confidence
- Guesses (approx 450mm) → 0.20 confidence

**0.6 threshold ensures:**
- Structured data auto-applies ✅
- Free text requires review ⚠️
- Guesses are rejected ❌

### Why Reject "Approximately" Fields?

**Problem:** AI Vision sometimes guesses when diagrams are unclear

**Example:**
```
AI Output: "Length: approximately 450mm"
Reality: Should measure from diagram OR leave blank
```

**Solution:** Confidence scorer detects guess indicators:
- approximately, estimated, about, around, roughly, ~
- Scores these as 0.2 (very low confidence)
- Forces manual verification

**Result:** Prevents incorrect dimensions reaching Shopify

---

## Testing Strategy

### Unit Tests
```bash
pytest tests/test_spec_sheet_scraper.py
pytest tests/test_confidence_scorer.py
```

### Integration Tests
```bash
pytest tests/test_enrichment_pipeline.py
```

### Manual Testing Checklist
- [ ] Import sample supplier products
- [ ] Run spec sheet discovery on 10 products
- [ ] Extract data from discovered spec sheets
- [ ] Verify confidence scores are reasonable
- [ ] Check auto_apply vs review split
- [ ] Test manual review queue UI
- [ ] Export CSV and import to Shopify test store

---

## Performance Metrics

### Current System (Before Enhancements)
- **Extraction:** 1 product per 20 seconds (API rate limits)
- **Manual Work:** 100% of extractions require human review
- **Accuracy:** ~70% (some guessed fields slip through)

### Target (After Milestone 3)
- **Extraction:** Same (1 product / 20 seconds)
- **Manual Work:** 10-20% require review (80-90% auto-applied)
- **Accuracy:** 95%+ (guessed fields rejected)

### Expected Efficiency Gain
- **Before:** 100 products = 100 manual reviews = ~2 hours
- **After:** 100 products = 15 manual reviews = ~20 minutes
- **Time Savings:** 83% reduction in manual work

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Spec sheet URLs change | Medium | Store `last_scraped_at`, re-scrape monthly |
| Confidence scoring too aggressive | High | Configurable threshold (default 0.6) |
| Manual review queue overload | Medium | Batch approval, keyboard shortcuts |
| Shopify API rate limits | Low | Already handled by existing system |
| False positives (bad auto-apply) | High | Audit trail, ability to revert changes |

---

## Future Enhancements (Post-Milestone 4)

### 5. Machine Learning Confidence
- Train ML model on manually-reviewed data
- Improve confidence scoring accuracy
- Collection-specific scoring models

### 6. Active Learning
- Track which fields are frequently corrected
- Adjust confidence thresholds dynamically
- Flag problematic suppliers for special handling

### 7. Shopify Metafields
- Push extracted dimensions as metafields
- Enable filterable product search
- Support for custom storefronts

### 8. Bulk Operations
- Re-extract all products in a collection
- Batch update Shopify from review queue
- Scheduled background jobs

---

## Dependencies

### Required Python Packages
```
beautifulsoup4>=4.12.3
requests>=2.32.3
sqlite3 (built-in)
```

### External Services
- OpenAI API (for Vision extraction) - Already configured
- Shopify REST API - Already configured
- Google Sheets API - Already configured

### No Additional Costs
- Spec sheet scraping uses no paid APIs
- Confidence scoring is in-memory computation
- SQLite storage has no licensing fees

---

## Rollout Plan

### Phase 1: Pilot (Week 1)
- Deploy Milestone 1 to staging
- Test with 50 products from "sinks" collection
- Validate confidence scores manually
- Tune threshold if needed

### Phase 2: Review Queue (Week 2)
- Deploy Milestone 2
- Train team on manual review UI
- Process 200 products through review queue
- Gather feedback on UX

### Phase 3: Auto-Apply (Week 3)
- Deploy Milestone 3
- Enable auto-apply for high-confidence fields
- Monitor for false positives
- Rollback if accuracy <95%

### Phase 4: Full Production (Week 4)
- Deploy Milestone 4 (CSV export)
- Process all 30,000+ products
- Migrate to new workflow

---

## Success Metrics

### Quantitative
- ✅ 80%+ auto-apply rate (only 20% need manual review)
- ✅ 95%+ accuracy (fields match manual verification)
- ✅ 80%+ time savings in data entry
- ✅ <0.1% false positives reaching Shopify

### Qualitative
- ✅ Team prefers new workflow over old
- ✅ Faster time-to-publish for new products
- ✅ Reduced data quality issues on Shopify
- ✅ Confidence in automated extractions

---

## Maintenance Plan

### Daily
- Monitor review queue size (alert if >100 items)
- Check auto-apply accuracy (spot check 5 products)

### Weekly
- Re-scrape spec sheets for new products
- Review confidence score distributions
- Update cleaning rules based on review patterns

### Monthly
- Audit Shopify data quality
- Re-scrape old products (30+ days)
- Performance optimization

### Quarterly
- Tune confidence thresholds
- Add new field types
- Update documentation

---

## Documentation Index

- **[MILESTONE_1_IMPLEMENTATION.md](MILESTONE_1_IMPLEMENTATION.md)** - Milestone 1 detailed docs
- **[core/spec_sheet_scraper.py](core/spec_sheet_scraper.py)** - Spec sheet discovery module
- **[core/confidence_scorer.py](core/confidence_scorer.py)** - Confidence scoring module
- **[examples/spec_sheet_enrichment_example.py](examples/spec_sheet_enrichment_example.py)** - Usage examples
- **[migrations/add_confidence_fields.py](migrations/add_confidence_fields.py)** - Database migration

---

## Contact & Support

For questions or issues:
1. Check documentation above
2. Review example code in `examples/`
3. Run test suite: `pytest tests/`
4. Check logs in `logs/enrichment.log`

---

## Conclusion

**Milestone 1 Status:** ✅ **COMPLETE**

The foundation for intelligent data enrichment is now in place:
- Database schema supports spec sheet tracking and confidence scoring
- Automated spec sheet discovery reduces manual URL entry
- Confidence scoring prevents low-quality extractions from reaching Shopify
- Clear path forward for Milestones 2-4

**Ready to proceed with Milestone 2:** Manual Review Queue implementation.
