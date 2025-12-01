#!/usr/bin/env python3
import csv
import urllib.request
import urllib.parse
import json
import time
import sys

GEOCODIO_API_KEY = "e1cd921cddddc5dddbd6bc965b1cd5c6666c229"
GEOCODIO_URL = "https://api.geocod.io/v1.7/geocode"

def build_address(row):
    """Build a full address from CSV row components"""
    street = row.get('street', '').strip()
    city = row.get('city', '').strip()
    state = row.get('state', '').strip()
    
    parts = [street, city, state, 'Italy']
    return ', '.join([p for p in parts if p])

def geocode_address(address):
    """Geocode a single address using geocod.io"""
    try:
        params = urllib.parse.urlencode({
            'q': address,
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
                    return lat, lon, accuracy
            
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print("[WARN] Rate limited by geocod.io, waiting 60 seconds...")
            time.sleep(60)
            return geocode_address(address)
        else:
            print(f"[ERROR] Geocod.io returned status {e.code}")
    except urllib.error.URLError as e:
        print(f"[WARN] URL error for address '{address}': {e}")
    except Exception as e:
        print(f"[ERROR] Geocoding error for '{address}': {e}")
    
    return 0.0, 0.0, 'failed'

def geocode_italy_facilities(input_csv, output_csv):
    """Geocode Italian facilities and update CSV"""
    
    print(f"Reading from: {input_csv}")
    
    rows = []
    with open(input_csv, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    print(f"Found {len(rows)} facilities to geocode")
    
    geocoded_count = 0
    failed_count = 0
    skipped_count = 0
    
    for idx, row in enumerate(rows):
        print(f"[{idx + 1}/{len(rows)}] Processing...")
        
        existing_lat = float(row.get('latitude', 0.0))
        existing_lon = float(row.get('longitude', 0.0))
        
        if existing_lat != 0.0 and existing_lon != 0.0:
            skipped_count += 1
            continue
        
        address = build_address(row)
        if not address or address == ', Italy':
            print(f"  [SKIP] No address components")
            skipped_count += 1
            continue
        
        lat, lon, accuracy = geocode_address(address)
        
        row['latitude'] = lat
        row['longitude'] = lon
        
        if lat != 0.0 and lon != 0.0:
            geocoded_count += 1
            print(f"  [OK] {address[:60]}... -> ({lat}, {lon}) [{accuracy}]")
        else:
            failed_count += 1
            print(f"  [FAIL] {address[:60]}...")
        
        time.sleep(0.1)
    
    print(f"\nWriting to: {output_csv}")
    
    with open(output_csv, 'w', newline='', encoding='utf-8-sig') as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    
    print(f"\nGeocoding Summary:")
    print(f"  - Newly geocoded: {geocoded_count}")
    print(f"  - Failed: {failed_count}")
    print(f"  - Skipped (already had coordinates): {skipped_count}")
    print(f"  - Total: {len(rows)}")

if __name__ == "__main__":
    input_file = "static_data/it/locations.csv"
    output_file = "static_data/it/locations.csv"
    
    geocode_italy_facilities(input_file, output_file)
    print("\nGeocoding complete!")
