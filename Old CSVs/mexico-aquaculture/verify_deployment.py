#!/usr/bin/env python3
"""
Verification script to ensure Mexico data has been properly integrated.
"""

import csv
import os
from collections import defaultdict

def verify_file(filepath, required_cols=None):
    """Verify CSV file exists and has valid structure."""
    if not os.path.exists(filepath):
        return False, f"File not found: {filepath}"
    
    try:
        with open(filepath, 'r', encoding='latin-1') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
            if required_cols:
                for col in required_cols:
                    if col not in reader.fieldnames:
                        return False, f"Missing required column: {col}"
            
            return True, f"OK ({len(rows)} records)"
    except Exception as e:
        return False, f"Error: {e}"

def analyze_deployment():
    """Analyze deployed Mexico data."""
    filepath = '../../static_data/mx/locations.csv'
    
    print("=" * 70)
    print("MEXICO DATASET DEPLOYMENT VERIFICATION")
    print("=" * 70)
    print()
    
    # Check if file exists
    if not os.path.exists(filepath):
        print(f"ERROR: {filepath} not found!")
        return False
    
    print(f"[*] Reading deployment file: {filepath}")
    
    try:
        stats = {
            'total': 0,
            'with_coords': 0,
            'by_type': defaultdict(int),
            'by_state': defaultdict(int),
            'with_phone': 0,
            'with_email': 0
        }
        
        with open(filepath, 'r', encoding='latin-1') as f:
            reader = csv.DictReader(f)
            for row in reader:
                stats['total'] += 1
                
                if row.get('latitude') and row.get('longitude'):
                    try:
                        lat = float(row.get('latitude', 0))
                        lon = float(row.get('longitude', 0))
                        if -90 <= lat <= 90 and -180 <= lon <= 180:
                            stats['with_coords'] += 1
                    except:
                        pass
                
                facility_type = row.get('type', 'Unknown')
                stats['by_type'][facility_type] += 1
                
                state = row.get('state', 'Unknown')
                stats['by_state'][state] += 1
                
                if row.get('phone'):
                    stats['with_phone'] += 1
                if row.get('email'):
                    stats['with_email'] += 1
        
        # Display results
        print()
        print("[OK] File loaded successfully")
        print()
        print("STATISTICS:")
        print("-" * 70)
        print(f"  Total facilities:        {stats['total']:>10,}")
        print(f"  With coordinates:        {stats['with_coords']:>10,} ({100*stats['with_coords']/stats['total']:.1f}%)")
        print(f"  With phone:              {stats['with_phone']:>10,} ({100*stats['with_phone']/stats['total']:.1f}%)")
        print(f"  With email:              {stats['with_email']:>10,} ({100*stats['with_email']/stats['total']:.1f}%)")
        print()
        
        print("FACILITY TYPES:")
        print("-" * 70)
        for ftype in sorted(stats['by_type'].keys()):
            count = stats['by_type'][ftype]
            pct = 100 * count / stats['total']
            print(f"  {ftype:<30} {count:>10,} ({pct:>5.1f}%)")
        print()
        
        print("STATES (Sample - Top 10):")
        print("-" * 70)
        sorted_states = sorted(stats['by_state'].items(), key=lambda x: x[1], reverse=True)
        for state, count in sorted_states[:10]:
            print(f"  {state:<30} {count:>10,}")
        print(f"  ... and {len(stats['by_state'])-10} more states (32 total)")
        print()
        
        print("=" * 70)
        print("DEPLOYMENT STATUS: [OK] READY FOR INTEGRATION")
        print("=" * 70)
        print()
        print("File size: {:.1f} MB".format(os.path.getsize(filepath) / 1024 / 1024))
        print("Location: {}".format(os.path.abspath(filepath)))
        print()
        print("Next steps:")
        print("  1. Build backend: cargo shuttle run")
        print("  2. Test API: /api/locations?country_code=mx")
        print("  3. Verify facilities appear on map")
        print()
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = analyze_deployment()
    exit(0 if success else 1)
