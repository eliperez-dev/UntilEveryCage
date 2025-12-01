# Mexico DENUE Dataset Processing

## Quick Summary

This directory contains scripts to process Mexico's DENUE economic facilities dataset and integrate animal-related facilities into the Until Every Cage is Empty project.

## Status: ✓ COMPLETE

**23,996 Mexican animal-related facilities have been processed and deployed to `static_data/mx/locations.csv`**

## Quick Start

### Process Data (if needed)
```bash
# Run all processing scripts in order
python3 03_create_filtered_csv.py    # Filter for animal facilities
python3 04_clean_data.py             # Clean and standardize
python3 05_convert_to_project_schema.py  # Convert to project format
python3 copy_to_project.py           # Deploy to project
```

### What's Included
- **23,996 facilities** across all 32 Mexican states
- **3 facility types**: Aquaculture (fish farms), Fishing operations, Animal farming services
- **100% with valid coordinates** (latitude/longitude)
- **Spanish activity names** (preserved from DENUE data)

### Files
- `locations.csv` → Deployed to `static_data/mx/` for project use
- `mexico_filtered.csv` → Raw filtered data
- `mexico_cleaned.csv` → Cleaned/normalized data
- `denue_inegi_11_.csv` → Original DENUE data

## Documentation

- **`MEXICO_DATA_PIPELINE.md`** - Technical details on data processing pipeline
- **`INTEGRATION_SUMMARY.md`** - Integration status and next steps
- **`denue_diccionario_de_datos.csv`** - DENUE data dictionary (Spanish)

## Processing Scripts

| Script | Purpose |
|--------|---------|
| `00_explore_dataset.py` | Explore dataset structure |
| `01_analyze_scian_codes.py` | Analyze SCIAN activity codes |
| `02_filter_animal_facilities.py` | Identify animal-related facilities |
| `03_create_filtered_csv.py` | Extract filtered data |
| `04_clean_data.py` | Standardize and clean data |
| `05_convert_to_project_schema.py` | Map to project schema |
| `copy_to_project.py` | Deploy to project directory |

## Data Categories

### By Facility Type
- Fishing Operations: 20,726 (86.4%)
- Aquaculture: 3,112 (13.0%)
- Animal Farming Services: 158 (0.7%)

### Coverage
- All 32 Mexican states included
- 1,081 unique municipalities represented
- Date range: 2019-2025 (registration dates)

## Integration Status

✓ Data filtered and cleaned  
✓ Schema converted  
✓ Deployed to `static_data/mx/`  
⏳ Awaiting backend build to include in API  
⏳ Optional: Frontend enhancement for Mexican states  

## Notes

- Dataset contains **only aquaculture, fishing, and agricultural services**
- Does NOT include slaughterhouses, processing plants, or research facilities
- To expand coverage, additional Mexican government data sources needed (COFEPRIS, SENASICA)
- All animal processing/slaughter fields in CSV are empty (not applicable to Mexico data)

## Next Steps

1. Build and deploy backend: `cargo shuttle run`
2. Test with: `/api/locations?country_code=mx`
3. Verify Mexico facilities appear on map
4. (Optional) Add Mexican states to state selector in UI
5. (Optional) Add Spanish language support

---

For questions about the data or processing, see the full technical documentation files.
