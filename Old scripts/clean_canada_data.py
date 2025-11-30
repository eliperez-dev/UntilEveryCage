#!/usr/bin/env python3
"""
Clean Canadian meat facility data (Federal + Ontario) into Rust Location struct format.

Federal data has been geocoded by geocod.io and needs:
- Function codes parsed into facility type & animals
- Address parsed from components
- DBAs extracted from operator name

Ontario data already has most fields populated, needs:
- Animal booleans mapped to specific Location struct fields
"""

import csv
import os
from pathlib import Path
from collections import OrderedDict


def parse_function_codes(codes):
    """
    Parse Federal function codes into facility type and animal list.
    Format: "3x 6fx 9B/US 11ADFGKV"
    
    Facility types:
    1=Slaughter, 2=Canning, 3=Boning/Cutting, 4=Rendering, 
    6=Processing, 7=Packaging, 8=Inedible Rendering, 10=Storage
    
    Animals: a=Cattle, b=Calves, c=Sheep/Goats, d=Swine, 
    e=Horses, f=Poultry, g=Rabbits, x=Red Meat
    """
    if not codes or not codes.strip():
        return "Unknown", {}
    
    codes = codes.upper().strip()
    
    facility_type = "Unknown"
    animals = {}
    
    for char in codes:
        if char == '1':
            facility_type = "Slaughter"
        elif char == '2':
            facility_type = "Canning"
        elif char == '3':
            facility_type = "Boning and Cutting"
        elif char == '4':
            facility_type = "Rendering"
        elif char == '6':
            facility_type = "Processing"
        elif char == '7':
            facility_type = "Packaging"
        elif char == '8':
            facility_type = "Inedible Rendering"
        elif char.isdigit() and char != '1':
            if facility_type == "Unknown":
                facility_type = f"Type {char}"
    
    # Extract animals from codes
    animal_map = {
        'A': ('beef_cow_slaughter', 'beef_processing'),
        'B': ('beef_cow_slaughter', 'beef_processing'),
        'C': ('beef_cow_slaughter', 'beef_processing'),
        'D': ('market_swine_slaughter', 'pork_processing'),
        'E': ('market_swine_slaughter', 'pork_processing'),
        'F': ('young_chicken_slaughter', 'chicken_processing'),
        'G': ('young_chicken_slaughter', 'chicken_processing'),
        'I': ('young_chicken_slaughter', 'chicken_processing'),
        'K': ('young_turkey_slaughter', 'turkey_processing'),
        'R': ('duck_slaughter', 'duck_processing'),
        'S': ('goat_slaughter', 'goat_processing'),
        'V': ('sheep_slaughter', 'sheep_processing'),
        'X': ('rabbit_slaughter', 'rabbit_processing'),
    }
    
    for char in codes.upper():
        if char in animal_map:
            slaughter_field, processing_field = animal_map[char]
            if facility_type == "Slaughter":
                animals[slaughter_field] = "Yes"
            else:
                animals[processing_field] = "Yes"
    
    return facility_type, animals


def clean_operator_name(name):
    """Extract primary name and DBAs from operator field."""
    if not name:
        return "", ""
    
    if "Also Doing Business As" in name or "Also Doing Business as" in name:
        parts = name.split("Also Doing Business")
        primary = parts[0].strip()
        dbas = parts[1].strip() if len(parts) > 1 else ""
        dbas = dbas.replace("Name:", "").strip()
        return primary, dbas
    
    return name.strip(), ""


def extract_address_parts(geocodio_result):
    """Extract street, city, state, zip from geocod.io result."""
    street = geocodio_result.get('Geocodio Address Line 1', '').strip()
    city = geocodio_result.get('Geocodio City', '').strip()
    state = geocodio_result.get('Geocodio State', '').strip()
    postal = geocodio_result.get('Geocodio Postal Code', '').strip()
    
    return street, city, state, postal


def read_csv(filepath):
    """Read CSV with error handling for encoding."""
    encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
    
    for encoding in encodings:
        try:
            with open(filepath, 'r', encoding=encoding) as f:
                reader = csv.DictReader(f)
                return list(reader)
        except (UnicodeDecodeError, UnicodeError):
            continue
    
    return []


def create_location_row(data, country_code):
    """Create a Location struct CSV row from raw data."""
    row = OrderedDict()
    
    row['establishment_id'] = data.get('establishment_id', '')
    row['establishment_number'] = data.get('establishment_number', '')
    row['establishment_name'] = data.get('establishment_name', '')
    row['duns_number'] = ''
    row['street'] = data.get('street', '')
    row['city'] = data.get('city', '')
    row['state'] = data.get('state', '')
    row['zip'] = data.get('zip', '')
    row['phone'] = data.get('phone', '')
    row['grant_date'] = data.get('grant_date', '')
    row['type'] = data.get('type', '')
    row['dbas'] = data.get('dbas', '')
    row['district'] = ''
    row['circuit'] = ''
    row['size'] = ''
    row['latitude'] = data.get('latitude', '')
    row['longitude'] = data.get('longitude', '')
    row['county'] = data.get('county', '')
    row['fips_code'] = ''
    
    row['meat_exemption_custom_slaughter'] = ''
    row['poultry_exemption_custom_slaughter'] = ''
    row['slaughter'] = data.get('slaughter', '')
    row['meat_slaughter'] = data.get('meat_slaughter', '')
    row['beef_cow_slaughter'] = data.get('beef_cow_slaughter', '')
    row['steer_slaughter'] = data.get('steer_slaughter', '')
    row['heifer_slaughter'] = data.get('heifer_slaughter', '')
    row['bull_stag_slaughter'] = data.get('bull_stag_slaughter', '')
    row['dairy_cow_slaughter'] = data.get('dairy_cow_slaughter', '')
    row['heavy_calf_slaughter'] = data.get('heavy_calf_slaughter', '')
    row['bob_veal_slaughter'] = data.get('bob_veal_slaughter', '')
    row['formula_fed_veal_slaughter'] = data.get('formula_fed_veal_slaughter', '')
    row['non_formula_fed_veal_slaughter'] = data.get('non_formula_fed_veal_slaughter', '')
    row['market_swine_slaughter'] = data.get('market_swine_slaughter', '')
    row['sow_slaughter'] = data.get('sow_slaughter', '')
    row['roaster_swine_slaughter'] = data.get('roaster_swine_slaughter', '')
    row['boar_stag_swine_slaughter'] = data.get('boar_stag_swine_slaughter', '')
    row['stag_swine_slaughter'] = data.get('stag_swine_slaughter', '')
    row['feral_swine_slaughter'] = data.get('feral_swine_slaughter', '')
    row['goat_slaughter'] = data.get('goat_slaughter', '')
    row['young_goat_slaughter'] = data.get('young_goat_slaughter', '')
    row['adult_goat_slaughter'] = data.get('adult_goat_slaughter', '')
    row['sheep_slaughter'] = data.get('sheep_slaughter', '')
    row['lamb_slaughter'] = data.get('lamb_slaughter', '')
    row['deer_reindeer_slaughter'] = data.get('deer_reindeer_slaughter', '')
    row['antelope_slaughter'] = data.get('antelope_slaughter', '')
    row['elk_slaughter'] = data.get('elk_slaughter', '')
    row['bison_slaughter'] = data.get('bison_slaughter', '')
    row['buffalo_slaughter'] = data.get('buffalo_slaughter', '')
    row['water_buffalo_slaughter'] = data.get('water_buffalo_slaughter', '')
    row['cattalo_slaughter'] = data.get('cattalo_slaughter', '')
    row['yak_slaughter'] = data.get('yak_slaughter', '')
    row['other_voluntary_livestock_slaughter'] = data.get('other_voluntary_livestock_slaughter', '')
    row['rabbit_slaughter'] = data.get('rabbit_slaughter', '')
    row['poultry_slaughter'] = data.get('poultry_slaughter', '')
    row['young_chicken_slaughter'] = data.get('young_chicken_slaughter', '')
    row['light_fowl_slaughter'] = data.get('light_fowl_slaughter', '')
    row['heavy_fowl_slaughter'] = data.get('heavy_fowl_slaughter', '')
    row['capon_slaughter'] = data.get('capon_slaughter', '')
    row['young_turkey_slaughter'] = data.get('young_turkey_slaughter', '')
    row['young_breeder_turkey_slaughter'] = data.get('young_breeder_turkey_slaughter', '')
    row['old_breeder_turkey_slaughter'] = data.get('old_breeder_turkey_slaughter', '')
    row['fryer_roaster_turkey_slaughter'] = data.get('fryer_roaster_turkey_slaughter', '')
    row['duck_slaughter'] = data.get('duck_slaughter', '')
    row['goose_slaughter'] = data.get('goose_slaughter', '')
    row['pheasant_slaughter'] = data.get('pheasant_slaughter', '')
    row['quail_slaughter'] = data.get('quail_slaughter', '')
    row['guinea_slaughter'] = data.get('guinea_slaughter', '')
    row['ostrich_slaughter'] = data.get('ostrich_slaughter', '')
    row['emu_slaughter'] = data.get('emu_slaughter', '')
    row['rhea_slaughter'] = data.get('rhea_slaughter', '')
    row['squab_slaughter'] = data.get('squab_slaughter', '')
    row['other_voluntary_poultry_slaughter'] = data.get('other_voluntary_poultry_slaughter', '')
    row['slaughter_or_processing_only'] = ''
    row['slaughter_only_class'] = ''
    row['slaughter_only_species'] = ''
    row['meat_slaughter_only_species'] = ''
    row['poultry_slaughter_only_species'] = ''
    row['slaughter_volume_category'] = ''
    row['processing_volume_category'] = ''
    
    row['beef_processing'] = data.get('beef_processing', '')
    row['pork_processing'] = data.get('pork_processing', '')
    row['antelope_processing'] = data.get('antelope_processing', '')
    row['bison_processing'] = data.get('bison_processing', '')
    row['buffalo_processing'] = data.get('buffalo_processing', '')
    row['deer_processing'] = data.get('deer_processing', '')
    row['elk_processing'] = data.get('elk_processing', '')
    row['goat_processing'] = data.get('goat_processing', '')
    row['other_voluntary_livestock_processing'] = data.get('other_voluntary_livestock_processing', '')
    row['rabbit_processing'] = data.get('rabbit_processing', '')
    row['reindeer_processing'] = data.get('reindeer_processing', '')
    row['sheep_processing'] = data.get('sheep_processing', '')
    row['yak_processing'] = data.get('yak_processing', '')
    row['chicken_processing'] = data.get('chicken_processing', '')
    row['duck_processing'] = data.get('duck_processing', '')
    row['goose_processing'] = data.get('goose_processing', '')
    row['pigeon_processing'] = data.get('pigeon_processing', '')
    row['ratite_processing'] = data.get('ratite_processing', '')
    row['turkey_processing'] = data.get('turkey_processing', '')
    row['exotic_poultry_processing'] = data.get('exotic_poultry_processing', '')
    row['other_voluntary_poultry_processing'] = data.get('other_voluntary_poultry_processing', '')
    
    return row


def clean_federal_data():
    """Clean Federal geocoded data into Location format."""
    print("\n--- PROCESSING FEDERAL DATA ---")
    
    fed_file = Path('dirty-datasets/canada/Federal/federal_buildings_geocoded.csv')
    print(f"Reading: {fed_file}")
    
    rows = read_csv(fed_file)
    print(f"Loaded {len(rows)} facilities")
    
    cleaned_rows = []
    
    for i, row in enumerate(rows, 1):
        # Extract basic info
        estab_num = row.get('Establishment number', '').strip()
        operator_name, dbas = clean_operator_name(row.get('Name of the operator', ''))
        phone = row.get('Telephone Number', '').strip()
        
        # Parse function codes
        facility_type, animal_fields = parse_function_codes(row.get('Function Codes', ''))
        
        # Extract address
        street, city, state, postal = extract_address_parts(row)
        
        # Geocoding
        try:
            lat = float(row.get('Geocodio Latitude', 0) or 0)
            lon = float(row.get('Geocodio Longitude', 0) or 0)
        except:
            lat, lon = 0, 0
        
        # Build location data
        location_data = {
            'establishment_id': f"CA_FED_{estab_num}",
            'establishment_number': estab_num,
            'establishment_name': operator_name,
            'street': street,
            'city': city,
            'state': state,
            'zip': postal,
            'phone': phone,
            'grant_date': '2025-01-01',
            'type': facility_type,
            'dbas': dbas,
            'latitude': lat,
            'longitude': lon,
        }
        
        # Add animal fields
        location_data.update(animal_fields)
        
        cleaned_row = create_location_row(location_data, 'ca')
        cleaned_rows.append(cleaned_row)
        
        if (i % 100) == 0:
            print(f"  Processed {i}/{len(rows)}")
    
    return cleaned_rows


def clean_ontario_data():
    """Clean Ontario data into Location format."""
    print("\n--- PROCESSING ONTARIO DATA ---")
    
    ont_file = Path('dirty-datasets/canada/Ontario/ONTARIO_CONSOLIDATED.csv')
    print(f"Reading: {ont_file}")
    
    rows = read_csv(ont_file)
    print(f"Loaded {len(rows)} facilities")
    
    cleaned_rows = []
    
    for i, row in enumerate(rows, 1):
        plant_num = row.get("Plant Number_No. de l'usine", '').strip()
        plant_name = row.get("Plant Name_ Nom de l'usine", '').strip()
        
        # Extract address components
        street = row.get('Address_Adresse', '').strip()
        city = row.get('City_Ville', '').strip()
        state = row.get('Province', '').strip()
        postal = row.get('Postal Code_Code postal', '').strip()
        phone = row.get('Telephone_Téléphone', '').strip()
        
        # Determine facility type
        if row.get('FP_ETVA avec abattoir') == '1':
            facility_type = "Slaughter"
        elif row.get('FSMP_ETVA') == '1':
            facility_type = "Processing"
        else:
            facility_type = "Other"
        
        # Map animal booleans to fields
        animal_fields = {}
        
        if row.get('Beef_Boeuf') == '1':
            animal_fields['beef_cow_slaughter'] = 'Yes'
        if row.get('Pigs_Porcs') == '1':
            animal_fields['market_swine_slaughter'] = 'Yes'
        if row.get('Chicken, Fowl_Poulet, Oiseaux de basse-cour') == '1':
            animal_fields['young_chicken_slaughter'] = 'Yes'
        if row.get('Turkeys_Dindes') == '1':
            animal_fields['young_turkey_slaughter'] = 'Yes'
        if row.get('Ducks, Geese_Canards, Oies') == '1':
            animal_fields['duck_slaughter'] = 'Yes'
        if row.get('Rabbits_Lapins') == '1':
            animal_fields['rabbit_slaughter'] = 'Yes'
        if row.get('Goats, Lamb, Sheep_Chèvres, Agneaux, Moutons') == '1':
            animal_fields['goat_slaughter'] = 'Yes'
            animal_fields['lamb_slaughter'] = 'Yes'
            animal_fields['sheep_slaughter'] = 'Yes'
        if row.get('Veal, Light Calves_Veaux de boucherie, Veaux légers') == '1':
            animal_fields['heavy_calf_slaughter'] = 'Yes'
        if row.get('Deer, Elk_Cerfs, Élans') == '1':
            animal_fields['deer_reindeer_slaughter'] = 'Yes'
            animal_fields['elk_slaughter'] = 'Yes'
        if row.get('Buffalo,Yak_Bison, Yack') == '1':
            animal_fields['bison_slaughter'] = 'Yes'
            animal_fields['yak_slaughter'] = 'Yes'
        if row.get('Emus, Ostrich, Rhea_Émeus, Autruches, Nandous') == '1':
            animal_fields['ostrich_slaughter'] = 'Yes'
            animal_fields['emu_slaughter'] = 'Yes'
        if row.get('Alpaca, Llama_Alpaga, Lama') == '1':
            animal_fields['other_voluntary_livestock_slaughter'] = 'Yes'
        if row.get('Fancy Poultry_Volaille à chair fine') == '1':
            animal_fields['other_voluntary_poultry_slaughter'] = 'Yes'
        
        # Geocoding
        try:
            lat = float(row.get('Latitude', 0) or 0)
            lon = float(row.get('Longitude', 0) or 0)
        except:
            lat, lon = 0, 0
        
        # Build location data
        location_data = {
            'establishment_id': f"CA_ON_{plant_num}",
            'establishment_number': plant_num,
            'establishment_name': plant_name,
            'street': street,
            'city': city,
            'state': state,
            'zip': postal,
            'phone': phone,
            'grant_date': '2025-01-01',
            'type': facility_type,
            'dbas': '',
            'latitude': lat,
            'longitude': lon,
        }
        
        location_data.update(animal_fields)
        
        cleaned_row = create_location_row(location_data, 'ca')
        cleaned_rows.append(cleaned_row)
        
        if (i % 100) == 0:
            print(f"  Processed {i}/{len(rows)}")
    
    return cleaned_rows


def main():
    print("=" * 70)
    print("CANADA DATA CLEANING - Converting to Location struct format")
    print("=" * 70)
    
    # Clean Federal
    federal_cleaned = clean_federal_data()
    print(f"Federal cleaned: {len(federal_cleaned)} facilities")
    
    # Clean Ontario
    ontario_cleaned = clean_ontario_data()
    print(f"Ontario cleaned: {len(ontario_cleaned)} facilities")
    
    # Merge
    all_facilities = federal_cleaned + ontario_cleaned
    print(f"Total: {len(all_facilities)} facilities")
    
    # Write output
    output_file = Path('static_data/ca/locations.csv')
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    if all_facilities:
        fieldnames = list(all_facilities[0].keys())
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_facilities)
        
        print(f"\n" + "=" * 70)
        print(f"Output: {output_file}")
        print(f"Total facilities: {len(all_facilities)}")
        print("=" * 70)


if __name__ == '__main__':
    main()
