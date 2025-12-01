#!/usr/bin/env python3
import csv
from collections import defaultdict

scian_codes = defaultdict(set)

print("Analyzing SCIAN codes in DENUE dataset...")
try:
    with open('denue_inegi_11_.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            codigo = row.get('codigo_act', '').strip()
            nombre = row.get('nombre_act', '').strip()
            if codigo and nombre:
                scian_codes[codigo].add(nombre)
except UnicodeDecodeError:
    with open('denue_inegi_11_.csv', 'r', encoding='latin-1') as f:
        reader = csv.DictReader(f)
        for row in reader:
            codigo = row.get('codigo_act', '').strip()
            nombre = row.get('nombre_act', '').strip()
            if codigo and nombre:
                scian_codes[codigo].add(nombre)

print(f"\nFound {len(scian_codes)} unique SCIAN codes\n")
print("SCIAN Code | Activity Name")
print("-" * 80)
for codigo in sorted(scian_codes.keys()):
    names = list(scian_codes[codigo])
    print(f"{codigo}: {names[0]}")
