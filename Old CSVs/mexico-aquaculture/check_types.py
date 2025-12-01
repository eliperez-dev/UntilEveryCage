import csv

types_count = {}
with open('../../static_data/mx/locations.csv', 'r', encoding='latin-1') as f:
    reader = csv.DictReader(f)
    for row in reader:
        type_val = row.get('type', '').strip()
        if type_val:
            types_count[type_val] = types_count.get(type_val, 0) + 1

for type_name in sorted(types_count.keys()):
    print(f'{type_name}: {types_count[type_name]}')
print(f'\nTotal types: {len(types_count)}')
