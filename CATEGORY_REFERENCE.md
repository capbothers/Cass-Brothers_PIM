# Product Category Reference Guide

Complete reference for standardized category values used in the enrichment pipeline.

## 3-Tier Navigation Structure

**Navigation Path:** Home > Super Category > Primary Category > Product Type

**Example:** Home > Tapware > Basin Tapware > Wall Mounted

### Fields:
- `super_category`: Top-level grouping (15 options)
- `primary_category`: Main product category (30+ options)
- `product_category_type`: Subcategory for filtering (varies by product)

---

## Super Categories (super_category)

**15 top-level navigation categories:**

1. **Tapware** - Basin, Kitchen, Bath, Shower tapware
2. **Basins** - All basin products
3. **Toilets** - Standard toilets, bidets, urinals
4. **Smart Toilets** - Smart toilet systems
5. **Baths** - All bath products
6. **Sinks** - Kitchen and laundry sinks
7. **Furniture** - Vanities, mirrors, cabinets
8. **Showers** - Showers, shower screens
9. **Accessories** - Bathroom and kitchen accessories
10. **Boiling, Chilled & Sparkling** - Specialty water systems (Zip, Billi)
11. **Appliances** - Kitchen and laundry appliances
12. **Hot Water Systems** - Continuous flow, storage, heat pumps
13. **Heating & Cooling** - Air conditioning, heaters, ventilation
14. **Hardware & Outdoor** - Outdoor products, skylights, drainage
15. **Assisted Living** - Accessibility and aged care products

---

## Primary Categories (primary_category)

**Expanded to 30+ categories:**

### Tapware Categories
1. **Basin Tapware** - Basin mixers, basin taps, basin wall mixers, bench mount mixers, three piece tapware
2. **Kitchen Tapware** - Sink mixers, kitchen mixers, filtered water taps, pull-out spray mixers
3. **Bath Tapware** - Bath mixers, bath wall mixers, bath spouts, bath fillers
4. **Shower Tapware** - Shower mixers, wall mixers, diverters

### Core Bathroom Categories
5. **Basins** - All types of basins/washbasins
6. **Toilets** - Standard toilets (not smart)
7. **Smart Toilets** - Integrated smart toilet systems
8. **Baths** - Freestanding baths, built-in baths, corner baths
9. **Bidets** - Bidet fixtures
10. **Urinals** - Commercial urinals

### Sink Categories
11. **Kitchen Sinks** - Kitchen sinks, bar sinks
12. **Laundry Sinks** - Laundry tubs and sinks

### Furniture & Storage
13. **Vanities** - Vanity units (wall hung, freestanding, floor mounted)
14. **Mirrors & Cabinets** - Bathroom mirrors, mirror cabinets, shaving cabinets

### Showers
15. **Showers** - Shower heads, hand showers, shower rails, shower sets
16. **Shower Screens** - Shower enclosures and screens

### Accessories
17. **Bathroom Accessories** - Towel rails, toilet roll holders, shelves, hooks, soap dispensers
18. **Kitchen Accessories** - Sink accessories, drainer trays, colanders

### Specialty Water Systems
19. **Boiling Water Taps** - Instant boiling water systems
20. **Chilled Water Taps** - Chilled water dispensers
21. **Sparkling Water Taps** - Sparkling water systems
22. **Filtered Water Systems** - Water filtration systems

### Appliances
23. **Kitchen Appliances** - Rangehoods, ovens, cooktops, dishwashers
24. **Laundry Appliances** - Washing machines, dryers

### Hot Water Systems
25. **Continuous Flow** - Tankless instant hot water
26. **Storage Water Heaters** - Tank-based hot water systems
27. **Heat Pumps** - Heat pump hot water systems

### Heating & Cooling
28. **Air Conditioning** - Split systems, ducted systems
29. **Heaters** - Indoor and outdoor heaters
30. **Underfloor Heating** - In-floor heating systems
31. **Ventilation** - Exhaust fans, ventilation systems

### Hardware & Outdoor
32. **Outdoor Products** - Outdoor kitchens, outdoor showers
33. **Skylights** - Roof windows and skylights
34. **Drainage** - Linear wastes, floor wastes, grates

### Assisted Living
35. **Assisted Living** - Accessibility fixtures and aged care products
36. **Aged Care** - Specialized aged care bathroom products

---

## Product Category Type (product_category_type)

**Subcategories that describe installation/mounting type:**

### Basin Types
- Countertop / Above Counter
- Wall Hung
- Undermount
- Semi-Recessed
- Inset / Top Mount
- Pedestal
- Vessel
- Corner

### Toilet Types
- Wall Hung
- Floor Mounted / Close Coupled
- Back To Wall
- In-Wall / Concealed Cistern
- Smart Toilet
- Wall Faced

### Tapware Types
- Bench Mount / Deck Mount
- Wall Mounted
- Floor Mounted
- Three Piece Set
- Single Lever
- Two Handle
- Pull-Out Spray
- Filtered

### Sink Types
- Topmount / Inset
- Undermount
- Flush Mount
- Butler / Farmhouse
- Single Bowl
- Double Bowl
- One and a Quarter Bowl

### Bath Types
- Freestanding
- Built-In / Drop-In
- Corner
- Island
- Back To Wall

### Vanity Types
- Wall Hung
- Freestanding
- Floor Mounted
- Double Basin
- Single Basin

### Shower Types
- Rail Shower
- Hand Shower
- Overhead Shower
- Multifunction
- Dual Shower

### Accessory Types
- Single Rail
- Double Rail
- Ladder Rail
- Heated
- Corner Shelf
- Linear Shelf

---

## Collection Names (collection_name)

**Common brand collections/ranges from suppliers:**

### Abey Collections
- Alfresco
- Barazza
- Boutique Lugano
- Schock
- Lago

### Caroma Collections
- Urbane
- Luna
- Leda
- Contura
- Opal
- Signature
- Profile
- Coolibah
- Caravelle
- Tasman
- Somerton
- Cosmo
- Vitra
- Forma

### Fienza Collections
- Koko
- Axel
- Luciana
- Alessio
- Enzo
- Mayfair
- Tuscany
- Byron
- Vela
- Poco
- Uno
- Bronte

### Phoenix Tapware Collections
- Vivid Slimline
- Tapware Series
- Rush
- Mekko
- Radii
- Lexi
- Toi

### Arcisan Collections
- Synergii
- Axus
- Zara
- Resonance
- Komodo

### Linsol Collections
- Como
- Capo
- Capri
- Curva
- Ella

### Parisi Collections
- Quadro
- Milli
- Vetto
- Ellisse

### Other Notable Collections
- Edwardian (heritage style)
- Contemporary
- Classic
- Modern
- Minimalist
- Industrial
- Hamptons
- Scandinavian

---

## Validation Rules

### Primary Category Mapping

When extracting from supplier pages, map product types to primary categories:

```
Basin Mixer → Basin Tapware
Kitchen Mixer → Kitchen Tapware
Bath Spout → Bath Tapware
Shower Mixer → Shower Tapware

Countertop Basin → Basins
Wall Basin → Basins

Close Coupled Toilet → Toilets
Wall Hung Toilet → Toilets

Kitchen Sink → Kitchen Sinks
Bar Sink → Kitchen Sinks

Freestanding Bath → Baths

Heated Towel Rail → Bathroom Accessories
Toilet Roll Holder → Bathroom Accessories
```

### Category Type Standardization

Standardize variations to consistent values:

```
"wall hung" / "wall-hung" / "wall mounted" → "Wall Hung"
"above counter" / "countertop" / "vessel" → "Countertop"
"undermount" / "under mount" / "under-mount" → "Undermount"
"floor mounted" / "floor standing" → "Floor Mounted"
"in-wall" / "concealed" / "in wall" → "In-Wall"
```

### Collection Name Extraction

Look for collection names in:
1. Product title (e.g., "Caroma Urbane Basin")
2. Product URL (e.g., `/products/urbane-basin/`)
3. Breadcrumb navigation
4. Product description headers
5. Range/collection fields in specifications

Clean collection names:
- Remove supplier prefix (e.g., "Caroma Urbane" → "Urbane")
- Title case (e.g., "URBANE" → "Urbane")
- Remove "Collection", "Range", "Series" suffixes

---

## Examples

### Example 1: Basin Mixer
```json
{
  "super_category": "Tapware",
  "primary_category": "Basin Tapware",
  "product_category_type": "Bench Mount",
  "collection_name": "Urbane",
  "overall_width_mm": 180,
  "material": "brass",
  "colour_finish": "Chrome"
}
```
**Navigation:** Home > Tapware > Basin Tapware > Bench Mount

### Example 2: Kitchen Sink
```json
{
  "super_category": "Sinks",
  "primary_category": "Kitchen Sinks",
  "product_category_type": "Undermount",
  "collection_name": "Alfresco",
  "overall_width_mm": 540,
  "material": "stainless steel",
  "colour_finish": "316 Marine Grade"
}
```
**Navigation:** Home > Sinks > Kitchen Sinks > Undermount

### Example 3: Wall Hung Toilet
```json
{
  "super_category": "Toilets",
  "primary_category": "Toilets",
  "product_category_type": "Wall Hung",
  "collection_name": "Luna",
  "overall_width_mm": 360,
  "material": "ceramic",
  "colour_finish": "White"
}
```
**Navigation:** Home > Toilets > Wall Hung

### Example 4: Freestanding Bath
```json
{
  "super_category": "Baths",
  "primary_category": "Baths",
  "product_category_type": "Freestanding",
  "collection_name": "Byron",
  "overall_width_mm": 1700,
  "material": "acrylic",
  "colour_finish": "Gloss White"
}
```
**Navigation:** Home > Baths > Freestanding

### Example 5: Heated Towel Rail
```json
{
  "super_category": "Accessories",
  "primary_category": "Bathroom Accessories",
  "product_category_type": "Heated Ladder Rail",
  "collection_name": null,
  "overall_width_mm": 600,
  "material": "stainless steel",
  "colour_finish": "Polished"
}
```
**Navigation:** Home > Accessories > Bathroom Accessories > Heated Ladder Rail

---

## Notes for LLM Extraction

When extracting categories:

1. **Be specific but consolidated** - "Basin Mixer" should map to "Basin Tapware", not create a new category
2. **Use product context** - If unclear, check product title and URL for hints
3. **Prioritize primary category** - Every product must have a primary_category
4. **Optional subcategory** - product_category_type is optional but recommended
5. **Collection is optional** - Only extract if clearly stated, don't infer
6. **Handle combos correctly** - "Sink Mixer with Pull-out Spray" → primary: "Kitchen Tapware", type: "Pull-Out Spray"

## Confidence Guidelines

- **High confidence (≥0.7)**: Category clearly stated, matches standard list exactly
- **Medium confidence (0.3-0.7)**: Category inferred from context, slight variation from standard
- **Low confidence (<0.3)**: Category ambiguous or completely missing
