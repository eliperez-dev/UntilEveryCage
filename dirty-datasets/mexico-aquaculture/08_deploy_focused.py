#!/usr/bin/env python3
import shutil
import os

src = 'locations_focused.csv'
dst = '../../static_data/mx/locations.csv'

try:
    print(f"Deploying focused Mexico dataset...")
    print(f"  Source: {src}")
    print(f"  Destination: {dst}")
    
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy(src, dst)
    
    file_size = os.path.getsize(dst) / 1024 / 1024
    print(f"\nSuccess! Deployed {file_size:.2f} MB")
    print(f"Records: 3,270 (aquaculture + animal farming services)")
    print(f"Replaces: Previous 23,996 record version with fishing operations")
    
except Exception as e:
    print(f"Error: {e}")
