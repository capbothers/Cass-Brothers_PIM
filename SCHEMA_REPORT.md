# Schema Report (from config/collections.py)

## SinksCollection

- ai_extraction_fields: 28
- quality_fields: 30
- column_mapping keys: 62

**ai_extraction_fields missing in column_mapping:** None

**quality_fields missing in column_mapping:** None

## TapsCollection

- ai_extraction_fields: 13
- quality_fields: 23
- column_mapping keys: 48

**ai_extraction_fields missing in column_mapping:** None

**quality_fields missing in column_mapping:** None

## ToiletsCollection

- ai_extraction_fields: 18
- quality_fields: 18
- column_mapping keys: 44

**ai_extraction_fields missing in column_mapping:**
- ,
- ,
            # Toilet specifications (using sheet column names)
- ,
            # WELS fields (EXCLUDED - auto-populated from WELS reference sheet via lookup, not AI extraction)
            #
- ,              # Pan depth in mm (individual)
- ,              # Pan width in mm (individual)
- ,              # pan shape (S-trap, P-trap, etc.)
- ,             # Pan height in mm (individual)
- ,             # model/product name
- ,             # water inlet position
- ,         # flush type (Single, Dual)
- ,       # material (Ceramic, Vitreous China)
- ,       # seat type (Soft Close, Standard, etc.)
- ,      # rim design (Rimless, Standard, etc.)
            # Dimensions
- ,      # toilet type (Close Coupled, Back to Wall, etc.)
- ,  # Pan height separately (legacy)
            # Warranty
- ,  # Width x Depth x Height in mm (combined)
- t overwrite existing data)

**quality_fields missing in column_mapping:** None

## SmartToiletsCollection

- ai_extraction_fields: 32
- quality_fields: 22
- column_mapping keys: 64

**ai_extraction_fields missing in column_mapping:**
- ,

            # === SMART TOILET SPECIFIC FIELDS ===
            # Power & Electrical
- ,
            # Standard toilet specifications
- ,                # Voltage (e.g., 220-240V)
- ,              # Pan depth in mm
- ,              # Pan width in mm
            # Warranty
- ,              # pan shape (S-trap, P-trap, etc.)
- ,             # Pan height in mm
- ,             # model/product name
- ,             # water inlet position
- ,           # Frequency (e.g., 50/60Hz)
- ,         # Auto flush

            # Temperature Controls
- ,         # Bidet wash function
- ,         # Deodorizer function
- ,         # e.g., "Front, Rear, Oscillating"
- ,         # flush type (Single, Dual)
- ,        # Heated seat
- ,        # Night light
- ,       # material (Ceramic, Vitreous China)
- ,       # seat type (Soft Close, Standard, etc.)
- ,      # rim design (Rimless, Standard, etc.)
            # Dimensions
- ,      # toilet type (Close Coupled, Back to Wall, Wall Hung)
- ,     # Power consumption (e.g., 841W)
- ,     # Warm air dryer
- ,    # Cord length in meters
- ,   # Adjustable seat temperature

            # Hygiene Features
- ,   # UV sterilization

            # Controls
- ,   # e.g., "Isolated 10amp circuit"

            # Smart Features (Yes/No)
- ,  # Adjustable water temperature
- ,  # Width x Depth x Height in mm (combined)
- , # Auto open/close lid
- , # Self-cleaning nozzle
- t overwrite existing data)

**quality_fields missing in column_mapping:** None

## ShowersCollection

- ai_extraction_fields: 47
- quality_fields: 20
- column_mapping keys: 62

**ai_extraction_fields missing in column_mapping:**
- ,
- ,

            # === SHOWER TYPE CLASSIFICATION ===
- ,                 # Flow rate in litres per minute (e.g., 9, 7.5)
- ,                 # Wall, Ceiling, Gooseneck
- ,                # Angle of arm

            # === SHOWER MIXER FIELDS ===
- ,               # Ceramic disc, Quarter turn
- ,               # Exposed, Concealed, Thermostatic
- ,               # Maximum temperature °C

            # === SHOWER RAIL FIELDS ===
- ,               # Minimum temperature °C
- ,               # Number of hoses (1, 2)
- ,               # Round, Square

            # === SHOWER ARM FIELDS ===
- ,              # Lever, Cross, Knob
- ,              # Rail Set, Shower System, Hand Shower, Shower Arm, Shower Rose, Mixer

            # === COMMON SHOWER SPECIFICATIONS ===
            # WELS Rating
- ,              # Silver, Chrome, etc.

            # === OVERHEAD / SHOWER ROSE FIELDS ===
- ,              # Star rating (3 Star, 4 Star, etc.)
- ,              # e.g., "Rain, Massage, Mist" or "PowderRain, IntenseRain, MonoRain"
- ,            # 2-way, 3-way, None
- ,            # Arm length (e.g., 400mm)
- ,            # Flow rate L/min
- ,            # Yes/No - includes soap dish
- ,           # Hose length (e.g., 1500mm)
- ,           # Optional soap dish product code
- ,           # Rail length (e.g., 600mm, 700mm)
- ,           # Round, Square
- ,          # Number of spray functions (1, 3, etc.)
- ,          # Round, Square, Oval
- ,          # Yes/No - is rail height adjustable
- ,         # Connection size (e.g., G 1/2, 15mm)
- ,         # Maximum pressure in kPa
- ,         # Minimum pressure in kPa
- ,         # Rail diameter (e.g., 25mm)
- ,         # Rose diameter (alias for overhead)
- ,         # Yes/No - includes wall bracket
- ,        # Outlet connection

            # === ADDITIONAL FEATURES ===
- ,        # WELS registration number

            # Flow & Pressure
- ,        # Wall mount, Ceiling mount
- ,        # Yes/No - Select button for spray change

            # === HOSE FIELDS ===
- ,       # Yes/No - suitable for mains pressure
- ,     # Overhead rose diameter (e.g., 230mm, 250mm)
- ,    # Handpiece/shower head diameter (e.g., 100mm, 105mm, 130mm)
- , # Adjustable range (e.g., 650-850)

            # === HAND SHOWER / HANDPIECE FIELDS ===
- t overwrite existing data)

**quality_fields missing in column_mapping:** None

## BathsCollection

- ai_extraction_fields: 11
- quality_fields: 17
- column_mapping keys: 45

**ai_extraction_fields missing in column_mapping:**
- ,
            # Bath specifications
- ,
            # Dimensions
- ,              # Bath length
- ,           # Overflow yes/no
- ,       # Acrylic, Cast Iron, Composite, etc.
- ,       # Bath depth/height
- ,       # Bath width
- ,      # Freestanding, Drop-in, Alcove, Corner
- ,      # Grade/quality of material
- , # Waste outlet size
            # Additional specs
- t overwrite existing data)

**quality_fields missing in column_mapping:** None

## BasinsCollection

- ai_extraction_fields: 13
- quality_fields: 20
- column_mapping keys: 45

**ai_extraction_fields missing in column_mapping:** None

**quality_fields missing in column_mapping:** None

## FilterTapsCollection

- ai_extraction_fields: 30
- quality_fields: 21
- column_mapping keys: 61

**ai_extraction_fields missing in column_mapping:**
- ,
- ,
            # Filter tap specifications
- ,                   # Hot water capability
- ,                   # Tank capacity
- ,                  # Cold water capability
            # Materials and construction
- ,                  # Tap material
- ,                  # Warranty period
            # Dimensions
- ,                 # Commercial use yes/no
- ,                # Flow rate L/min
- ,                # Residential use yes/no
            # Water features
- ,               # Ambient water capability
- ,               # Boiling water capability
- ,               # Chilled water capability
- ,              # Chrome, Matte Black, etc.
- ,              # Lever, Knob, etc.
- ,              # Undermount, Deck-mounted, etc.
- ,              # WELS rating
- ,             # Number of handles
- ,             # Sparkling water capability
- ,             # Swivel capability yes/no
            # Technical specs
- ,           # Cartridge type
- ,           # Spout reach in mm
- ,          # Spout height in mm
- ,         # Maximum pressure
            # Certifications
- ,         # Minimum pressure
- ,     # Lead-free compliant
            # Location
- ,  # WaterMark certified
- , # Dimensions of underbench unit
- , # WELS registration
- t overwrite existing data)

**quality_fields missing in column_mapping:** None

## HotWaterCollection

- ai_extraction_fields: 5
- quality_fields: 11
- column_mapping keys: 37

**ai_extraction_fields missing in column_mapping:** None

**quality_fields missing in column_mapping:** None

## TestMinimalCollection

- ai_extraction_fields: 6
- quality_fields: 3
- column_mapping keys: 21

**ai_extraction_fields missing in column_mapping:** None

**quality_fields missing in column_mapping:** None

## UnassignedCollection

- ai_extraction_fields: 0
- quality_fields: 5
- column_mapping keys: 15

**ai_extraction_fields missing in column_mapping:** None

**quality_fields missing in column_mapping:** None
