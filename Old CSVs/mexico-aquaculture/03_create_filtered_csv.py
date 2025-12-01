#!/usr/bin/env python3
"""
Step 1: Filter DENUE dataset for animal-related facilities and save to new CSV.

This script:
1. Reads the full DENUE CSV
2. Filters for relevant animal exploitation facilities
3. Saves filtered data to 'mexico_filtered.csv'
"""

import csv

RELEVANT_SCIAN_CODES = {
    '112513', '112514', '112515', '112516', '112519',
    '114111', '114112', '114113', '114119',
    '115210'
}

FACILITY_TYPE_MAPPING = {
    '112513': 'Aquaculture Facility',
    '112514': 'Aquaculture Facility',
    '112515': 'Aquaculture Facility',
    '112516': 'Aquaculture Facility',
    '112519': 'Aquaculture Facility',
    '114111': 'Fishing Operation',
    '114112': 'Fishing Operation',
    '114113': 'Fishing Operation',
    '114119': 'Fishing Operation',
    '115210': 'Animal Farming Service'
}

def main():
    input_file = 'denue_inegi_11_.csv'
    output_file = 'mexico_filtered.csv'
    
    count_filtered = 0
    count_total = 0
    
    print(f"Reading from {input_file}...")
    
    try:
        with open(input_file, 'r', encoding='latin-1') as infile:
            reader = csv.DictReader(infile)
            fieldnames = reader.fieldnames + ['facility_type']
            
            with open(output_file, 'w', encoding='latin-1', newline='') as outfile:
                writer = csv.DictWriter(outfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for row in reader:
                    count_total += 1
                    scian_code = row.get('codigo_act', '').strip()
                    
                    if scian_code in RELEVANT_SCIAN_CODES:
                        row['facility_type'] = FACILITY_TYPE_MAPPING[scian_code]
                        writer.writerow(row)
                        count_filtered += 1
                    
                    if count_total % 5000 == 0:
                        print(f"  Processed {count_total} records ({count_filtered} filtered)...")
        
        print(f"\nProcessing complete!")
        print(f"Total records read: {count_total}")
        print(f"Facilities filtered: {count_filtered}")
        print(f"Output file: {output_file}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
