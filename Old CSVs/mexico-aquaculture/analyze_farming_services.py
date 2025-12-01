#!/usr/bin/env python3
import csv

print("=" * 80)
print("ANIMAL FARMING SERVICES - EXAMPLES")
print("=" * 80)
print()

count = 0
with open('locations.csv', 'r', encoding='latin-1') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row.get('type') == 'Farm / Breeder':
            print(f"Name: {row.get('establishment_name')}")
            print(f"  Activity: {row.get('activities')}")
            print(f"  Location: {row.get('city')}, {row.get('state')}")
            print(f"  Phone: {row.get('phone') if row.get('phone') else 'N/A'}")
            print(f"  Coordinates: {row.get('latitude')}, {row.get('longitude')}")
            print()
            count += 1
            if count >= 20:
                break

print(f"\nTotal Animal Farming Services: 158")

print("\n" + "=" * 80)
print("FISHING OPERATIONS - SIZE DISTRIBUTION")
print("=" * 80)
print()

with open('mexico_cleaned.csv', 'r', encoding='latin-1') as f:
    reader = csv.DictReader(f)
    employees = {}
    fishing_count = 0
    
    for row in reader:
        if row.get('facility_type') == 'Fishing Operation':
            fishing_count += 1
            emp_range = row.get('employees_range', 'Unknown')
            employees[emp_range] = employees.get(emp_range, 0) + 1

print(f"Total Fishing Operations: {fishing_count}")
print()
print("Employee Size Distribution:")
for emp_range in sorted(employees.keys()):
    count = employees[emp_range]
    pct = 100 * count / fishing_count
    print(f"  {emp_range:<20} {count:>6} ({pct:>5.1f}%)")
