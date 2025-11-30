#!/usr/bin/env python3
"""
Convert focused Mexico data (aquaculture + animal farming only) to project schema.

This script:
1. Reads mexico_focused.csv (3,270 records)
2. Converts to project Location schema
3. Outputs locations_focused.csv
"""

import csv

FACILITY_TYPE_MAP = {
    'Aquaculture Facility': 'Aquaculture Farm',
    'Animal Farming Service': 'Farm / Breeder'
}

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
    
    # Empty animal processing/slaughter fields (not applicable to Mexico)
    for field in [
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
        'squab_slaughter', 'other_voluntary_poultry_slaughter', 'slaughter_or_processing_only',
        'slaughter_only_class', 'slaughter_only_species', 'meat_slaughter_only_species',
        'poultry_slaughter_only_species'
    ]:
        converted[field] = ''
    
    # Empty processing fields
    for field in [
        'beef_processing', 'pork_processing', 'antelope_processing',
        'bison_processing', 'buffalo_processing', 'deer_processing',
        'elk_processing', 'goat_processing', 'other_voluntary_livestock_processing',
        'rabbit_processing', 'reindeer_processing', 'sheep_processing',
        'yak_processing', 'chicken_processing', 'duck_processing', 'goose_processing',
        'pigeon_processing', 'ratite_processing', 'turkey_processing',
        'exotic_poultry_processing', 'other_voluntary_poultry_processing'
    ]:
        converted[field] = ''
    
    return converted

def main():
    input_file = 'mexico_focused.csv'
    output_file = 'locations_focused.csv'
    
    count_processed = 0
    
    print(f"Converting focused dataset to project schema...")
    print(f"Input: {input_file}\n")
    
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
                    
                    if count_processed % 500 == 0:
                        print(f"  Converted {count_processed} records...")
        
        print(f"\nConversion complete!")
        print(f"Records converted: {count_processed}")
        print(f"Output file: {output_file} ({count_processed} records)")
        print(f"\nReady for deployment to: static_data/mx/locations.csv")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
