# Tapware Review — Changelog & Rules

**File:** tapware_review.csv
**Last Updated:** 2026-02-13
**Total Products:** 4,253

---

## Recent Changes

### 5. Column H — Shower Mixers & Bath Mixers → Wall Mixers

| Change | Rows | Detail |
|--------|------|--------|
| Shower Mixers → Wall Mixers | 94 | Wall Mounted shower mixers consolidated into Wall Mixers |
| Bath Mixers → Wall Mixers | 264 | Wall Mounted bath mixers consolidated into Wall Mixers |
| Basin Mixers → Wall Mixers | 5 | Hansgrohe Logis Wall Basin Mixer (71220003 + 13622180), Mixx Saffron Dual Wall Plate Mixer x4 (11SL955BLEF/CLE/GLEF/MLE) |

*7 hob-mounted products intentionally excluded — 2 Shower Mixers (Parisi Ellisse/Quadro Hob Mixer & Hand Shower) and 5 Bath Mixers (Fienza Kaya/Sansa Hob Mixer Set, Sussex Calibre/Circa/Duet). Diverters (290) confirmed unchanged.*

### 1. Title Cleanup
- Removed **79** en dash characters (`–`, U+2013) from titles, replaced with standard hyphens (`-`)

### 2. Column H (product_category_type) Updates

| Change | Rows | Detail |
|--------|------|--------|
| Basin Mixer → Basin Mixers | 593 | Pluralised |
| Wall Basin Mixer → Wall Basin Mixers | 372 | Pluralised |
| Bath Mixer → Bath Mixers | 269 | Pluralised |
| Pull-Out Mixer → Pull-Out Mixers | 531 | Pluralised |
| Shower Mixer → Shower Mixers | 96 | Pluralised |
| Hob Mixer → Hob Mixers | 24 | Pluralised |
| Diverter → Diverters | 1 | Pluralised |
| Basin Tap Sets → Basin Tap Sets, Bath Tap Sets | 17 | Where title includes "bath" and "basin" |
| Basin Tap Sets → Bath Tap Sets | 4 | Where title includes "bath" only (no "basin") |
| Wall Basin Mixer → Wall Basin Mixers, Wall Bath Mixers | 249 | Where title includes "bath" |
| Shower Mixer in title → Wall Mixers | 207 | Title-based reclassification |
| Diverter in title → Diverters | 289 | Title-based reclassification |
| Sensor in title → Spouts & Bath Fillers, Sensor Tapware | 16 | Title-based reclassification |
| 4x Greens Luxe Pull Down → Pull-Out Mixers | 4 | Pull-out/pull-down subcategory rule |
| 96385C56AF → Pull-Out Mixers, Sensor Tapware | 1 | Pull-down + Sensor — primary type with Sensor Tapware as secondary filter |
| 5B2-S → Basin Mixers, Sensor Tapware | 1 | Sensor as secondary filter appended to primary type |
| 527494, 5K3-S → Kitchen Mixers, Sensor Tapware | 2 | Sensor as secondary filter appended to primary type |
| QCU.01-3H → Basin Tap Sets, Bath Tap Sets | 1 | Manual correction |
| NS135 CHR → Sink Tap Sets | 1 | Manual correction |

### 3. Column N (installation_type) Updates

| Change | Rows | Detail |
|--------|------|--------|
| In-Wall → Wall Mounted | 207 | Standardised terminology |
| Hob Mounting → Hob Mounted | 3 | Standardised terminology |
| Empty → Hob Mounted | 9 | Where title includes "Hob" |
| Empty → Wall Mounted | 9 | Where title includes "Wall" |
| Wall Top Assemblies: Hob Mounted → Wall Mounted | 30 | "Wall Top Assembly" products are wall mounted |
| Floor mounted products: Hob/Wall Mounted → Floor Mounted | 15 | Title includes "Floormount", "Floor Mounted", or "Floorstanding" |
| Wall products incorrectly Hob Mounted → Wall Mounted | 4 | Kohler Avid Wall Mount, Phoenix Ivy Wall Sink Set/Outlet, Phoenix Vivid Wall Sink Set |
| Shower Mixers: Hob Mounted → Wall Mounted | 32 | Shower mixers are wall-mounted products by nature |
| Bath/Shower Mixers: Hob Mounted → Wall Mounted | 6 | Caroma Luna/Pin Lever/Vivas Bath-Shower Mixers, Gareth Ashton Park Avenue |
| Sussex Bath Mixer Systems: Hob Mounted → Wall Mounted | 5 | Sussex Circa/Duet/Suba Bath Mixer Systems with Handshower |
| 99603C → Floor Mounted | 1 | Caroma Contura Freestanding Bath Mixer |
| 96372B6AF → Wall Mounted | 1 | Caroma Liano II Basin/Bath Outlet — wall outlet |
| 53360 → Wall Mounted | 1 | Elson Esperance Bath Set |
| 3BTM-BB → Floor Mounted | 1 | Gareth Ashton Lucia Bath Filler |
| 8 Basin Mixers: Wall Mounted → Hob Mounted | 8 | Incorrect installation_type — Brodware (1.6716.08.2.01, 1.8004.00.4.01), Fienza (228103DCO, 233110DB), Gareth Ashton (3B2), Greens (LF24203550GM, LF23703550BB, 21302558) |

### 4. Column J (colour_finish) Corrections

403 rows with incorrect colour/finish values corrected based on title analysis:

| SKU | Old Value | New Value |
|-----|-----------|-----------|
| GPR1000 | Chrome | Stainless Steel (reverted back to Chrome on 2026-02-12 — title says Stainless Steel but product description confirms Chrome; one-off exception) |
| EE2.01-1H.41 | Brushed Brass | Brushed Nickel |
| LU118DM-S-BN | Brass | Brushed Nickel |
| LU121BM-S-CH | Brushed Nickel | Chrome |
| VE104506FMB | Gunmetal | Matte Black |
| 849053BBZ6AF | Brass | Brushed Bronze |
| 229101GM | Chrome | Gunmetal |
| 151-7815-12-1 | Chrome | Brushed Gold |
| VS2812-31-1 | Matte Black | Brushed Carbon |
| EE2.01-2RF160.41 | Brushed Brass | Brushed Nickel |
| EE2.01-2E160.41 | Brushed Brass | Brushed Nickel |
| EE2.01-2RF220.41 | Brushed Brass | Brushed Nickel |
| EE2.01-2E220.41 | Brushed Brass | Brushed Nickel |
| 139-2805-31-1 | Brushed Nickel | Brushed Carbon |
| 1104590B + 8733500 | Gold | Gunmetal |
| 24D018GM | Chrome | Gunmetal |
| NR221903gMB | Bronze | Matte Black |
| 60201#299 | Brushed Nickel | Matte Black |
| NR692109a03CH | Matte Black | Chrome |
| PA102516FMB | Gunmetal | Matte Black |
| T465685 | Brushed Nickel | Brushed Gold |
| 31 Phoenix SKUs (suffix -31/-31-1) | Gunmetal | Brushed Carbon |
| 4 Phoenix SKUs (suffix -31/-31-1) | (empty) | Brushed Carbon |

*Phoenix Brushed Carbon batch (35 rows): All Phoenix Tapware products with "Brushed Carbon" in title across Gloss MKII, Mekko, Nuage, Teel, Vask, and Vivid Slimline ranges. The `-31` suffix is Phoenix's finish code for Brushed Carbon. 3 additional rows already had the correct value from earlier corrections.*

*Nero York Porcelain Lever batch (17 rows): Column J had lever colour (White) or simplified colour (Brass) instead of body colour. Corrected based on title colour after the dash (e.g. "White Porcelain Lever - Matte Black" → J = Matte Black). 19 additional Nero York Porcelain Lever rows already had the correct Chrome/Matte Black value.*

| 8 Nero York SKUs (suffix 01MB) | White | Matte Black |
| 2 Nero York SKUs (suffix 01AB) | White | Aged Brass |
| 7 Nero York SKUs (suffix 01AB) | Brass | Aged Brass |
| 174 SKUs with "Brushed Gold" in title | Gold | Brushed Gold |
| 20 Oliveri SKUs with "Classic Gold" in title | Gold | Classic Gold |
| 23 SKUs with "Brushed Copper" in title | Copper | Brushed Copper |

*Colour specificity batch (217 rows): "Gold" and "Copper" were too generic — updated to match the specific finish in the title. Brushed Gold (Nero, Phoenix, Gessi, Suprema Xpressfit, Villeroy & Boch, Zucchetti), Classic Gold (Oliveri), Brushed Copper (Fienza, Gessi, Greens).*

*PVD batch (29 rows): Products with PVD coating in title now use "PVD [Colour]" prefix format to retain the PVD reference. Updated across Arcisan, Meir, Fienza, Linkware, and Blanco.*

| 3 Arcisan SKUs (Brushed Brass PVD) | Brass | PVD Brushed Brass |
| 3 Arcisan SKUs (Brushed Rose Gold PVD) | Gold | PVD Brushed Rose Gold |
| 1 Arcisan SKU (Rose Gold PVD) | Gold | PVD Rose Gold |
| 2 Arcisan SKUs (Brushed Gun Metal PVD) | Gunmetal | PVD Brushed Gunmetal |
| 4 SKUs (Brushed Nickel PVD / PVD Brushed Nickel) | Brushed Nickel | PVD Brushed Nickel |
| 3 Fienza SKUs (PVD Brushed Copper) | Copper | PVD Brushed Copper |
| 2 Meir SKUs (PVD Gun Metal) | Gunmetal | PVD Gunmetal |
| 3 Linkware SKUs (PVD Gold) | Gold | PVD Gold |
| 2 Fienza SKUs (PVD Urban Brass) | Brass | PVD Urban Brass |
| 1 Meir SKU (PVD Bronze) | Bronze | PVD Bronze |
| 1 Meir SKU (PVD Lustre Bronze) | Bronze | PVD Lustre Bronze |
| 1 Meir SKU (PVD Tiger Bronze) | Brass | PVD Tiger Bronze |
| 2 Blanco SKUs (PVD Steel) | (empty) | PVD Steel |
| 1 Blanco SKU (PVD Steel) | Stainless Steel | PVD Steel |
| 6B1-GM | PVD Gunmetal | Gunmetal |
| SP8041 | PVD Chrome | Chrome |

*Note: 229103GM, D231101GM, D229101GM-2 (Fienza) retain PVD Gunmetal as one-off exceptions — title says "Gun Metal" but PVD finish is confirmed.*

*Vendor-specific finishes batch (49 rows): Proprietary and specific finish names restored from generic colour values.*

| 35 Parisi SKUs (Fucile) | Gunmetal | Fucile |
| 6 Parisi SKUs (Fucile) | Matte Black | Fucile |
| 2 Parisi SKUs (Carbon Satin) | Matte Black | Carbon Satin |
| 1 Parisi SKU (Brushed Pewter) | Chrome | Brushed Pewter |
| 5 Gareth Ashton 304 SKUs (suffix -BR) | Stainless Steel | Brushed Stainless Steel |

*Note: Gareth Ashton titles use "Brushed Steel" and "Brushed Stainless" interchangeably — standardised to "Brushed Stainless Steel" as confirmed by manufacturer.*

*Two-tone / dual-finish batch (29 rows): Standardised using primary body colour rule. Hansgrohe "Brushed Black Chrome" is a single finish (not two-tone).*

| 5 Hansgrohe SKUs (Brushed Black Chrome) | Chrome/Matte Black | Brushed Black Chrome |
| 5 Newform SKUs (Chrome/Black) | Matte Black | Chrome |
| 4 Newform SKUs (Chrome/White) | White | Chrome |
| 6 Parisi O'Rama SKUs (Chrome with Matt Black Handle) | Chrome, Matte Black / Matte Black | Chrome |
| 3 Parisi SKUs (Chrome with Black/White accent) | Matte Black / (empty) | Chrome |
| 6 Villeroy & Boch Avia 2.0 SKUs (Ceramic/Brushed Gold) | Gold | Brushed Gold |
| 1.8541.00.4.01 | Chrome | White |
| 228109MW | Matte White, Matte Black | Matte White |
| 6495.045AF | Matte Black | Chrome |
| 10.151.423.000 | Matte Black | Chrome |

---

## Current Rules

### Column H (product_category_type)

All values should be **plural**. The following rules are applied based on title (column C) keywords:

| Title Keyword | Column H Value |
|---------------|----------------|
| "Pull-Out" or "Pull-Down" | Pull-Out Mixers (intentional subcategory for kitchen/laundry) |
| "Sensor" | Sensor Tapware (secondary filter — append to primary type, e.g. Pull-Out Mixers, Sensor Tapware) |
| "Diverter" | Diverters |
| "Shower Mixer" | Wall Mixers |
| Title has "basin" AND "bath" | Append both categories (e.g. Basin Tap Sets, Bath Tap Sets) |
| Title has "bath" only (no "basin") | Use bath-only category (e.g. Bath Tap Sets) |
| Title has "Wall" + "Basin/Bath" | Wall Basin Mixers, Wall Bath Mixers |

#### Valid Column H Values

| Value | Current Count |
|-------|---------------|
| Basin Mixers | 775 |
| Wall Mixers | 543 |
| Pull-Out Mixers | 535 |
| Kitchen Mixers | 521 |
| Spouts & Bath Fillers | 428 |
| Wall Basin Mixers | 372 |
| Basin Tap Sets | 292 |
| Diverters | 290 |
| Wall Basin Mixers, Wall Bath Mixers | 249 |
| Bath Tap Sets | 138 |
| Hob Mixers | 24 |
| Basin Tap Sets, Bath Tap Sets | 18 |
| Laundry Tap | 15 |
| Pot Filler | 13 |
| Spouts & Bath Fillers, Sensor Tapware | 12 |
| Washing Machine Stop | 7 |
| Laundry Tap Set | 6 |
| Bath Mixers | 5 |
| Shower Mixers | 2 |
| Kitchen Mixers, Sensor Tapware | 2 |
| Basin Mixers, Sensor Tapware | 1 |
| Pull-Out Mixers, Sensor Tapware | 1 |
| Sink Tap Sets | 1 |
| Isolation Valve | 1 |
| Pillar Tap | 1 |
| Wall Stop | 1 |

### Column N (installation_type)

| Rule | Column N Value |
|------|----------------|
| Title includes "Hob" | Hob Mounted |
| Title includes "Wall" or "Wall Top Assembly" | Wall Mounted |
| Title includes "Floormount", "Floor Mounted", or "Floorstanding" | Floor Mounted |
| Shower Mixers (wall-mounted by nature) | Wall Mounted |
| Bath/Shower Mixers (wall-mounted by nature) | Wall Mounted |
| All "In-Wall" values standardised to | Wall Mounted |
| All "Hob Mounting" values standardised to | Hob Mounted |

Note: One-off hob-mounted shower mixers may exist but are rare. Floor Mounted usually applies to bath mixers/fillers.

#### Valid Column N Values

| Value | Current Count | Description |
|-------|---------------|-------------|
| Hob Mounted | 2,112 | Deck/hob/benchtop mounted |
| Wall Mounted | 2,062 | Wall mounted (includes former "In-Wall" and "Wall Top Assembly") |
| Floor Mounted | 59 | Floor standing (freestanding bath mixers/fillers) |
| (empty) | 20 | Laundry taps, washing machine stops, cistern taps — left blank intentionally |

### Column J (colour_finish)

- Colour/finish should match the product colour stated in the title (column C), **not** the colour of handles, levers, or decorative elements (e.g. "White Porcelain Lever" does not mean J = "White")
- For two-tone products (e.g. "Chrome/Black", "Chrome & Black"), use the primary body colour
- Where title and description conflict (e.g. GPR1000), defer to the product description as the source of truth
- Phoenix `-31` / `-31-1` suffix SKUs = Brushed Carbon (not Gunmetal)
- PVD products: retain "PVD" prefix in colour_finish — format as "PVD [Colour]" (e.g. PVD Brushed Nickel, PVD Gold)

---

## Known Outstanding Items

- ~~**Brushed Carbon vs Gunmetal** (~25 rows): Phoenix products with "Brushed Carbon" in title currently have "Gunmetal" in J — may need review~~ **RESOLVED** (35 rows updated on 2026-02-13)
- ~~**Nero York lever colours** (~8 rows): "White Porcelain Lever" / "Black Porcelain Lever" in title — J has lever colour instead of body colour~~ **RESOLVED** (17 rows updated on 2026-02-13)
- ~~**Two-tone products** (~15 rows): Products with dual colours (e.g. Chrome/Black) — J only captures one colour~~ **RESOLVED** (29 rows updated on 2026-02-13)
- **Wall Mixers — sub-classification review** (~242 rows): The 543 Wall Mixers contain products that need further review and likely reclassification:
  - **17 non-mixer products**: 11 wall shower heads (Greens Glide Syntra x5, Greens Lavish x6), 3 shower heads/risers (Armando Vicario, Gareth Ashton x2), 1 shower riser & head (Parisi EE.08-1W), 1 combination shower (Argent SC11230B), 1 wall top assembly (Fienza 336104BK)
  - **60 "Set" products**: Mixer + spout/body bundles (Fienza x18, Oliveri x16, Phoenix x9, Argent x6, Gareth Ashton x5, Brodware x4, Sussex x2)
  - **50 "Spout" products**: Mixer + integrated spout combos (Parisi x31, Nero x9, Sussex x3, others)
  - **25 "System" products**: Multi-piece systems with outlets/handshowers (Sussex x21, Nero x4)
  - **27 Nero divertor products**: Shower mixer dividers — may need own category or merge with Diverters
  - **78 Trim Kit Only products**: Cosmetic trim without in-wall body (Fienza x46, Phoenix x28, V&B x3, Hansa x1)
  - *Note: some products appear in multiple groups above (e.g. a "system" that also has "spout" and "handshower")*
- **Duplicate SKUs** (8 pairs): Need investigation and resolution
- **Empty installation_type** (20 rows): Laundry taps, washing machine stops, cistern taps — left blank intentionally
- **Empty colour_finish** (220 rows): Products missing colour data
