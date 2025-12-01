#!/usr/bin/env python3
import csv

entidades = set()
municipios = set()
scian_codes = set()

try:
    encoding = 'latin-1'
    with open('denue_inegi_11_.csv', 'r', encoding=encoding) as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            count += 1
            entidades.add(row.get('entidad', ''))
            municipios.add(f"{row.get('entidad', '')} - {row.get('municipio', '')}")
            scian_codes.add(row.get('codigo_act', ''))
    
    print(f"Total records: {count}")
    print(f"\nEntidades (States): {sorted(entidades)}")
    print(f"\nNumber of unique municipalities: {len(municipios)}")
    print(f"\nSCIAN codes present: {sorted(scian_codes)}")
except Exception as e:
    print(f"Error: {e}")
