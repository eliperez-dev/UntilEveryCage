#!/usr/bin/env python3
"""
Script to filter DENUE dataset for animal-related facilities.

This script identifies facilities involved in:
- Aquaculture (fish farming)
- Fishing operations
- Animal farming and breeding services
- Meat processing and slaughter operations (if present)
- Animal research/testing (if present)

SCIAN Code Mappings:
  Aquaculture:
    - 112513: Shrimp aquaculture (saltwater)
    - 112514: Crustacean aquaculture (freshwater)
    - 112515: Fish aquaculture (freshwater)
    - 112516: Fish aquaculture (saltwater)
    - 112519: Other aquaculture
  
  Fishing:
    - 114111: Shrimp fishing
    - 114112: Tuna fishing
    - 114113: Sardine/anchovy fishing
    - 114119: Fish/crustacean/mollusk fishing and capture
  
  Animal farming services:
    - 115210: Services related to animal raising and exploitation
"""

import csv
from collections import defaultdict

AQUACULTURE_CODES = {'112513', '112514', '112515', '112516', '112519'}
FISHING_CODES = {'114111', '114112', '114113', '114119'}
ANIMAL_FARMING_CODES = {'115210'}

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

def classify_facility(scian_code):
    if scian_code in AQUACULTURE_CODES:
        return 'Aquaculture Facility'
    elif scian_code in FISHING_CODES:
        return 'Fishing Operation'
    elif scian_code in ANIMAL_FARMING_CODES:
        return 'Animal Farming Service'
    return None

def main():
    relevant_facilities = []
    facility_types = defaultdict(int)
    
    print("Filtering DENUE dataset for animal-related facilities...\n")
    
    try:
        with open('denue_inegi_11_.csv', 'r', encoding='latin-1') as f:
            reader = csv.DictReader(f)
            for row in reader:
                scian_code = row.get('codigo_act', '').strip()
                
                if scian_code in FACILITY_TYPE_MAPPING:
                    facility_type = FACILITY_TYPE_MAPPING[scian_code]
                    relevant_facilities.append({
                        'row': row,
                        'facility_type': facility_type,
                        'scian_code': scian_code
                    })
                    facility_types[facility_type] += 1
    
    except Exception as e:
        print(f"Error reading file: {e}")
        return
    
    print(f"Found {len(relevant_facilities)} animal-related facilities\n")
    print("Breakdown by facility type:")
    print("-" * 50)
    for ftype, count in sorted(facility_types.items()):
        print(f"  {ftype}: {count}")
    
    print(f"\nTotal facilities to include: {sum(facility_types.values())}")
    
    print("\nSample facilities by type:")
    print("-" * 50)
    
    shown_by_type = defaultdict(int)
    for facility in relevant_facilities[:20]:
        ftype = facility['facility_type']
        if shown_by_type[ftype] < 2:
            row = facility['row']
            print(f"\n[{ftype}]")
            print(f"  Name: {row.get('nom_estab', 'N/A')}")
            print(f"  Location: {row.get('municipio', 'N/A')}, {row.get('entidad', 'N/A')}")
            print(f"  SCIAN: {facility['scian_code']}")
            print(f"  Activity: {row.get('nombre_act', 'N/A')}")
            shown_by_type[ftype] += 1
    
    print(f"\n[OK] Analysis complete. Found {len(relevant_facilities)} facilities to process.")
    return relevant_facilities

if __name__ == '__main__':
    main()
