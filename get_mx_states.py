import csv
states = set()
with open('static_data/mx/locations.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        states.add(row['state'].strip())
for state in sorted(states):
    print(state)
