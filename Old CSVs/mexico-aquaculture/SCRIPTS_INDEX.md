# Mexico Data Processing Scripts Index

All scripts process the DENUE dataset progressively. Run them in order.

## Phase 0: Exploration (Optional)

### `00_explore_dataset.py`
- **Purpose**: Get initial overview of DENUE dataset
- **Input**: `denue_inegi_11_.csv`
- **Output**: Console output (no file)
- **Shows**: Total records, all states, unique municipalities, SCIAN codes
- **Run time**: ~0.5s
- **Optional**: Good for understanding data before processing

### `01_analyze_scian_codes.py`
- **Purpose**: Analyze SCIAN activity codes
- **Input**: `denue_inegi_11_.csv`
- **Output**: Console output (no file)
- **Shows**: All SCIAN codes found and their descriptions
- **Run time**: ~0.5s
- **Optional**: Good for verifying what facility types are available

### `02_filter_animal_facilities.py`
- **Purpose**: Show filtering logic and sample facilities
- **Input**: `denue_inegi_11_.csv`
- **Output**: Console output (no file)
- **Shows**: Sample facilities by type, filtering breakdown
- **Run time**: ~0.5s
- **Optional**: Verify which facilities will be included

---

## Phase 1: Filtering (Required)

### `03_create_filtered_csv.py`
- **Purpose**: Extract only animal-related facilities
- **Input**: `denue_inegi_11_.csv` (25,465 records)
- **Output**: `mexico_filtered.csv` (23,996 records)
- **Filters**: SCIAN codes 112513-112519, 114111-114119, 115210
- **Run time**: ~0.9s
- **Produces**: 9.2 MB file with filtered facilities

---

## Phase 2: Cleaning (Required)

### `04_clean_data.py`
- **Purpose**: Clean and standardize data
- **Input**: `mexico_filtered.csv` (23,996 records)
- **Output**: `mexico_cleaned.csv` (23,996 records)
- **Operations**:
  - Consolidates multi-line address fields
  - Validates coordinates
  - Cleans phone numbers
  - Handles missing values
  - Manages encoding issues
- **Run time**: ~1.0s
- **Produces**: 10.1 MB file with cleaned data

---

## Phase 3: Schema Conversion (Required)

### `05_convert_to_project_schema.py`
- **Purpose**: Convert to project Location schema
- **Input**: `mexico_cleaned.csv` (23,996 records)
- **Output**: `locations.csv` (23,996 records)
- **Maps**: DENUE fields to project schema
- **Note**: Leaves US-specific animal fields empty
- **Run time**: ~1.0s
- **Produces**: 7.85 MB file ready for project

---

## Phase 4: Deployment (Required)

### `copy_to_project.py`
- **Purpose**: Deploy processed data to project
- **Input**: `locations.csv` (from Phase 3)
- **Output**: `../../static_data/mx/locations.csv`
- **Creates**: `static_data/mx/` directory if needed
- **Run time**: ~0.2s
- **Result**: Data deployed and ready for backend integration

---

## Phase 5: Verification (Optional)

### `verify_deployment.py`
- **Purpose**: Verify deployment was successful
- **Input**: `../../static_data/mx/locations.csv`
- **Output**: Console report (no file)
- **Verifies**:
  - File exists and is readable
  - All records have coordinates
  - Facility types are correct
  - Distribution across states
  - Contact information coverage
- **Run time**: ~0.5s

---

## Complete Pipeline

Run all required scripts in order:

```bash
python3 03_create_filtered_csv.py
python3 04_clean_data.py
python3 05_convert_to_project_schema.py
python3 copy_to_project.py
python3 verify_deployment.py
```

**Total execution time: ~3-4 seconds**

---

## Files Summary

| File | Type | Size | Records | Purpose |
|------|------|------|---------|---------|
| `denue_inegi_11_.csv` | Input | 12.9 MB | 25,465 | Original DENUE data |
| `mexico_filtered.csv` | Intermediate | 9.2 MB | 23,996 | Filtered facilities |
| `mexico_cleaned.csv` | Intermediate | 10.1 MB | 23,996 | Cleaned data |
| `locations.csv` | Output | 7.85 MB | 23,996 | Project schema |
| `locations.csv` | Deployed | 7.85 MB | 23,996 | In `static_data/mx/` |

---

## Environment

- **Python**: 3.10+ (uses csv, shutil modules)
- **Encoding**: Latin-1 for input, UTF-8 for project integration
- **OS**: Windows, Linux, macOS

---

## Troubleshooting

### "ModuleNotFoundError"
Python needs CSV module (built-in). Ensure Python 3.10+ installed.

### "File not found"
Ensure script is run from `dirty-datasets/mexico/` directory.

### "UnicodeDecodeError"
Scripts handle encoding automatically. If custom data, update encoding parameter.

### "Permission denied"
Ensure write permissions to `static_data/mx/` directory.

---

## Documentation

- **`README.md`** - Quick start guide
- **`MEXICO_DATA_PIPELINE.md`** - Detailed technical documentation
- **`INTEGRATION_SUMMARY.md`** - Integration status and next steps
- **`denue_diccionario_de_datos.csv`** - DENUE field definitions (Spanish)

---

## Statistics at a Glance

```
Original DENUE records:     25,465
Animal facilities extracted: 23,996 (94.2%)
Final deployment:           23,996 records
Coverage:                   32 states, 1,081 municipalities
Data quality:               100% coordinates valid
```
