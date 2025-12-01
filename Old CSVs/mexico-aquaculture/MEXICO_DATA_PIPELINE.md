# Mexico DENUE Dataset Integration Pipeline

## Overview
This pipeline processes Mexico's DENUE (Directorio Estadístico Nacional de Unidades Económicas) dataset to extract animal-related facilities for integration into the Until Every Cage is Empty project.

## Source Data
- **File**: `denue_inegi_11_.csv`
- **Records**: 25,465 total records
- **Encoding**: Latin-1
- **Source**: INEGI (Instituto Nacional de Estadística y Geografía)
- **Classification**: SCIAN 2018 (Sistema de Clasificación Industrial para América del Norte)

## Dataset Scope
The dataset provided covers **all 32 Mexican states and 1,081 municipalities**, but contains only **15 SCIAN activity codes** related to aquaculture, fishing, and agricultural services.

## Processing Pipeline

### Step 1: Analysis (`00_explore_dataset.py` and `01_analyze_scian_codes.py`)
- Identifies all unique SCIAN codes in the dataset
- Maps codes to facility types
- Counts records by activity type

**Key Findings:**
- Total animal-related facilities: 23,996
- Aquaculture facilities: 3,112
- Fishing operations: 20,726
- Animal farming services: 158

### Step 2: Filtering (`03_create_filtered_csv.py`)
- Extracts records with relevant SCIAN codes
- Output: `mexico_filtered.csv` (23,996 records)

**SCIAN Codes Included:**
- **112513-112519**: Aquaculture (fish farming, shrimp farms, etc.)
- **114111-114119**: Commercial fishing operations
- **115210**: Services related to animal raising and exploitation

### Step 3: Cleaning (`04_clean_data.py`)
- Standardizes address formatting
- Validates and cleans coordinates
- Handles phone numbers
- Processes missing/null values
- Output: `mexico_cleaned.csv` (23,996 records)

**Cleaning Operations:**
- Consolidates multi-line address fields (street type + name + number)
- Validates latitude/longitude ranges
- Extracts and standardizes phone numbers
- Fills missing city names from municipality field
- Handles encoding issues

### Step 4: Schema Conversion (`05_convert_to_project_schema.py`)
- Maps cleaned data to project Location schema
- Fills empty animal processing/slaughter fields (N/A for this dataset)
- Creates final output ready for deployment
- Output: `locations.csv` (23,996 records)

**Output Structure:**
- All records have coordinates (latitude/longitude)
- Facility type: "Aquaculture Farm", "Fishing Operation", or "Farm / Breeder"
- US-specific animal slaughter/processing fields left empty (not applicable to Mexico data)
- Core fields: name, address, city, state, phone, coordinates, facility type

## Important Notes

### Data Limitations
1. **No slaughterhouses/processing plants**: The DENUE dataset provided contains only aquaculture, fishing, and agricultural services. Industrial meat processing facilities are not included in this particular data extract.

2. **No research facilities/labs**: No animal testing laboratories are present in the dataset.

3. **Agricultural services only**: The dataset focuses on primary production (farming, fishing) rather than secondary industries (processing, research).

### Future Enhancements
To create a more comprehensive Mexico database, additional data sources would be needed:
- COFEPRIS (Comisión Federal para la Protección contra Riesgo Sanitario) for research facilities
- SENASICA (Servicio Nacional de Sanidad, Inocuidad y Calidad Agroalimentaria) for slaughterhouses and processing plants
- SEMARNAT (Secretaría de Medio Ambiente y Recursos Naturales) for wildlife breeding facilities

### Field Mappings
| DENUE Field | Project Field | Notes |
|-------------|---------------|-------|
| `id` | `establishment_id` | Unique identifier |
| `nom_estab` | `establishment_name` | Business name |
| `latitud`/`longitud` | `latitude`/`longitude` | Coordinates |
| `entidad` | `state` | Mexican state |
| `municipio` | `county`/`city` | Municipality |
| `codigo_act` | Mapped to type | SCIAN code classification |
| `nombre_act` | `activities` | Activity description |
| `raz_social` | `dbas` | Legal business name |
| `tipo_vial`, `nom_vial`, etc. | `street` | Consolidated address |
| `telefono` | `phone` | Contact number |
| `fecha_alta` | `grant_date` | Date registered |

## Usage

### Running the Pipeline
```bash
cd dirty-datasets/mexico

# Step 1: Analyze
python3 00_explore_dataset.py
python3 01_analyze_scian_codes.py

# Step 2: Filter
python3 02_filter_animal_facilities.py
python3 03_create_filtered_csv.py

# Step 3: Clean
python3 04_clean_data.py

# Step 4: Convert
python3 05_convert_to_project_schema.py
```

### Output Files
- `mexico_filtered.csv`: Raw filtered data (23,996 records)
- `mexico_cleaned.csv`: Standardized cleaned data
- `locations.csv`: Final project-ready data

## Integration Steps

1. Create directory: `static_data/mx/`
2. Copy `locations.csv` to `static_data/mx/locations.csv`
3. Update backend code to include Mexico in country listings
4. Update frontend to add Mexican states to state selector
5. Test country filtering with `?country_code=mx` API parameter

## Statistics

### By State (Top 10)
The dataset includes all 32 Mexican states. Facilities are distributed across all municipalities.

### By Facility Type
- **Fishing Operations**: 86.4% (20,726 records)
- **Aquaculture**: 13.0% (3,112 records)  
- **Animal Farming Services**: 0.7% (158 records)

### Data Quality
- Complete coordinates: 100%
- Valid phone numbers: ~45%
- Email addresses: ~15%
- Websites: ~3%

## Files Generated

```
dirty-datasets/mexico/
├── denue_inegi_11_.csv (original, 25,465 records)
├── denue_diccionario_de_datos.csv (data dictionary)
├── mexico_filtered.csv (23,996 relevant facilities)
├── mexico_cleaned.csv (cleaned, standardized)
├── locations.csv (project-ready schema, 23,996 records)
├── 00_explore_dataset.py
├── 01_analyze_scian_codes.py
├── 02_filter_animal_facilities.py
├── 03_create_filtered_csv.py
├── 04_clean_data.py
├── 05_convert_to_project_schema.py
└── MEXICO_DATA_PIPELINE.md (this file)
```

## Next Steps

1. **Expand data sources**: Integrate additional Mexican government datasets for processing facilities and research labs
2. **Improve facility classification**: Use additional metadata or machine learning to better classify facilities
3. **Add facility details**: Scrape websites or contact facilities for more information (animals, capacity, etc.)
4. **Create Mexico-specific UI**: Add special handling for Mexican municipalities and states
5. **Add Spanish language support**: Translate UI elements for Mexican users
