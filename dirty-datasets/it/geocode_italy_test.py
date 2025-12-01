#!/usr/bin/env python3
import csv
import urllib.request
import urllib.parse
import json
import time
import re

GEOCODIO_API_KEY = "e1cd921cddddc5dddbd6bc965b1cd5c6666c229"
GEOCODIO_URL = "https://api.geocod.io/v1.7/geocode"

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
                    return lat, lon, accuracy, None
            
    except urllib.error.HTTPError as e:
        if e.code == 422:
            print(f"      DEBUG: 422 error - response: {e.read().decode('utf-8')[:200]}")
        return 0.0, 0.0, 'failed', f"HTTP {e.code}"
    except Exception as e:
        return 0.0, 0.0, 'failed', str(e)
    
    return 0.0, 0.0, 'failed', 'No results'

def test_geocoding():
    """Test geocoding with first 10 records"""
    
    print("Testing geocoding with first 10 records...\n")
    
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
        
        province_code = extract_province_code(state)
        if province_code:
            state = province_code
        
        address = build_address(street, city, state)
        print(f"      Address: {address}")
        
        lat, lon, accuracy, error = geocode_address(address)
        
        if lat != 0.0 and lon != 0.0:
            is_italy = 40 < lat < 48 and 6 < lon < 20
            status = "[OK] ITALY" if is_italy else "[BAD] NOT ITALY"
            print(f"      Result: {status} ({lat:.4f}, {lon:.4f}) [{accuracy}]")
            results.append({
                'name': row['establishment_name'][:40],
                'address': address,
                'lat': lat,
                'lon': lon,
                'accuracy': accuracy,
                'is_italy': is_italy
            })
        else:
            print(f"      Result: [FAIL] ({error})")
            results.append({
                'name': row['establishment_name'][:40],
                'address': address,
                'lat': 0.0,
                'lon': 0.0,
                'accuracy': 'failed',
                'is_italy': False
            })
        
        print()
        time.sleep(0.1)
    
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    success = sum(1 for r in results if r['is_italy'])
    failed = sum(1 for r in results if not r['is_italy'] and (r['lat'] != 0.0 or r['lon'] != 0.0))
    no_result = sum(1 for r in results if r['lat'] == 0.0 and r['lon'] == 0.0)
    
    print(f"Success (Italy coords): {success}/10")
    print(f"Wrong coords (not Italy): {failed}/10")
    print(f"No result: {no_result}/10")
    
    if failed > 0:
        print(f"\nRecords with wrong coordinates:")
        for r in results:
            if not r['is_italy'] and (r['lat'] != 0.0 or r['lon'] != 0.0):
                print(f"  - {r['name']}: ({r['lat']:.4f}, {r['lon']:.4f})")
                print(f"    Tested: {r['address']}")

if __name__ == "__main__":
    test_geocoding()
    print("\nTest complete!")
