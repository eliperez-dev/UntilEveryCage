#!/usr/bin/env python3
import csv
import urllib.request
import urllib.parse
import json
import time
import re

GEOCODIO_API_KEY = "e1cd921cddddc5dddbd6bc965b1cd5c6666c229"
GEOCODIO_URL = "https://api.geocod.io/v1.7/geocode"

ITALY_PROVINCES = {
    'LT': 'Latina', 'RM': 'Roma', 'TA': 'Taranto', 'VR': 'Verona', 'PV': 'Pavia',
    'PT': 'Pistoia', 'IM': 'Imperia', 'UD': 'Udine', 'PU': 'Pesaro e Urbino', 'NO': 'Novara',
    'BI': 'Biella', 'TO': 'Torino', 'AL': 'Alessandria', 'AT': 'Asti', 'CN': 'Cuneo',
    'GE': 'Genova', 'SV': 'Savona', 'LA': 'La Spezia', 'BG': 'Bergamo', 'BS': 'Brescia'
}

def extract_province_code(city_state_str):
    """Extract province code from strings like 'BASSIANO (LT)' or 'ARICCIA (RM)'"""
    match = re.search(r'\(([A-Z]{2})\)\s*$', city_state_str)
    if match:
        return match.group(1)
    return None

def build_address_v2(street, city, state_code):
    """Build address with province code instead of full name"""
    parts = []
    if street and street.strip():
        parts.append(street.strip())
    if city and city.strip():
        parts.append(city.strip())
    if state_code and state_code.strip():
        parts.append(state_code.strip())
    parts.append('Italy')
    
    return ', '.join(parts)

def geocode_address(address):
    """Geocode a single address using geocod.io with better Italian support"""
    try:
        params = urllib.parse.urlencode({
            'q': address,
            'country': 'IT',
            'api_key': GEOCODIO_API_KEY
        })
        url = f"{GEOCODIO_URL}?{params}"
        
        with urllib.request.urlopen(url, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                if data.get('results') and len(data['results']) > 0:
                    result = data['results'][0]
                    lat = result['location']['lat']
                    lon = result['location']['lng']
                    accuracy = result.get('accuracy', 'unknown')
                    return lat, lon, accuracy, None
            
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print("[WARN] Rate limited by geocod.io, waiting 60 seconds...")
            time.sleep(60)
            return geocode_address(address)
        else:
            return 0.0, 0.0, 'failed', f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return 0.0, 0.0, 'failed', str(e)
    except Exception as e:
        return 0.0, 0.0, 'failed', str(e)
    
    return 0.0, 0.0, 'failed', 'No results'

def geocode_italy_facilities_v2(input_csv, output_csv):
    """Geocode Italian facilities with improved address format"""
    
    print(f"Reading from: {input_csv}")
    
    rows = []
    with open(input_csv, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    print(f"Found {len(rows)} facilities to geocode")
    
    geocoded_count = 0
    failed_count = 0
    skipped_count = 0
    bad_coords = []
    
    for idx, row in enumerate(rows):
        print(f"[{idx + 1}/{len(rows)}]", end=' ', flush=True)
        
        existing_lat = float(row.get('latitude', 0.0))
        existing_lon = float(row.get('longitude', 0.0))
        
        if existing_lat != 0.0 and existing_lon != 0.0:
            if 40 < existing_lat < 48 and 6 < existing_lon < 20:
                print("OK (valid existing)")
                skipped_count += 1
                continue
            else:
                print(f"BAD COORDS ({existing_lat:.2f}, {existing_lon:.2f}) - regeocoding")
                bad_coords.append((row['establishment_name'], existing_lat, existing_lon))
        
        street = row.get('street', '').strip()
        city = row.get('city', '').strip()
        state = row.get('state', '').strip()
        
        province_code = extract_province_code(state)
        if province_code:
            state = province_code
        
        address = build_address_v2(street, city, state)
        
        if not address or address == 'Italy':
            print("SKIP (no address)")
            skipped_count += 1
            continue
        
        lat, lon, accuracy, error = geocode_address(address)
        
        if lat != 0.0 and lon != 0.0:
            if 40 < lat < 48 and 6 < lon < 20:
                row['latitude'] = lat
                row['longitude'] = lon
                geocoded_count += 1
                print(f"OK ({lat:.4f}, {lon:.4f}) [{accuracy}]")
            else:
                print(f"FAIL (coords outside Italy: {lat:.4f}, {lon:.4f})")
                failed_count += 1
        else:
            print(f"FAIL ({error})")
            failed_count += 1
        
        time.sleep(0.1)
    
    print(f"\nWriting to: {output_csv}")
    
    with open(output_csv, 'w', newline='', encoding='utf-8-sig') as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    
    print(f"\nGeocoding Summary:")
    print(f"  - Successfully geocoded: {geocoded_count}")
    print(f"  - Failed: {failed_count}")
    print(f"  - Skipped (valid existing coords): {skipped_count}")
    print(f"  - Total: {len(rows)}")
    
    if bad_coords:
        print(f"\nBad coordinates detected and marked for regeocode:")
        for name, lat, lon in bad_coords[:10]:
            print(f"  - {name[:40]}: ({lat}, {lon})")

if __name__ == "__main__":
    input_file = "static_data/it/locations.csv"
    output_file = "static_data/it/locations.csv"
    
    geocode_italy_facilities_v2(input_file, output_file)
    print("\nGeocoding complete!")
