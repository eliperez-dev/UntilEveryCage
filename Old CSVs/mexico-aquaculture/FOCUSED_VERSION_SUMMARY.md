# Mexico Focused Dataset - Summary

**Status**: ✓ DEPLOYED

## Overview

Created a **focused version** of the Mexico dataset containing only industrial animal production infrastructure, excluding small-scale independent fishing operations.

## What Changed

### Original Dataset (Full Version)
- **Total**: 23,996 facilities
- Composition:
  - Fishing Operations: 20,726 (86.4%)
  - Aquaculture Farms: 3,112 (13.0%)
  - Animal Farming Services: 158 (0.7%)

### New Focused Dataset
- **Total**: 3,270 facilities ✓ **DEPLOYED**
- Composition:
  - Aquaculture Farms: 3,112 (95.2%)
  - Animal Farming Services: 158 (4.8%)
  - Fishing Operations: 0 (excluded)

### Rationale

**Removed 20,726 fishing operations (86.4%) because:**
1. **76.7% are 0-5 employees** = independent/small-scale operators
2. **Misaligned with project focus** = infrastructure of industrial animal exploitation
3. **Not comparable to US data** = which focuses on slaughterhouses, processing, research
4. **Dilutes dataset quality** = artisanal operations vs. industrial infrastructure

**Kept aquaculture & animal farming because:**
1. Actual farm infrastructure & production facilities
2. Support services for livestock exploitation (genetics, holding, weighing)
3. Aligned with project mission
4. More valuable for analysis

## Data Quality

| Metric | Value |
|--------|-------|
| Total Records | 3,270 |
| Complete Coordinates | 3,270 (100%) |
| With Phone | 1,562 (47.8%) |
| States Covered | 32/32 (100%) |
| File Size | 0.96 MB |

## Geographic Coverage

All 32 Mexican states represented:
- Aquaculture concentrated in coastal states (Oaxaca, Tabasco, Veracruz)
- Animal farming services distributed across all states
- 1,000+ municipalities covered

## Facility Types

### Aquaculture Farms (3,112 - 95.2%)
Fish farms, shrimp farms, crustacean aquaculture
- Saltwater: 1,600+
- Freshwater: 1,500+

### Animal Farming Services (158 - 4.8%)
- Genetic services (semen sales, breeding)
- Livestock holding/collection centers
- Weighing stations
- Support infrastructure

## Files Generated

### Processing Scripts (new)
- `06_create_focused_filter.py` - Filter for focused facilities
- `07_convert_focused_to_schema.py` - Convert to project schema
- `08_deploy_focused.py` - Deploy to project
- `09_compare_versions.py` - Compare old vs new

### Data Files (new)
- `mexico_focused.csv` - Cleaned focused data (3,270 records)
- `locations_focused.csv` - Project schema version
- `static_data/mx/locations.csv` - **DEPLOYED** ✓

### Data Files (original)
- `locations.csv` - Full version with fishing (still available in dirty-datasets/mexico/)

## Deployment

**Current deployment**: `static_data/mx/locations.csv`
- 3,270 records
- Aquaculture + Animal farming services only
- 0.96 MB file size
- Ready for backend integration

## Usage

### Build & Test
```bash
cargo shuttle run
```

### Query API
```bash
# Get Mexico facilities
GET /api/locations?country_code=mx

# Expected: 3,270 facilities returned
```

### Verify Frontend
- Navigate to map
- Apply Mexico country filter
- Should see 3,270 facilities (not 23,996)
- Mostly aquaculture farms (green/yellow markers)

## If You Want to Switch Back

The full version is still available in `dirty-datasets/mexico/`:

```bash
cd dirty-datasets/mexico
python3 copy_to_project.py  # Uses locations.csv (full version)
```

This would deploy the 23,996 record version with fishing operations included.

## Next Steps

1. Rebuild backend with focused dataset
2. Test `/api/locations?country_code=mx`
3. Verify marker distribution on map
4. Deploy to production when ready

## Statistics

### Reduction
- Removed: 20,726 records (86.4%)
- Kept: 3,270 records (13.6%)
- File size reduction: 7.85 MB → 0.96 MB

### Quality Improvement
- Removed: Low-value small-scale operators
- Kept: Infrastructure aligned with project mission
- Result: Cleaner, more focused dataset

---

**Recommendation**: This focused version is better aligned with the project's goal of exposing the infrastructure of industrial animal exploitation. The removal of small-scale artisanal fishing operations makes the data more meaningful and comparable to other countries.

**Status**: Ready for deployment ✓
