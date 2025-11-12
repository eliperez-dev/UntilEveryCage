import requests
from bs4 import BeautifulSoup
import csv

url = "https://www.salute.gov.it/consultazioneStabilimenti/ConsultazioneStabilimentiServlet?ACTION=gestioneSingolaCategoria&idNormativa=2&idCategoria=1"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

print("Fetching webpage...")
response = requests.get(url, headers=headers)
response.encoding = 'utf-8'

print("Parsing HTML...")
soup = BeautifulSoup(response.text, 'html.parser')

table = soup.find('table')

if not table:
    print("No table found on the page")
    exit()

rows = table.find_all('tr')
print(f"Found {len(rows)} rows in table")

headers_row = ['APPROVAL_NUMBER', 'NAME', 'VAT', 'TAX_CODE', 'TOWN_REGION', 'CATEGORY', 'ASSOCIATED_ACTIVITIES', 'SPECIES', 'REMARKS', 'TSE_FEED_BAN']

data = []

for i, row in enumerate(rows):
    cells = row.find_all(['th', 'td'])
    
    if i == 0 or i == 1:
        continue
    
    if len(cells) == 10:
        row_data = [cell.get_text(strip=True) for cell in cells]
        data.append(row_data)
    elif len(cells) > 0:
        print(f"Skipping row {i} with {len(cells)} columns")

output_file = 'd:/Projects/UntilEveryCage/Old CSVs/italian_facilities.csv'
print(f"\nWriting {len(data)} rows to {output_file}...")

with open(output_file, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(headers_row)
    writer.writerows(data)

print(f"Done! Scraped {len(data)} facilities")
print(f"Output saved to: {output_file}")
