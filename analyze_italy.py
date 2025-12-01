import pandas as pd
import json

df = pd.read_csv('dirty-datasets/italy_locations.csv', encoding='utf-8-sig')
print('Column names:')
print(df.columns.tolist())
print('\nFirst 5 rows:')
print(df[['APPROVAL NUMBER', 'NAME', 'CATEGORY', 'ASSOCIATED ACTIVITIES', 'SPECIES', 'TOWN/REGION']].head(10))
print('\nUnique CATEGORY values:', sorted(df['CATEGORY'].dropna().unique()))
print('\nUnique ASSOCIATED ACTIVITIES values:', sorted(df['ASSOCIATED ACTIVITIES'].dropna().unique()))
print('\nSample SPECIES values:')
print(df['SPECIES'].dropna().head(20).tolist())
print(f'\nTotal rows: {len(df)}')
print(f'\nRows with missing coordinates: {df[df["APPROVAL NUMBER"].isna()].shape[0]}')

category_activity_combinations = df.groupby(['CATEGORY', 'ASSOCIATED ACTIVITIES']).size()
print('\nCategory + Activity Combinations:')
print(category_activity_combinations)
