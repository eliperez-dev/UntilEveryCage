import pandas as pd
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import time

def geocode_italian_facilities(input_filename="d:/Projects/UntilEveryCage/Old CSVs/italian_facilities.csv", 
                                output_filename="d:/Projects/UntilEveryCage/Old CSVs/italian_facilities_geocoded.csv"):
    """
    Reads Italian facilities CSV, geocodes the addresses to find latitude and longitude,
    and saves a new, enriched CSV file.
    """
    print("--- Starting Geocoding Process for Italian Facilities ---")
    
    try:
        df = pd.read_csv(input_filename, dtype=str)
        print(f"Successfully loaded {len(df)} records from '{input_filename}'.")
    except FileNotFoundError:
        print(f"ERROR: The input file '{input_filename}' was not found.")
        return

    geolocator = Nominatim(user_agent="italian_facilities_map/1.0", timeout=10)
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.1, error_wait_seconds=10.0)

    latitudes = []
    longitudes = []

    print("\nStarting to geocode addresses. This will take several minutes...")
    
    for index, row in df.iterrows():
        address_str = f"{row['TOWN_REGION']}, Italy"
        
        if (index + 1) % 100 == 0:
            print(f"  Progress: {index + 1}/{len(df)} ({(index + 1) / len(df) * 100:.1f}%)")

        try:
            location = geocode(address_str)
            if location:
                latitudes.append(location.latitude)
                longitudes.append(location.longitude)
            else:
                latitudes.append(None)
                longitudes.append(None)
                print(f"    > WARNING: Could not find coordinates for: {address_str}")

        except Exception as e:
            print(f"    > ERROR during geocoding row {index + 1}: {e}")
            latitudes.append(None)
            longitudes.append(None)

    df['latitude'] = latitudes
    df['longitude'] = longitudes
    
    successful = sum(1 for lat in latitudes if lat is not None)
    print(f"\nGeocoding complete: {successful}/{len(df)} addresses successfully geocoded ({successful/len(df)*100:.1f}%)")

    df.to_csv(output_filename, index=False)
    print(f"\nSUCCESS! Enriched data saved to '{output_filename}'")


if __name__ == "__main__":
    geocode_italian_facilities()
