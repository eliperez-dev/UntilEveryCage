#!/usr/bin/env python3
"""
Combine labs, meat, and aquaculture data into unified locations.csv

This script:
1. Reads labs.csv, meat.csv, and aquaculture(cleaned).csv
2. Maps all three to the unified Location schema used across all countries
3. Intelligently populates animal slaughter/processing fields based on activity descriptions
4. Outputs to static_data/mx/locations.csv
"""

import csv
import os
import sys
from collections import defaultdict

ACTIVITY_TO_ANIMALS = {
    'beef': {
        'beef_slaughter': 'Yes', 'beef_cow_slaughter': 'Yes', 'steer_slaughter': 'Yes',
        'heifer_slaughter': 'Yes', 'bull_stag_slaughter': 'Yes', 'dairy_cow_slaughter': 'Yes',
        'beef_processing': 'Yes'
    },
    'pork': {
        'market_swine_slaughter': 'Yes', 'sow_slaughter': 'Yes', 'roaster_swine_slaughter': 'Yes',
        'pork_processing': 'Yes'
    },
    'poultry': {
        'poultry_slaughter': 'Yes', 'young_chicken_slaughter': 'Yes', 'light_fowl_slaughter': 'Yes',
        'heavy_fowl_slaughter': 'Yes', 'young_turkey_slaughter': 'Yes',
        'chicken_processing': 'Yes', 'turkey_processing': 'Yes'
    },
    'avicultura': {
        'poultry_slaughter': 'Yes', 'young_chicken_slaughter': 'Yes',
        'chicken_processing': 'Yes'
    },
    'ganado': {
        'beef_slaughter': 'Yes', 'beef_cow_slaughter': 'Yes',
        'beef_processing': 'Yes'
    },
    'cerdo': {
        'market_swine_slaughter': 'Yes', 'pork_processing': 'Yes'
    },
    'conejo': {
        'rabbit_slaughter': 'Yes', 'rabbit_processing': 'Yes'
    },
    'cabra': {
        'goat_slaughter': 'Yes', 'goat_processing': 'Yes'
    },
    'oveja': {
        'sheep_slaughter': 'Yes'
    },
    'pez': {
        'poultry_slaughter': 'Yes'
    },
    'acuicultura': {},
    'piscicultura': {},
    'acua': {},
    'ranicultura': {}
}

def get_facility_type(activity_desc):
    activity_lower = (activity_desc or '').lower()
    
    if any(word in activity_lower for word in ['acuicultura', 'piscicultura', 'ranicultura', 'pez', 'acua']):
        return 'Aquaculture'
    elif any(word in activity_lower for word in ['laboratorio', 'investigacion', 'analytical', 'análisis']):
        return 'Laboratory'
    elif any(word in activity_lower for word in ['matanza', 'slaughter', 'sacrifi']):
        return 'Slaughterhouse'
    else:
        return 'Processing'

def get_animal_fields(activity_desc):
    """Map activity description to animal slaughter/processing fields"""
    animal_fields = {}
    activity_lower = (activity_desc or '').lower()
    
    for keyword, fields in ACTIVITY_TO_ANIMALS.items():
        if keyword in activity_lower:
            animal_fields.update(fields)
    
    if 'ganado' in activity_lower or 'carne' in activity_lower:
        animal_fields['meat_slaughter'] = 'Yes'
    if 'aves' in activity_lower:
        animal_fields['poultry_slaughter'] = 'Yes'
    
    return animal_fields

def clean_phone(phone_str):
    if not phone_str or phone_str.strip() == '':
        return ''
    phone = phone_str.strip()
    return phone if phone else ''

def clean_address_from_parts(tipo_vial, nom_vial, numero_ext, letra_ext, numero_int, letra_int):
    """Reconstruct address from DENUE parts"""
    parts = []
    
    if tipo_vial and tipo_vial.strip():
        parts.append(tipo_vial.strip())
    if nom_vial and nom_vial.strip():
        parts.append(nom_vial.strip())
    if numero_ext and numero_ext.strip():
        parts.append(numero_ext.strip())
    if letra_ext and letra_ext.strip():
        parts.append(letra_ext.strip())
    
    address = ' '.join(parts)
    
    if numero_int and numero_int.strip():
        address += f" Int. {numero_int.strip()}"
    if letra_int and letra_int.strip():
        address += f" {letra_int.strip()}"
    
    return address if address.strip() else ''

def clean_coordinates(lat_str, lon_str):
    try:
        lat = float(lat_str) if lat_str and lat_str.strip() else None
        lon = float(lon_str) if lon_str and lon_str.strip() else None
        
        if lat and lon:
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return (lat, lon)
    except (ValueError, TypeError):
        pass
    
    return (None, None)

def process_labs_meat(input_file, facility_type_name, output_rows):
    """Process labs.csv or meat.csv files"""
    try:
        with open(input_file, 'r', encoding='latin-1', errors='replace') as f:
            reader = csv.DictReader(f)
            count = 0
            
            for row in reader:
                try:
                    row_id = row.get('ID', '').strip()
                    if not row_id:
                        continue
                    
                    name = row.get('Nombre de la Unidad Económica', '').strip()
                    legal_name = row.get('Razón social', '').strip()
                    name = name or legal_name or 'Unknown'
                    activity_desc = row.get('Nombre de clase de la actividad', '').strip()
                    
                    address = clean_address_from_parts(
                        row.get('Tipo de vialidad', ''),
                        row.get('Nombre de la vialidad', ''),
                        row.get('Número exterior o kilómetro', ''),
                        row.get('Letra exterior', ''),
                        row.get('Número interior', ''),
                        row.get('Letra interior', '')
                    )
                    
                    city = row.get('Localidad', '').strip() or row.get('Municipio', '').strip() or ''
                    state = row.get('Entidad federativa', '').strip() or ''
                    postal_code = row.get('Código Postal', '').strip() or ''
                    phone = clean_phone(row.get('Número de teléfono', ''))
                    email = row.get('Correo electrónico', '').strip() or ''
                    
                    lat_str = row.get('Latitud', '').strip()
                    lon_str = row.get('Longitud', '').strip()
                    lat, lon = clean_coordinates(lat_str, lon_str)
                    
                    if lat is None or lon is None:
                        continue
                    
                    grant_date = row.get('Fecha de incorporación al DENUE', '').strip() or ''
                    
                    output_rows.append({
                        'establishment_id': row_id,
                        'establishment_number': row_id,
                        'establishment_name': name,
                        'duns_number': '',
                        'street': address,
                        'city': city,
                        'state': state,
                        'zip': postal_code,
                        'phone': phone,
                        'grant_date': grant_date,
                        'type': get_facility_type(activity_desc),
                        'dbas': legal_name,
                        'district': '',
                        'circuit': '',
                        'size': row.get('Descripcion estrato personal ocupado', '').strip() or '',
                        'latitude': lat,
                        'longitude': lon,
                        'county': '',
                        'fips_code': '',
                        'facility_type': get_facility_type(activity_desc),
                        'activity_desc': activity_desc,
                        'animal_fields': get_animal_fields(activity_desc)
                    })
                    
                    count += 1
                    if count % 1000 == 0:
                        print(f"  Processed {count} records from {os.path.basename(input_file)}...")
                
                except Exception as e:
                    continue
        
        print(f"Processed {count} records from {input_file}")
        return count
    
    except Exception as e:
        print(f"Error reading {input_file}: {e}")
        return 0

def process_aquaculture(input_file, output_rows):
    """Process aquaculture(cleaned).csv"""
    try:
        with open(input_file, 'r', encoding='latin-1') as f:
            reader = csv.DictReader(f)
            count = 0
            
            for row in reader:
                try:
                    est_id = row.get('establishment_id', '').strip()
                    if not est_id:
                        continue
                    
                    lat_str = row.get('latitude', '').strip()
                    lon_str = row.get('longitude', '').strip()
                    lat, lon = clean_coordinates(lat_str, lon_str)
                    
                    if lat is None or lon is None:
                        continue
                    
                    activity_desc = row.get('activities', '').strip() or row.get('type', '').strip()
                    
                    est_name = row.get('establishment_name', '').strip()
                    legal_name_aqua = row.get('dbas', '').strip()
                    est_name = est_name or legal_name_aqua or 'Unknown'
                    
                    output_rows.append({
                        'establishment_id': est_id,
                        'establishment_number': row.get('establishment_number', '').strip(),
                        'establishment_name': est_name,
                        'duns_number': row.get('duns_number', '').strip() or '',
                        'street': row.get('street', '').strip() or '',
                        'city': row.get('city', '').strip() or '',
                        'state': row.get('state', '').strip() or '',
                        'zip': row.get('zip', '').strip() or '',
                        'phone': row.get('phone', '').strip() or '',
                        'grant_date': row.get('grant_date', '').strip() or '',
                        'type': 'Aquaculture',
                        'dbas': row.get('dbas', '').strip() or '',
                        'district': row.get('district', '').strip() or '',
                        'circuit': row.get('circuit', '').strip() or '',
                        'size': row.get('size', '').strip() or '',
                        'latitude': lat,
                        'longitude': lon,
                        'county': row.get('county', '').strip() or '',
                        'fips_code': row.get('fips_code', '').strip() or '',
                        'facility_type': 'Aquaculture Farm',
                        'activity_desc': activity_desc,
                        'animal_fields': {}
                    })
                    
                    count += 1
                    if count % 1000 == 0:
                        print(f"  Processed {count} aquaculture records...")
                
                except Exception as e:
                    continue
        
        print(f"Processed {count} aquaculture records")
        return count
    
    except Exception as e:
        print(f"Error reading {input_file}: {e}")
        return 0

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dirty_datasets_root = os.path.dirname(script_dir)
    project_root = os.path.dirname(dirty_datasets_root)
    
    labs_file = os.path.join(dirty_datasets_root, 'mexico', 'labs.csv')
    meat_file = os.path.join(dirty_datasets_root, 'mexico', 'meat.csv')
    aqua_file = os.path.join(dirty_datasets_root, 'mexico', 'aquaculture(cleaned).csv')
    output_file = os.path.join(project_root, 'static_data', 'mx', 'locations.csv')
    
    output_rows = []
    
    print("=" * 60)
    print("COMBINING MEXICO LOCATION DATA")
    print("=" * 60)
    
    print("\nReading labs.csv...")
    labs_count = process_labs_meat(labs_file, 'Laboratory', output_rows)
    
    print("\nReading meat.csv...")
    meat_count = process_labs_meat(meat_file, 'Meat Processing', output_rows)
    
    print("\nReading aquaculture(cleaned).csv...")
    aqua_count = process_aquaculture(aqua_file, output_rows)
    
    print(f"\nTotal records collected: {len(output_rows)}")
    print(f"  - Labs: {labs_count}")
    print(f"  - Meat: {meat_count}")
    print(f"  - Aquaculture: {aqua_count}")
    
    all_slaughter_fields = [
        'meat_exemption_custom_slaughter', 'poultry_exemption_custom_slaughter', 'slaughter',
        'meat_slaughter', 'beef_cow_slaughter', 'steer_slaughter', 'heifer_slaughter',
        'bull_stag_slaughter', 'dairy_cow_slaughter', 'heavy_calf_slaughter', 'bob_veal_slaughter',
        'formula_fed_veal_slaughter', 'non_formula_fed_veal_slaughter', 'market_swine_slaughter',
        'sow_slaughter', 'roaster_swine_slaughter', 'boar_stag_swine_slaughter', 'stag_swine_slaughter',
        'feral_swine_slaughter', 'goat_slaughter', 'young_goat_slaughter', 'adult_goat_slaughter',
        'sheep_slaughter', 'lamb_slaughter', 'deer_reindeer_slaughter', 'antelope_slaughter',
        'elk_slaughter', 'bison_slaughter', 'buffalo_slaughter', 'water_buffalo_slaughter',
        'cattalo_slaughter', 'yak_slaughter', 'other_voluntary_livestock_slaughter', 'rabbit_slaughter',
        'poultry_slaughter', 'young_chicken_slaughter', 'light_fowl_slaughter', 'heavy_fowl_slaughter',
        'capon_slaughter', 'young_turkey_slaughter', 'young_breeder_turkey_slaughter',
        'old_breeder_turkey_slaughter', 'fryer_roaster_turkey_slaughter', 'duck_slaughter',
        'goose_slaughter', 'pheasant_slaughter', 'quail_slaughter', 'guinea_slaughter',
        'ostrich_slaughter', 'emu_slaughter', 'rhea_slaughter', 'squab_slaughter',
        'other_voluntary_poultry_slaughter', 'slaughter_or_processing_only', 'slaughter_only_class',
        'slaughter_only_species', 'meat_slaughter_only_species', 'poultry_slaughter_only_species',
        'slaughter_volume_category', 'processing_volume_category'
    ]
    
    all_processing_fields = [
        'beef_processing', 'pork_processing', 'antelope_processing', 'bison_processing',
        'buffalo_processing', 'deer_processing', 'elk_processing', 'goat_processing',
        'other_voluntary_livestock_processing', 'rabbit_processing', 'reindeer_processing',
        'sheep_processing', 'yak_processing', 'chicken_processing', 'duck_processing',
        'goose_processing', 'pigeon_processing', 'ratite_processing', 'turkey_processing',
        'exotic_poultry_processing', 'other_voluntary_poultry_processing'
    ]
    
    fieldnames = [
        'establishment_id', 'establishment_number', 'establishment_name', 'duns_number',
        'street', 'city', 'state', 'zip', 'phone', 'grant_date', 'type', 'activities', 'dbas',
        'district', 'circuit', 'size', 'latitude', 'longitude', 'county', 'fips_code'
    ] + all_slaughter_fields + all_processing_fields
    
    print(f"\nWriting to {output_file}...")
    
    try:
        with open(output_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for row_data in output_rows:
                output_row = {
                    'establishment_id': row_data['establishment_id'],
                    'establishment_number': row_data['establishment_number'],
                    'establishment_name': row_data['establishment_name'],
                    'duns_number': row_data['duns_number'],
                    'street': row_data['street'],
                    'city': row_data['city'],
                    'state': row_data['state'],
                    'zip': row_data['zip'],
                    'phone': row_data['phone'],
                    'grant_date': row_data['grant_date'],
                    'type': row_data['type'],
                    'activities': row_data['activity_desc'],
                    'dbas': row_data['dbas'],
                    'district': row_data['district'],
                    'circuit': row_data['circuit'],
                    'size': row_data['size'],
                    'latitude': row_data['latitude'],
                    'longitude': row_data['longitude'],
                    'county': row_data['county'],
                    'fips_code': row_data['fips_code']
                }
                
                for field in all_slaughter_fields + all_processing_fields:
                    output_row[field] = row_data['animal_fields'].get(field, '')
                
                writer.writerow(output_row)
        
        print(f"Successfully wrote {len(output_rows)} records to {output_file}")
        print("\nCombination complete!")
        
    except Exception as e:
        print(f"Error writing output file: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
