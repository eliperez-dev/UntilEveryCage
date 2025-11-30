#!/usr/bin/env python3
"""
Combine all 17 Ontario meat facility CSVs into a single consolidated dataset.

This script:
1. Reads all 17 CSV files from dirty-datasets/canada/Ontario/
2. Deduplicates by Plant Number (unique identifier)
3. Preserves all data columns
4. Outputs a single consolidated CSV with all Ontario facilities
"""

import csv
import os
from pathlib import Path
from collections import OrderedDict

def read_csv_rows(filepath):
    """Read CSV file and return list of rows as dictionaries."""
    rows = []
    encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252', 'utf-8-sig']
    
    for encoding in encodings:
        try:
            with open(filepath, 'r', encoding=encoding) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append(row)
            return rows
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception as e:
            print(f"Error reading {filepath} with {encoding}: {e}")
            return rows
    
    print(f"Error reading {filepath}: Could not decode with any encoding")
    return rows

def combine_ontario_csvs():
    """Combine all 17 Ontario CSV files into one consolidated dataset."""
    
    ontario_dir = Path('dirty-datasets/canada/Ontario')
    
    # Get all CSV files in the Ontario directory, sorted by filename
    csv_files = sorted([f for f in ontario_dir.glob('*.csv')])
    
    print(f"Found {len(csv_files)} CSV files in {ontario_dir}")
    print("\nFiles to process:")
    for i, f in enumerate(csv_files, 1):
        print(f"  {i}. {f.name}")
    
    # Read the main file first (1._all_meat_plants.csv)
    main_file = ontario_dir / '1._all_meat_plants.csv'
    print(f"\nLoading base file: {main_file.name}")
    rows = read_csv_rows(main_file)
    print(f"  - Loaded {len(rows)} rows")
    
    # Create a dictionary keyed by Plant Number for deduplication
    plant_dict = OrderedDict()
    fieldnames = None
    
    for row in rows:
        plant_num = row.get("Plant Number_No. de l'usine")
        if plant_num:
            plant_dict[plant_num] = row
            if fieldnames is None:
                fieldnames = list(row.keys())
    
    print(f"  - Deduplicated to {len(plant_dict)} unique plants")
    
    # Process all other files (exclude the consolidated output if it exists)
    other_files = [f for f in csv_files if f.name != '1._all_meat_plants.csv' and f.name != 'ONTARIO_CONSOLIDATED.csv']
    
    for csv_file in other_files:
        print(f"\nProcessing: {csv_file.name}")
        rows = read_csv_rows(csv_file)
        print(f"  - Loaded {len(rows)} rows")
        
        for row in rows:
            plant_num = row.get("Plant Number_No. de l'usine")
            
            if plant_num and plant_num not in plant_dict:
                # New facility not in main file
                plant_dict[plant_num] = row
        
        print(f"  - Now have {len(plant_dict)} unique plants total")
    
    # Convert to list of rows, sorted by Plant Number (alphanumeric)
    def sort_key(row):
        plant_num = str(row.get("Plant Number_No. de l'usine", "0"))
        # Try to convert to int if all numeric, otherwise use string
        try:
            return (0, int(plant_num))
        except ValueError:
            return (1, plant_num)
    
    final_rows = sorted(plant_dict.values(), key=sort_key)
    
    # Output consolidated CSV
    output_file = Path('dirty-datasets/canada/Ontario/ONTARIO_CONSOLIDATED.csv')
    
    if fieldnames is None and final_rows:
        fieldnames = list(final_rows[0].keys())
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(final_rows)
    
    print(f"\n{'='*70}")
    print(f"CONSOLIDATION COMPLETE!")
    print(f"{'='*70}")
    print(f"Output file: {output_file}")
    print(f"Total facilities: {len(final_rows)}")
    print(f"\nData Summary:")
    print(f"  - Columns: {len(fieldnames) if fieldnames else 0}")
    print(f"  - Rows: {len(final_rows)}")
    
    # Show sample
    if final_rows:
        print(f"\nFirst 3 facilities:")
        for i, row in enumerate(final_rows[:3], 1):
            plant_name = row.get("Plant Name_ Nom de l'usine", 'N/A')
            plant_num = row.get("Plant Number_No. de l'usine", 'N/A')
            city = row.get('City_Ville', 'N/A')
            print(f"  {i}. {plant_name} (#{plant_num}) - {city}")
    
    # Data quality checks
    coords_count = sum(1 for r in final_rows if r.get('Latitude', '').strip())
    phone_count = sum(1 for r in final_rows if r.get('Telephone_Téléphone', '').strip())
    
    print(f"\nData quality checks:")
    print(f"  - Plants with coordinates: {coords_count}")
    print(f"  - Plants missing coordinates: {len(final_rows) - coords_count}")
    print(f"  - Plants with phone: {phone_count}")
    
    return final_rows

if __name__ == '__main__':
    combine_ontario_csvs()
