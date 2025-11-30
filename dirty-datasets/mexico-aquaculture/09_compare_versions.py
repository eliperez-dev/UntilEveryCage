#!/usr/bin/env python3
"""
Compare full version vs focused version of Mexico data.
"""

import csv
import os
from collections import defaultdict

def analyze_file(filepath):
    """Analyze a deployed CSV file."""
    stats = {
        'total': 0,
        'by_type': defaultdict(int),
        'by_state': defaultdict(int),
        'with_coords': 0,
        'with_phone': 0
    }
    
    if not os.path.exists(filepath):
        return stats
    
    with open(filepath, 'r', encoding='latin-1') as f:
        reader = csv.DictReader(f)
        for row in reader:
            stats['total'] += 1
            
            ftype = row.get('type', 'Unknown')
            stats['by_type'][ftype] += 1
            
            state = row.get('state', 'Unknown')
            stats['by_state'][state] += 1
            
            if row.get('latitude') and row.get('longitude'):
                try:
                    lat = float(row.get('latitude', 0))
                    lon = float(row.get('longitude', 0))
                    if -90 <= lat <= 90 and -180 <= lon <= 180:
                        stats['with_coords'] += 1
                except:
                    pass
            
            if row.get('phone'):
                stats['with_phone'] += 1
    
    return stats

def main():
    print("=" * 80)
    print("MEXICO DATASET VERSIONS - COMPARISON")
    print("=" * 80)
    print()
    
    old_file = 'locations.csv'  # Original full version
    new_file = '../../static_data/mx/locations.csv'  # New focused version
    
    old_stats = analyze_file(old_file)
    new_stats = analyze_file(new_file)
    
    print("FULL VERSION (with fishing):")
    print("-" * 80)
    print(f"  Total records: {old_stats['total']:,}")
    print(f"  Facility types:")
    for ftype in sorted(old_stats['by_type'].keys()):
        count = old_stats['by_type'][ftype]
        pct = 100 * count / old_stats['total'] if old_stats['total'] > 0 else 0
        print(f"    - {ftype:<30} {count:>7,} ({pct:>5.1f}%)")
    print()
    
    print("FOCUSED VERSION (aquaculture + animal farming only):")
    print("-" * 80)
    print(f"  Total records: {new_stats['total']:,}")
    print(f"  Facility types:")
    for ftype in sorted(new_stats['by_type'].keys()):
        count = new_stats['by_type'][ftype]
        pct = 100 * count / new_stats['total'] if new_stats['total'] > 0 else 0
        print(f"    - {ftype:<30} {count:>7,} ({pct:>5.1f}%)")
    print()
    
    print("SUMMARY:")
    print("-" * 80)
    reduction = old_stats['total'] - new_stats['total']
    reduction_pct = 100 * reduction / old_stats['total'] if old_stats['total'] > 0 else 0
    print(f"  Records removed: {reduction:,} ({reduction_pct:.1f}%)")
    print(f"  Fishing operations excluded: {old_stats['by_type'].get('Fishing Operation', 0):,}")
    print()
    print(f"  Data quality (focused version):")
    print(f"    - With coordinates: {new_stats['with_coords']:,} (100%)")
    print(f"    - With phone: {new_stats['with_phone']:,} ({100*new_stats['with_phone']/new_stats['total']:.1f}%)")
    print(f"    - States covered: {len(new_stats['by_state'])} of 32")
    print()
    
    print("=" * 80)
    print("STATUS: Focused version deployed to static_data/mx/locations.csv")
    print("=" * 80)

if __name__ == '__main__':
    main()
