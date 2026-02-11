# Super Category Mapping (3-Tier Navigation)

Navigation hierarchy: **Home > Super Category > Primary Category > Product Type**

Example: **Home > Tapware > Basin Tapware > Wall Mounted**

---

## Super Category Groupings

### 1. TAPWARE
**Primary Categories:**
- Basin Tapware
- Kitchen Tapware
- Bath Tapware
- Shower Tapware

**Example Path:**
- Home > Tapware > Basin Tapware > Bench Mount
- Home > Tapware > Kitchen Tapware > Pull-Out Spray

---

### 2. BASINS
**Primary Categories:**
- Basins

**Example Path:**
- Home > Basins > Wall Hung
- Home > Basins > Countertop

---

### 3. TOILETS
**Primary Categories:**
- Toilets
- Bidets
- Urinals

**Example Path:**
- Home > Toilets > Wall Hung
- Home > Toilets > Back To Wall

---

### 4. BATHS
**Primary Categories:**
- Baths

**Example Path:**
- Home > Baths > Freestanding
- Home > Baths > Built-In

---

### 5. SINKS
**Primary Categories:**
- Kitchen Sinks
- Laundry Sinks

**Example Path:**
- Home > Sinks > Kitchen Sinks > Undermount
- Home > Sinks > Laundry Sinks > Topmount

---

### 6. FURNITURE
**Primary Categories:**
- Vanities
- Mirrors & Cabinets

**Example Path:**
- Home > Furniture > Vanities > Wall Hung
- Home > Furniture > Mirrors & Cabinets > Shaving Cabinets

---

### 7. SHOWER COMPONENTS
**Primary Categories:**
- Showers
- Shower Screens

**Example Path:**
- Home > Shower Components > Showers > Rain Shower
- Home > Shower Components > Shower Screens > Frameless

---

### 8. ACCESSORIES
**Primary Categories:**
- Bathroom Accessories
- Kitchen Accessories

**Example Path:**
- Home > Accessories > Bathroom Accessories > Heated Towel Rail
- Home > Accessories > Kitchen Accessories > Sink Strainer

---

### 9. OTHER
**Primary Categories:**
- Appliances
- Drainage
- Skylights

**Example Path:**
- Home > Other > Appliances > Instant Hot Water
- Home > Other > Drainage > Linear Waste

---

## Complete 3-Tier Structure

```
Home
├── Tapware (15,000+ products)
│   ├── Basin Tapware (7,160)
│   │   ├── Bench Mount
│   │   ├── Wall Mounted
│   │   └── Three Piece
│   ├── Kitchen Tapware (3,852)
│   │   ├── Pull-Out Spray
│   │   ├── Filtered
│   │   └── Standard
│   ├── Bath Tapware (2,173)
│   │   ├── Bath Mixers
│   │   └── Bath Spouts
│   └── Shower Tapware (1,890)
│       ├── Wall Mixers
│       └── Shower Mixers
│
├── Basins
│   ├── Wall Hung
│   ├── Countertop
│   └── Undermount
│
├── Toilets (7,416 products)
│   ├── Wall Hung
│   ├── Floor Mounted
│   ├── In-Wall
│   ├── Smart Toilet
│   ├── Bidets
│   └── Urinals
│
├── Baths
│   ├── Freestanding
│   └── Built-In
│
├── Sinks
│   ├── Kitchen Sinks
│   │   ├── Undermount
│   │   ├── Topmount
│   │   └── Butler
│   └── Laundry Sinks
│       ├── Single Bowl
│       └── Double Bowl
│
├── Furniture
│   ├── Vanities
│   │   ├── Wall Hung
│   │   ├── Freestanding
│   │   └── Floor Mounted
│   └── Mirrors & Cabinets
│       ├── Round Mirrors
│       ├── Rectangular Mirrors
│       └── Shaving Cabinets
│
├── Shower Components
│   ├── Showers
│   │   ├── Rain Shower
│   │   ├── Hand Shower
│   │   └── Shower Rails
│   └── Shower Screens
│       ├── Frameless
│       └── Semi-Frameless
│
├── Accessories
│   ├── Bathroom Accessories
│   │   ├── Towel Rails
│   │   ├── Toilet Roll Holders
│   │   └── Shelves
│   └── Kitchen Accessories
│       ├── Sink Strainers
│       └── Colanders
│
└── Other
    ├── Appliances
    ├── Drainage
    └── Skylights
```

---

## Benefits of 3-Tier Structure

1. **Cleaner Main Navigation** - 9 super categories instead of 20 primary categories
2. **Logical Grouping** - Related products grouped together (all tapware under "Tapware")
3. **Easier to Scale** - Add new primary categories without cluttering main menu
4. **Better Mobile Experience** - Fewer top-level menu items
5. **Matches Customer Mental Model** - "I need basins" → Direct access!

---

## Shopify Implementation

### Metafields
```json
{
  "super_category": "Tapware",
  "primary_category": "Basin Tapware",
  "product_category_type": "Wall Mounted"
}
```

### Collections Structure
- Create **9 super category collections** (manual or automated)
- Create **20 primary category collections** (automated by metafield)
- Use **product_category_type** for filtering within collections

### Navigation Menu
```
Tapware (links to /collections/tapware)
  └─ Basin Tapware (links to /collections/basin-tapware)
  └─ Kitchen Tapware (links to /collections/kitchen-tapware)
  └─ Bath Tapware (links to /collections/bath-tapware)
  └─ Shower Tapware (links to /collections/shower-tapware)

Basins (links to /collections/basins)
  └─ Direct to products (filtered by product_category_type)

Toilets (links to /collections/toilets)
  └─ Direct to products (includes Bidets, Urinals)

Baths (links to /collections/baths)
  └─ Direct to products (filtered by product_category_type)
```

---

## Automatic Assignment

The enrichment pipeline will automatically assign `super_category` based on `primary_category`:

```python
SUPER_CATEGORY_MAP = {
    "Basin Tapware": "Tapware",
    "Kitchen Tapware": "Tapware",
    "Bath Tapware": "Tapware",
    "Shower Tapware": "Tapware",
    "Basins": "Basins",
    "Toilets": "Toilets",
    "Bidets": "Toilets",
    "Urinals": "Toilets",
    "Baths": "Baths",
    "Kitchen Sinks": "Sinks",
    "Laundry Sinks": "Sinks",
    "Vanities": "Furniture",
    "Mirrors & Cabinets": "Furniture",
    "Showers": "Shower Components",
    "Shower Screens": "Shower Components",
    "Bathroom Accessories": "Accessories",
    "Kitchen Accessories": "Accessories",
    "Appliances": "Other",
    "Drainage": "Other",
    "Skylights": "Other"
}
```

No manual mapping needed - fully automatic!
