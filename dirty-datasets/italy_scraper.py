import requests
import pandas as pd
import io

url = "https://www.salute.gov.it/consultazioneStabilimenti/ConsultazioneStabilimentiServlet?ACTION=gestioneSingolaCategoria&idNormativa=2&idCategoria=1"

# Mimic a real browser
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

print("1. Downloading HTML...")
try:
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    
    # Parse ALL tables without assuming where the header is (header=None)
    # wrapping response.text in io.StringIO prevents a deprecation warning
    dfs = pd.read_html(io.StringIO(response.text), header=None)
    
    print(f"2. Parsing complete. Found {len(dfs)} tables in the HTML.")
    
    target_df = None
    
    # Loop through every table found to find the right one
    for i, df in enumerate(dfs):
        # Convert all data to string to make searching easier
        df_str = df.astype(str)
        
        # Search for the column header "APPROVAL NUMBER" in ANY row
        # We use a mask to find which row contains this text
        header_location = df_str.apply(lambda x: x.str.contains("APPROVAL NUMBER", case=False, na=False)).any(axis=1)
        
        if header_location.any():
            print(f"   -> Match found in Table {i}!")
            
            # Get the index of the row where the headers are
            header_row_index = header_location.idxmax()
            print(f"   -> Headers are located on row {header_row_index}. Extracting data below it...")
            
            # Slice the dataframe: 
            # 1. Take everything below the header row
            target_df = df.iloc[header_row_index + 1:].copy()
            
            # 2. Set the column names to the values found in the header row
            target_df.columns = df.iloc[header_row_index]
            
            # 3. Reset the index so it looks clean
            target_df.reset_index(drop=True, inplace=True)
            break
    
    if target_df is not None:
        filename = "italy_slaughterhouses.csv"
        # cleaning column names (strip whitespace)
        target_df.columns = target_df.columns.str.strip()
        
        target_df.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"3. SUCCESS: Extracted {len(target_df)} rows.")
        print(f"   Saved to: {filename}")
        
        # Print first few rows to verify
        print("\nPreview:")
        print(target_df[['APPROVAL NUMBER', 'NAME', 'TOWN/REGION']].head(3))
    else:
        print("ERROR: Scanned all tables but could not find the 'APPROVAL NUMBER' header row.")
        # Debug helper: print shapes of what we found
        for i, df in enumerate(dfs):
            print(f"Table {i} shape: {df.shape}")

except Exception as e:
    print(f"CRITICAL ERROR: {e}")