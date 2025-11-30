#!/usr/bin/env python3
"""
Step 3: Convert cleaned Mexico data to project schema.

This script:
1. Reads the cleaned data
2. Maps to project Location struct fields
3. Handles facility type classification
4. Outputs 'locations.csv' ready for static_data/mx/

The Mexico facilities are limited compared to US data:
- No detailed animal processing/slaughter fields available
- Use 'type', 'activities' for facility classification
- Map SCIAN codes to human-readable facility types
"""

import csv
import re

FACILITY_TYPE_MAP = {
    'Aquaculture Facility': 'Aquaculture Farm',
    'Fishing Operation': 'Fishing Operation',
    'Animal Farming Service': 'Farm / Breeder'
}

def classify_as_type(facility_type):
    """Map facility type to data type category."""
    if 'Aquaculture' in facility_type:
        return 'Aquaculture'
    elif 'Fishing' in facility_type:
        return 'Fishing'
    else:
        return 'Breeding/Farming'

def convert_employees_range(range_str):
    """Convert Mexico employee range format to standardized text."""
    if not range_str:
        return 'Unknown'
    
    range_map = {
        '0 a 5 personas': '0-5',
        '6 a 10 personas': '6-10',
        '11 a 30 personas': '11-30',
        '31 a 50 personas': '31-50',
        '51 a 100 personas': '51-100',
        '101 a 250 personas': '101-250',
        '251 y mas': '250+'
    }
    
    return range_map.get(range_str, range_str)

def convert_row(row):
    """Convert cleaned row to project schema."""
    converted = {}
    
    converted['establishment_id'] = row.get('id', '').strip()
    converted['establishment_number'] = row.get('id', '').strip()
    converted['establishment_name'] = row.get('establishment_name', '').strip()
    converted['duns_number'] = ''
    
    converted['street'] = row.get('street', '').strip()
    converted['city'] = row.get('city', '').strip() or row.get('municipality', '').strip()
    converted['state'] = row.get('state', '').strip()
    converted['zip'] = row.get('postal_code', '').strip()
    converted['phone'] = row.get('phone', '').strip()
    converted['grant_date'] = row.get('date_added', '').strip()
    
    facility_type = row.get('facility_type', '')
    converted['type'] = FACILITY_TYPE_MAP.get(facility_type, facility_type)
    converted['activities'] = row.get('activity_name', '').strip()
    converted['dbas'] = row.get('legal_name', '').strip()
    
    converted['district'] = ''
    converted['circuit'] = ''
    converted['size'] = ''
    
    try:
        converted['latitude'] = float(row.get('latitude', 0) or 0)
    except (ValueError, TypeError):
        converted['latitude'] = 0
    
    try:
        converted['longitude'] = float(row.get('longitude', 0) or 0)
    except (ValueError, TypeError):
        converted['longitude'] = 0
    
    converted['county'] = row.get('municipality', '').strip()
    converted['fips_code'] = ''
    
    converted['processing_volume_category'] = ''
    converted['slaughter_volume_category'] = ''
    
    for facility_field in [
        'meat_exemption_custom_slaughter', 'poultry_exemption_custom_slaughter',
        'slaughter', 'meat_slaughter', 'beef_cow_slaughter', 'steer_slaughter',
        'heifer_slaughter', 'bull_stag_slaughter', 'dairy_cow_slaughter',
        'heavy_calf_slaughter', 'bob_veal_slaughter', 'formula_fed_veal_slaughter',
        'non_formula_fed_veal_slaughter', 'market_swine_slaughter', 'sow_slaughter',
        'roaster_swine_slaughter', 'boar_stag_swine_slaughter', 'stag_swine_slaughter',
        'feral_swine_slaughter', 'goat_slaughter', 'young_goat_slaughter',
        'adult_goat_slaughter', 'sheep_slaughter', 'lamb_slaughter',
        'deer_reindeer_slaughter', 'antelope_slaughter', 'elk_slaughter',
        'bison_slaughter', 'buffalo_slaughter', 'water_buffalo_slaughter',
        'cattalo_slaughter', 'yak_slaughter', 'other_voluntary_livestock_slaughter',
        'rabbit_slaughter', 'poultry_slaughter', 'young_chicken_slaughter',
        'light_fowl_slaughter', 'heavy_fowl_slaughter', 'capon_slaughter',
        'young_turkey_slaughter', 'young_breeder_turkey_slaughter',
        'old_breeder_turkey_slaughter', 'fryer_roaster_turkey_slaughter',
        'duck_slaughter', 'goose_slaughter', 'pheasant_slaughter', 'quail_slaughter',
        'guinea_slaughter', 'ostrich_slaughter', 'emu_slaughter', 'rhea_slaughter',
        'squab_slaughter', 'other_voluntary_poultry_slaughter'
    ]:
        converted[facility_field] = ''
    
    for processing_field in [
        'beef_processing', 'pork_processing', 'antelope_processing',
        'bison_processing', 'buffalo_processing', 'deer_processing',
        'elk_processing', 'goat_processing', 'other_voluntary_livestock_processing',
        'rabbit_processing', 'reindeer_processing', 'sheep_processing',
        'yak_processing', 'chicken_processing', 'duck_processing', 'goose_processing',
        'pigeon_processing', 'ratite_processing', 'turkey_processing',
        'exotic_poultry_processing', 'other_voluntary_poultry_processing'
    ]:
        converted[processing_field] = ''
    
    return converted

def main():
    input_file = 'mexico_cleaned.csv'
    output_file = 'locations.csv'
    
    count_processed = 0
    
    print(f"Reading from {input_file}...")
    
    try:
        with open(input_file, 'r', encoding='latin-1') as infile:
            reader = csv.DictReader(infile)
            
            fieldnames = [
                'establishment_id', 'establishment_number', 'establishment_name', 'duns_number',
                'street', 'city', 'state', 'zip', 'phone', 'grant_date', 'type', 'activities',
                'dbas', 'district', 'circuit', 'size', 'latitude', 'longitude', 'county', 'fips_code',
                'meat_exemption_custom_slaughter', 'poultry_exemption_custom_slaughter', 'slaughter',
                'meat_slaughter', 'beef_cow_slaughter', 'steer_slaughter', 'heifer_slaughter',
                'bull_stag_slaughter', 'dairy_cow_slaughter', 'heavy_calf_slaughter', 'bob_veal_slaughter',
                'formula_fed_veal_slaughter', 'non_formula_fed_veal_slaughter', 'market_swine_slaughter',
                'sow_slaughter', 'roaster_swine_slaughter', 'boar_stag_swine_slaughter',
                'stag_swine_slaughter', 'feral_swine_slaughter', 'goat_slaughter', 'young_goat_slaughter',
                'adult_goat_slaughter', 'sheep_slaughter', 'lamb_slaughter', 'deer_reindeer_slaughter',
                'antelope_slaughter', 'elk_slaughter', 'bison_slaughter', 'buffalo_slaughter',
                'water_buffalo_slaughter', 'cattalo_slaughter', 'yak_slaughter',
                'other_voluntary_livestock_slaughter', 'rabbit_slaughter', 'poultry_slaughter',
                'young_chicken_slaughter', 'light_fowl_slaughter', 'heavy_fowl_slaughter',
                'capon_slaughter', 'young_turkey_slaughter', 'young_breeder_turkey_slaughter',
                'old_breeder_turkey_slaughter', 'fryer_roaster_turkey_slaughter', 'duck_slaughter',
                'goose_slaughter', 'pheasant_slaughter', 'quail_slaughter', 'guinea_slaughter',
                'ostrich_slaughter', 'emu_slaughter', 'rhea_slaughter', 'squab_slaughter',
                'other_voluntary_poultry_slaughter', 'slaughter_or_processing_only',
                'slaughter_only_class', 'slaughter_only_species', 'meat_slaughter_only_species',
                'poultry_slaughter_only_species', 'slaughter_volume_category', 'processing_volume_category',
                'beef_processing', 'pork_processing', 'antelope_processing', 'bison_processing',
                'buffalo_processing', 'deer_processing', 'elk_processing', 'goat_processing',
                'other_voluntary_livestock_processing', 'rabbit_processing', 'reindeer_processing',
                'sheep_processing', 'yak_processing', 'chicken_processing', 'duck_processing',
                'goose_processing', 'pigeon_processing', 'ratite_processing', 'turkey_processing',
                'exotic_poultry_processing', 'other_voluntary_poultry_processing'
            ]
            
            with open(output_file, 'w', encoding='latin-1', newline='') as outfile:
                writer = csv.DictWriter(outfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for row in reader:
                    converted = convert_row(row)
                    writer.writerow(converted)
                    count_processed += 1
                    
                    if count_processed % 5000 == 0:
                        print(f"  Converted {count_processed} records...")
        
        print(f"\nConversion complete!")
        print(f"Records converted: {count_processed}")
        print(f"Output file: {output_file}")
        print(f"\nReady for: static_data/mx/locations.csv")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
