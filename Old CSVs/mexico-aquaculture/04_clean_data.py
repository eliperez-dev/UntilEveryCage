#!/usr/bin/env python3
"""
Step 2: Clean the filtered Mexico facilities data.

This script:
1. Handles missing/empty values
2. Standardizes address formatting
3. Cleans phone numbers
4. Validates coordinates
5. Consolidates multi-line address fields
6. Handles encoding/text issues
7. Outputs 'mexico_cleaned.csv'
"""

import csv
import re

def clean_phone(phone_str):
    if not phone_str or phone_str.strip() == '':
        return ''
    phone = phone_str.strip()
    phone = re.sub(r'[^\d\-\+\(\)]', '', phone)
    return phone if phone else ''

def clean_address(street_type, street_name, ext_number, ext_letter, int_number, int_letter):
    parts = []
    
    if street_type and street_type.strip():
        parts.append(street_type.strip())
    if street_name and street_name.strip():
        parts.append(street_name.strip())
    if ext_number and ext_number.strip():
        parts.append(ext_number.strip())
    if ext_letter and ext_letter.strip():
        parts.append(ext_letter.strip())
    
    address = ' '.join(parts)
    
    if int_number and int_number.strip():
        address += f" Int. {int_number.strip()}"
    if int_letter and int_letter.strip():
        address += f" {int_letter.strip()}"
    
    return address if address.strip() else 'Unknown'

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

def clean_row(row):
    cleaned = {}
    
    cleaned['id'] = row.get('id', '').strip()
    cleaned['establishment_name'] = row.get('nom_estab', '').strip() or 'Unknown'
    cleaned['legal_name'] = row.get('raz_social', '').strip() or ''
    cleaned['scian_code'] = row.get('codigo_act', '').strip()
    cleaned['activity_name'] = row.get('nombre_act', '').strip() or ''
    cleaned['facility_type'] = row.get('facility_type', '').strip()
    
    cleaned['street'] = clean_address(
        row.get('tipo_vial', ''),
        row.get('nom_vial', ''),
        row.get('numero_ext', ''),
        row.get('letra_ext', ''),
        row.get('numero_int', ''),
        row.get('letra_int', '')
    )
    
    cleaned['settlement_type'] = row.get('tipo_asent', '').strip() or ''
    cleaned['settlement_name'] = row.get('nomb_asent', '').strip() or ''
    cleaned['postal_code'] = row.get('cod_postal', '').strip() or ''
    
    cleaned['municipality'] = row.get('municipio', '').strip() or 'Unknown'
    cleaned['state'] = row.get('entidad', '').strip() or 'Unknown'
    
    cleaned['city'] = cleaned['settlement_name'] if cleaned['settlement_name'] else cleaned['municipality']
    
    lat, lon = clean_coordinates(row.get('latitud', ''), row.get('longitud', ''))
    cleaned['latitude'] = lat if lat is not None else ''
    cleaned['longitude'] = lon if lon is not None else ''
    
    cleaned['phone'] = clean_phone(row.get('telefono', ''))
    cleaned['email'] = row.get('correoelec', '').strip() or ''
    cleaned['website'] = row.get('www', '').strip() or ''
    
    cleaned['employees_range'] = row.get('per_ocu', '').strip() or ''
    cleaned['establishment_type'] = row.get('tipoUniEco', '').strip() or 'Fijo'
    cleaned['date_added'] = row.get('fecha_alta', '').strip() or ''
    cleaned['country'] = 'mx'
    
    return cleaned

def main():
    input_file = 'mexico_filtered.csv'
    output_file = 'mexico_cleaned.csv'
    
    count_processed = 0
    count_errors = 0
    
    print(f"Reading from {input_file}...")
    
    try:
        with open(input_file, 'r', encoding='latin-1') as infile:
            reader = csv.DictReader(infile)
            
            fieldnames = [
                'country', 'id', 'establishment_name', 'legal_name', 'scian_code',
                'activity_name', 'facility_type', 'street', 'settlement_type',
                'settlement_name', 'city', 'municipality', 'state', 'postal_code',
                'latitude', 'longitude', 'phone', 'email', 'website',
                'employees_range', 'establishment_type', 'date_added'
            ]
            
            with open(output_file, 'w', encoding='latin-1', newline='') as outfile:
                writer = csv.DictWriter(outfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for row in reader:
                    try:
                        cleaned = clean_row(row)
                        writer.writerow(cleaned)
                        count_processed += 1
                    except Exception as e:
                        print(f"  Error processing row: {e}")
                        count_errors += 1
                    
                    if count_processed % 5000 == 0:
                        print(f"  Processed {count_processed} records...")
        
        print(f"\nCleaning complete!")
        print(f"Records processed: {count_processed}")
        print(f"Errors encountered: {count_errors}")
        print(f"Output file: {output_file}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
