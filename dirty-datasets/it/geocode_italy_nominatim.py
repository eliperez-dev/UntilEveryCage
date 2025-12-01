#!/usr/bin/env python3
"""Test geocoding using OpenStreetMap Nominatim (free, no API key needed)"""
import csv
import urllib.request
import urllib.parse
import json
import time
import re

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

def extract_province_code(city_state_str):
    """Extract province code from strings like 'BASSIANO (LT)'"""
    match = re.search(r'\(([A-Z]{2})\)\s*$', city_state_str)
    if match:
        return match.group(1)
    return None

def build_address(street, city, state_code):
    """Build full address"""
    parts = []
    if street and street.strip():
        parts.append(street.strip())
    if city and city.strip():
        parts.append(city.strip())
    parts.append('Italy')
    
    return ', '.join(parts)

def geocode_address_nominatim(address):
    """Geocode using OSM Nominatim"""
    try:
        params = urllib.parse.urlencode({
            'q': address,
            'format': 'json',
            'limit': 1
        })
        url = f"{NOMINATIM_URL}?{params}"
        
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(url, headers=headers)
        
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                if data and len(data) > 0:
                    result = data[0]
                    lat = float(result['lat'])
                    lon = float(result['lon'])
                    return lat, lon, 'nominatim', None
            
    except urllib.error.HTTPError as e:
        return 0.0, 0.0, 'failed', f"HTTP {e.code}"
    except Exception as e:
        return 0.0, 0.0, 'failed', str(e)
    
    return 0.0, 0.0, 'failed', 'No results'

def test_nominatim():
    """Test with Nominatim"""
    
    print("Testing geocoding with Nominatim (OpenStreetMap)...\n")
    
    rows = []
    with open('static_data/it/locations.csv', 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)[:10]
    
    print(f"Testing {len(rows)} facilities\n")
    
    results = []
    
    for idx, row in enumerate(rows):
        print(f"[{idx + 1}/10] Processing: {row['establishment_name'][:40]}")
        
        street = row.get('street', '').strip()
        city = row.get('city', '').strip()
        state = row.get('state', '').strip()
        
        address = build_address(street, city, state)
        print(f"      Address: {address}")
        
        lat, lon, accuracy, error = geocode_address_nominatim(address)
        
        if lat != 0.0 and lon != 0.0:
            is_italy = 40 < lat < 48 and 6 < lon < 20
            status = "[OK] ITALY" if is_italy else "[BAD] NOT ITALY"
            print(f"      Result: {status} ({lat:.4f}, {lon:.4f})")
            results.append({
                'name': row['establishment_name'][:40],
                'address': address,
                'lat': lat,
                'lon': lon,
                'is_italy': is_italy
            })
        else:
            print(f"      Result: [FAIL] ({error})")
            results.append({
                'name': row['establishment_name'][:40],
                'address': address,
                'lat': 0.0,
                'lon': 0.0,
                'is_italy': False
            })
        
        print()
        time.sleep(1.5)
    
    print("\n" + "="*80)
    print("NOMINATIM TEST SUMMARY")
    print("="*80)
    
    success = sum(1 for r in results if r['is_italy'])
    failed = sum(1 for r in results if not r['is_italy'] and (r['lat'] != 0.0 or r['lon'] != 0.0))
    no_result = sum(1 for r in results if r['lat'] == 0.0 and r['lon'] == 0.0)
    
    print(f"Success (Italy coords): {success}/10")
    print(f"Wrong coords (not Italy): {failed}/10")
    print(f"No result: {no_result}/10")
    
    if success > 0:
        print(f"\nSample successful results:")
        for r in results:
            if r['is_italy']:
                print(f"  - {r['name']}: ({r['lat']:.4f}, {r['lon']:.4f})")
                print(f"    Address: {r['address']}")

if __name__ == "__main__":
    test_nominatim()
    print("\nTest complete!")
