import pandas as pd
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import os
import time

# Configuration
INPUT_FILE = 'dirty-datasets/nz/data.csv'
OUTPUT_DIR = 'static_data/nz'
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'locations.csv')

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)


def process_nz_data():
    print(f"Reading {INPUT_FILE}...")
    try:
        df = pd.read_csv(INPUT_FILE)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    print(f"Found {len(df)} records.")

    # Initialize Geocoder
    geolocator = Nominatim(user_agent="nz_data_processor/1.0", timeout=10)
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.1)

    # Prepare new columns
    new_data = []

    # Limit for testing/demo purposes if needed. 
    # Set to None to process all.
    LIMIT = None
    count = 0
    for index, row in df.iterrows():
        if LIMIT and count >= LIMIT:
            break
            
        # Extract fields
        est_id = row.get('MPI ID Number', '')
        est_name = row.get('Operator Business Name', '')
        street = row.get('Physical Address', '')
        city = row.get('Physical Town/City', '')
        state = row.get('Operator Local Authority', '') # Using Authority as State/Region
        
        # Construct Address for Geocoding
        address = f"{street}, {city}, New Zealand"
        
        # Geocode
        lat = 0.0
        lon = 0.0
        
        try:
            location = geocode(address)
            if location:
                lat = location.latitude
                lon = location.longitude
                print(f"Geocoded {address} -> Lat: {lat}, Lon: {lon} ({index}/1654)")
        except Exception as e:
            print(f"Geocoding error for {address}: {e}")

        # Activities / Type
        risk_type = str(row.get('Risk Measure Type', ''))
        prog_type = str(row.get('Programme Type', ''))
        activities = f"{risk_type} - {prog_type}".strip(' -')

        # Slaughter / Processing
        secondary_process = str(row.get('Secondary Process', ''))
        product_material = str(row.get('Product/Material', ''))
        
        is_slaughter = "Yes" if "Slaughter" in secondary_process or "slaughter" in secondary_process.lower() else "No"
        
        # Animals Lists
        # We just use the Product/Material column as the list for now
        animals_processed = product_material
        animals_slaughtered = product_material if is_slaughter == "Yes" else ""

        new_record = {
            'establishment_id': est_id,
            'establishment_name': est_name,
            'street': street,
            'city': city,
            'state': state,
            'zip': '', # NZ Postcodes not explicitly in separate column usually
            'latitude': lat,
            'longitude': lon,
            'type': activities,
            'slaughter': is_slaughter,
            'animals_slaughtered_list': animals_slaughtered,
            'animals_processed_list': animals_processed,
            'phone': '',
            'grant_date': row.get('Effective Date', ''),
            'dbas': row.get('Operator Trading Name', ''),
            'slaughter_volume_category': '',
            'processing_volume_category': '',
            # Default boolean fields to empty (will be handled by Rust default)
        }
        
        new_data.append(new_record)
        count += 1

    # Create DataFrame
    out_df = pd.DataFrame(new_data)
    
    # Save
    print(f"Saving {len(out_df)} records to {OUTPUT_FILE}...")
    out_df.to_csv(OUTPUT_FILE, index=False)
    print("Done.")

if __name__ == "__main__":
    process_nz_data()
