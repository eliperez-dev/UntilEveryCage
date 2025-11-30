#!/usr/bin/env python3
import shutil
import os

src = 'locations.csv'
dst = '../../static_data/mx/locations.csv'

try:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy(src, dst)
    print(f"Successfully copied {src} to {dst}")
except Exception as e:
    print(f"Error: {e}")
