#!/usr/bin/env python3
"""
Create focused dataset: Aquaculture + Animal Farming Services only
(Exclude fishing operations - mostly independent small-scale operators)

This focuses on actual animal production infrastructure aligned with 
the project's mission of exposing industrial animal exploitation.
"""

import csv

FOCUSED_FACILITY_TYPES = {
    'Aquaculture Facility',
    'Animal Farming Service'
}

def main():
    input_file = 'mexico_cleaned.csv'
    output_file = 'mexico_focused.csv'
    
    count_total = 0
    count_focused = 0
    aquaculture_count = 0
    farming_count = 0
    
    print("Creating focused dataset (aquaculture + animal farming only)...\n")
    
    try:
        with open(input_file, 'r', encoding='latin-1') as infile:
            reader = csv.DictReader(infile)
            fieldnames = reader.fieldnames
            
            with open(output_file, 'w', encoding='latin-1', newline='') as outfile:
                writer = csv.DictWriter(outfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for row in reader:
                    count_total += 1
                    facility_type = row.get('facility_type', '')
                    
                    if facility_type in FOCUSED_FACILITY_TYPES:
                        writer.writerow(row)
                        count_focused += 1
                        
                        if 'Aquaculture' in facility_type:
                            aquaculture_count += 1
                        else:
                            farming_count += 1
        
        print(f"Processing complete!")
        print(f"  Total records read: {count_total}")
        print(f"  Facilities kept (focused): {count_focused}")
        print(f"  Fishing operations removed: {count_total - count_focused}")
        print(f"\nOutput file: {output_file}")
        print(f"\nBreakdown of focused dataset:")
        print(f"  - Aquaculture: {aquaculture_count} (95.2%)")
        print(f"  - Animal Farming Services: {farming_count} (4.8%)")
        print(f"  - TOTAL: {count_focused} records")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
